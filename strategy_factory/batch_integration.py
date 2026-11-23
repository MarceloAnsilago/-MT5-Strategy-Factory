"""Batch-to-individual integration harness. Exact fake adapter only; no MCP."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import sqlite3

from .analysis import read_artifact
from .batch_control import BatchBlocked
from .batch_manifest import fingerprint
from .batch_offline import OfflineBatchController
from .batch_safety import validate_plan, execution_gate
from .batch_consolidation import consolidate
from .integration_policy import ResourcePolicy, AcceptanceCriteria, check_individual_fixture, assess_acceptance, controls_digest
from .tester import BacktestConfig
from .tester_adapter import FakeTesterAdapter


class IntegrationBatchController(OfflineBatchController):
    """Extends the durable 3.3A ledger; never accepts an operational adapter."""
    live_execution_enabled=False

    def __init__(self,root,**kwargs):
        database=Path(root)/'control.sqlite'
        if database.exists():
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='integration_sandbox'").fetchone():
                    raise BatchBlocked('use a new integration root; historical ledgers cannot be repurposed')
        super().__init__(root,**kwargs)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS integration_sandbox (synthetic_only INTEGER CHECK(synthetic_only=1))')

    def simulate(self,*args,**kwargs):
        raise BatchBlocked('use simulate_integration; do not mix simulation engines in this ledger')

    def execute(self,*args,**kwargs):execution_gate()

    @staticmethod
    def _fake(adapter):
        if type(adapter) is not FakeTesterAdapter:
            raise PermissionError('integration harness accepts only the built-in exact fake adapter')

    def _preflight(self,plan,run_id,attempt,record,adapter,resources,criteria,now):
        validate_plan(plan)
        check_individual_fixture(plan,record,run_id=run_id,attempt=attempt,
                                 resources=resources,criteria=criteria,now=now)
        observation=adapter.inspect()
        if (observation['status']!='stopped' or observation['busy'] or observation['use_remote'] is not False or
            observation['use_cloud'] is not False or observation['local_agents']>resources.max_local_agents):
            raise BatchBlocked('synthetic Tester busy or agent policy not confirmed')
        if observation['memory_bytes']>resources.max_memory_bytes or observation['cpu_percent']>resources.max_cpu_percent:
            raise BatchBlocked('synthetic CPU/memory budget exceeded')
        if adapter.fault in ('hash_mismatch','duplicate_reservation'):
            raise BatchBlocked('synthetic hash mismatch or duplicate reservation')
        return observation

    def simulate_integration(self,batch_id,adapter,authorizations,*,resources=None,criteria=None,now=None,resume=None):
        self._fake(adapter)
        resources=resources or ResourcePolicy();criteria=criteria or AcceptanceCriteria()
        if type(resources) is not ResourcePolicy or type(criteria) is not AcceptanceCriteria:
            raise ValueError('typed resource and acceptance policies required')
        with self._worker(batch_id):
            with self._db() as db:
                manifest,state=self._load(db,batch_id)
                plan=validate_plan(read_artifact(self.root/batch_id/'safe_plan.json'))
                budget=manifest['budget']
                if resources.timeout_attempt_seconds>budget['timeout_per_test_seconds'] or resources.timeout_batch_seconds>budget['timeout_batch_seconds']:
                    raise BatchBlocked('integration timeouts exceed manifest budget')
                if state.get('integration_blocked') or any(r.get('requires_reconciliation') for r in state['runs'].values()):
                    raise BatchBlocked('ambiguous integration requires verified reconciliation')
                selected=self._select_attempts(manifest,state,resume)
                state.update(status='simulating',cancel_requested=False,integration_mode='synthetic_only')
                self._save(db,batch_id,state)
            try:
                for spec in manifest['runs']:
                    key=spec['run_id']
                    if key not in selected:continue
                    attempt=selected[key]
                    record=authorizations.get(key) if isinstance(authorizations,dict) else None
                    with self._db() as db:
                        _,state=self._load(db,batch_id)
                        if state['cancel_requested']:raise BatchBlocked('batch stop requested')
                        used=state.get('integration_seconds_used',0)
                        if used+resources.timeout_attempt_seconds>min(resources.timeout_batch_seconds,budget['timeout_batch_seconds']):
                            raise BatchBlocked('batch logical time budget exceeded')
                        if state.get('consecutive_failures',0)>=resources.max_consecutive_failures:
                            raise BatchBlocked('consecutive failure budget exhausted; new review required')
                        if (sum(len(r['attempts']) for r in state['runs'].values())>=budget['max_backtests'] or
                            self._usage(batch_id)>=budget['max_artifact_bytes'] or self.free_bytes()<budget['min_free_disk_bytes']):
                            raise BatchBlocked('attempt/storage/free disk budget exceeded')
                    observation=self._preflight(plan,key,attempt,record,adapter,resources,criteria,now)
                    scenario=next(s for s in plan['scenarios'] if s['run_id']==key)
                    request_id=fingerprint(dict(plan_sha256=fingerprint(plan),scenario_sha256=scenario['scenario_sha256'],
                                                attempt=attempt,controls_sha256=controls_digest(resources,criteria)))

                    def reserve():
                        # Called by the individual runner adapter under both isolated runner locks.
                        current=self._preflight(plan,key,attempt,record,adapter,resources,criteria,now)
                        if current['terminal_id']!=observation['terminal_id']:raise BatchBlocked('terminal identity changed')
                        with self._db() as db:
                            _,latest=self._load(db,batch_id)
                            run=latest['runs'][key]
                            if latest['cancel_requested'] or run.get('requires_reconciliation') or len(run['attempts'])+1!=attempt:
                                raise BatchBlocked('duplicate or cancelled reservation')
                            run['status']='simulating'
                            run['attempts'].append(dict(attempt=attempt,status='simulating',simulation_only=True,
                                request_sha256=request_id,terminal_id=current['terminal_id'],
                                sandbox=str(adapter.sandbox.resolve()),start_requested=True))
                            self._save(db,batch_id,latest)

                    strategy=next(s for s in manifest['strategies'] if s['strategy_id']==spec['strategy_id'])
                    def should_stop():
                        with self._db() as db:
                            _,latest=self._load(db,batch_id)
                            return latest['cancel_requested'] or used+adapter.clock()>=resources.timeout_batch_seconds
                    result=adapter.request(BacktestConfig(expert=strategy['ea']['path'],**spec['parameters']),
                                           inputs=spec['inputs'],request_identity=request_id,resources=resources,
                                           before_start=reserve,should_stop=should_stop)
                    summary=result.get('summary')
                    if result['status']=='completed':
                        if (not isinstance(summary,dict) or summary.get('evidence_kind')!='synthetic' or
                            summary.get('run_id')!=result['synthetic_run_id'] or summary.get('schema_version')!='1.1' or
                            summary.get('strategy',{}).get('inputs')!=spec['inputs'] or summary.get('parameters')!=spec['parameters'] or
                            summary.get('execution',{}).get('status')!='completed' or
                            summary.get('data_quality',{}).get('classification') in ('invalid','unavailable') or
                            summary.get('execution_audit',{}).get('status') not in ('consistent','partial')):
                            raise ValueError('invalid synthetic result')
                        consolidate([summary])  # Validate audit scope before persisting success.
                        assessment=assess_acceptance(summary,plan,key,criteria)
                        summary['batch_context']=dict(plan_sha256=fingerprint(plan),scenario_sha256=scenario['scenario_sha256'],
                            run_id=key,attempt=attempt,strategy_id=strategy['strategy_id'],strategy_version=strategy['version'],simulation_only=True)
                        relative=Path('runs')/key/('attempt_'+str(attempt))
                        self._write(manifest,relative/'audited_summary.json',summary,relative)
                        self._write(manifest,relative/'acceptance.json',assessment,relative)
                    with self._db() as db:
                        _,state=self._load(db,batch_id)
                        run=state['runs'][key]
                        state['integration_seconds_used']=state.get('integration_seconds_used',0)+result['elapsed_seconds']
                        # Pre-start failures do not invent a reservation or consume an attempt.
                        if run['attempts'] and run['attempts'][-1]['attempt']==attempt:
                            run['status']='simulated' if result['status']=='completed' else result['status']
                            run['attempts'][-1].update(status=run['status'],result=deepcopy({k:v for k,v in result.items() if k!='summary'}))
                        if result['ambiguous']:
                            run['requires_reconciliation']=True;state['integration_blocked']=True
                        if result['status']!='completed':
                            state['consecutive_failures']=state.get('consecutive_failures',0)+1
                            state['status']='interrupted' if result['ambiguous'] else 'failed'
                        else:state['consecutive_failures']=0
                        self._save(db,batch_id,state)
                    if result['status']!='completed':return deepcopy(state)
                # Consolidate immutable persisted audited summaries, including earlier explicit selections.
                paths=sorted((self.root/batch_id/'runs').glob('*/attempt_*/audited_summary.json'))
                collection=consolidate(read_artifact(p) for p in paths)
                with self._db() as db:
                    _,state=self._load(db,batch_id)
                    state['status']='simulated' if all(r['status']=='simulated' for r in state['runs'].values()) else 'paused'
                    state['integration_consolidation']=collection
                    self._save(db,batch_id,state)
                    return deepcopy(state)
            except BaseException as exc:
                with self._db() as db:
                    _,state=self._load(db,batch_id)
                    ambiguous=False
                    for run in state['runs'].values():
                        if run['status']=='simulating':
                            run['status']='interrupted';run['requires_reconciliation']=True
                            run['attempts'][-1]['status']='interrupted';ambiguous=True
                    state['integration_blocked']=ambiguous or state.get('integration_blocked',False)
                    state['status']='interrupted' if ambiguous else 'blocked'
                    state['consecutive_failures']=state.get('consecutive_failures',0)+1
                    state['error_type']=type(exc).__name__
                    self._save(db,batch_id,state)
                raise

    def reconcile_simulation(self,*args,**kwargs):
        raise BatchBlocked('integration requires adapter observations, not a boolean stopped assertion')

    def reconcile_integration(self,batch_id,run_id,adapter):
        self._fake(adapter)
        with self._worker(batch_id):
            with self._db() as db:
                _,state=self._load(db,batch_id)
                run=state['runs'][run_id]
                if not run.get('requires_reconciliation') or not run['attempts']:
                    raise BatchBlocked('no interrupted integration attempt')
                attempt=run['attempts'][-1]
                observed=adapter.inspect()
                if (observed['status']!='stopped' or observed['busy'] or observed['terminal_id']!=attempt['terminal_id'] or
                    observed['request_sha256']!=attempt['request_sha256'] or
                    observed['run_id']!='fake-'+attempt['request_sha256'][:24] or
                    str(adapter.sandbox.resolve())!=attempt['sandbox']):
                    raise BatchBlocked('synthetic stopped observation does not reconcile this attempt')
                # Remove only known locks under this exact synthetic sandbox, after observation.
                directory=adapter.sandbox/'individual'/attempt['request_sha256']
                lock=directory/'terminal.lock'
                shared_locks=list((adapter.sandbox/'locks').glob('*.lock'))
                if bool(lock.exists())!=bool(shared_locks) or len(shared_locks)>1:
                    raise BatchBlocked('incomplete synthetic lock evidence')
                if lock.exists():
                    owner=lock.read_text(encoding='utf-8')
                    owned=directory/owner
                    if owned.parent!=directory or not owned.is_dir():raise BatchBlocked('unknown synthetic lock owner')
                    if any(shared.read_text(encoding='utf-8')!=str(owned.resolve()) for shared in shared_locks):
                        raise BatchBlocked('different synthetic lock owner')
                    for shared in shared_locks:shared.unlink()
                    lock.unlink()
                run['requires_reconciliation']=False
                attempt['reconciliation']=dict(simulation_only=True,observation=observed)
                state['integration_blocked']=any(r.get('requires_reconciliation') for r in state['runs'].values())
                self._save(db,batch_id,state)
                return deepcopy(state)
