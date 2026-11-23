"""Offline individual-consent contract laboratory; no executable issuer or token."""
from contextlib import contextmanager,closing
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime,timezone
import json
from pathlib import Path
import sqlite3

from .analysis import read_artifact,write_artifact,clean_inputs
from .batch_manifest import fingerprint,exact,identifier,timestamp,sha
from .batch_safety import validate_plan,execution_gate
from .integration_policy import ResourcePolicy,AcceptanceCriteria,controls_digest
from .period_planning import validate_candidate_periods
from .tester import BacktestConfig

CONTEXT_KEYS={'schema_version','purpose','live_execution_enabled','plan_sha256','manifest_sha256','controls_sha256',
    'scenario_sha256','run_id','attempt','strategy_id','strategy_version','source_sha256','compiled_sha256',
    'ea_path','inputs','parameters','period','stage','resources','acceptance','terminal'}


def _validate_context(context):
    exact(context,CONTEXT_KEYS,'complete individual review context')
    if context['schema_version']!='3.3D-context-1' or context['purpose']!='synthetic_contract_review' or context['live_execution_enabled'] is not False:
        raise PermissionError('non-executable review context required')
    for key in ('plan_sha256','manifest_sha256','controls_sha256','scenario_sha256','source_sha256','compiled_sha256'):
        sha(context[key])
        if context[key] is None:raise ValueError('mandatory identity missing')
    identifier(context['run_id']);identifier(context['strategy_id'])
    if not isinstance(context['strategy_version'],str) or not context['strategy_version']:
        raise ValueError('strategy version required')
    if clean_inputs(context['inputs']) is None:raise ValueError('explicit inputs required')
    if type(context['attempt']) is not int or context['attempt']<1:raise ValueError('specific attempt required')
    resources=ResourcePolicy(**context['resources']);criteria=AcceptanceCriteria(**context['acceptance'])
    if controls_digest(resources,criteria)!=context['controls_sha256']:raise ValueError('control hash mismatch')
    BacktestConfig(expert=context['ea_path'],**context['parameters'])
    periods=dict(development=None,out_of_sample=None,final_test=None)
    if context['stage'] not in periods:raise ValueError('invalid stage')
    periods[context['stage']]=context['period'];validate_candidate_periods(periods)
    if context['period'] is None or any(context['period'][key]!=context['parameters'][key] for key in ('from_date','to_date')):
        raise ValueError('period and requested scenario mismatch')
    exact(context['terminal'],{'installation_sha256','server','build','environment'},'terminal')
    sha(context['terminal']['installation_sha256'])
    if context['terminal']['installation_sha256'] is None or context['terminal']['environment']!='demo' or context['terminal']['server']!='Rico-DEMO' or type(context['terminal']['build']) is not int or context['terminal']['build']<1:
        raise ValueError('reviewed demo terminal identity required')


def review_context(plan,run_id,attempt,terminal,resources,criteria):
    """Build a review target, never human consent or authorization."""
    plan=validate_plan(plan);validate_candidate_periods(plan['periods'])
    if type(resources) is not ResourcePolicy or type(criteria) is not AcceptanceCriteria:
        raise ValueError('typed reviewed controls required')
    exact(terminal,{'installation_sha256','server','build','environment'},'terminal identity')
    sha(terminal['installation_sha256'])
    if terminal['installation_sha256'] is None or terminal['environment']!='demo' or terminal['server']!='Rico-DEMO' or type(terminal['build']) is not int or terminal['build']<1:
        raise ValueError('explicit demo terminal identity required')
    run=next((r for r in plan['manifest']['runs'] if r['run_id']==run_id),None)
    if run is None or type(attempt) is not int or not 1<=attempt<=plan['manifest']['budget']['max_attempts_per_test']:
        raise ValueError('invalid specific attempt')
    if resources.timeout_attempt_seconds>plan['manifest']['budget']['timeout_per_test_seconds'] or resources.timeout_batch_seconds>plan['manifest']['budget']['timeout_batch_seconds']:
        raise ValueError('controls exceed reviewed manifest budget')
    scenario=next(s for s in plan['scenarios'] if s['run_id']==run_id)
    strategy=next(s for s in plan['manifest']['strategies'] if s['strategy_id']==run['strategy_id'])
    return dict(schema_version='3.3D-context-1',purpose='synthetic_contract_review',live_execution_enabled=False,
        plan_sha256=fingerprint(plan),manifest_sha256=fingerprint(plan['manifest']),controls_sha256=controls_digest(resources,criteria),
        scenario_sha256=scenario['scenario_sha256'],run_id=run_id,attempt=attempt,
        strategy_id=strategy['strategy_id'],strategy_version=strategy['version'],
        source_sha256=strategy['ea']['source_sha256'],compiled_sha256=strategy['ea']['compiled_sha256'],
        ea_path=strategy['ea']['path'],inputs=deepcopy(run['inputs']),parameters=deepcopy(run['parameters']),
        period=deepcopy(plan['periods'][scenario['stage']]),stage=scenario['stage'],
        resources=asdict(resources),acceptance=asdict(criteria),terminal=deepcopy(terminal))


def validate_consent_fixture(record,context,*,now=None):
    """Only a deliberately non-executable human-consent TEST fixture is accepted.

    There is no claim that actor strings authenticate a person. A real human
    approval channel and its trust/provenance checks remain unimplemented.
    """
    _validate_context(context)
    if not isinstance(record,dict):raise PermissionError('explicit individual consent fixture missing')
    exact(record,{'schema_version','fixture_kind','scope','authorization_id','context','context_sha256',
                  'issued_at','expires_at','human_consent'},'consent fixture')
    if record['schema_version']!='3.3D-contract-1' or record['fixture_kind']!='synthetic_non_executable' or record['scope']!='offline_contract_test':
        raise PermissionError('real or legacy authorization ineligible in this laboratory')
    identifier(record['authorization_id'])
    if context.get('purpose')!='synthetic_contract_review' or context.get('live_execution_enabled') is not False or record['context_sha256']!=fingerprint(context) or fingerprint(record['context'])!=fingerprint(context):
        raise PermissionError('consent does not bind the exact reviewed context')
    consent=record['human_consent']
    exact(consent,{'actor_kind','actor_id','statement','context_sha256'},'human consent test evidence')
    if (consent['actor_kind']!='human_test_fixture' or consent['actor_id']!='synthetic-human-reviewer' or
        consent['context_sha256']!=fingerprint(context) or
        consent['statement']!='CONSENTIMENTO HUMANO SINTETICO PARA TESTE OFFLINE '+fingerprint(context)):
        raise PermissionError('absent, agent-originated or mismatched explicit test consent')
    if not timestamp(record['issued_at'])<=(now or datetime.now(timezone.utc))<timestamp(record['expires_at']):
        raise PermissionError('consent expired or not yet valid')
    return True


class ConsentSimulationLedger:
    """Atomic single-use consumption/revocation in an exclusive synthetic root.

    Never imports an MCP/runner, never calls a callback, and cannot remove a
    consumed attempt. Receipts are test artifacts, categorically non-executable.
    """
    live_execution_enabled=False
    MARKER={'schema_version':'3.3D-contract-1','synthetic_only':True,'operational_use_forbidden':True}

    def __init__(self,root,*,reopen=False):
        self.root=Path(root);self.path=self.root/'consent_simulation.sqlite'
        if reopen:
            if fingerprint(read_artifact(self.root/'synthetic_only.json'))!=fingerprint(self.MARKER):raise PermissionError('unrelated or incomplete laboratory state')
            with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
                for table in ('fixtures','consumptions','revocations','starts','events'):
                    db.execute('SELECT 1 FROM '+table+' LIMIT 1').fetchall()
        else:
            self.root.mkdir(parents=True,exist_ok=False)
            write_artifact(self.root/'synthetic_only.json',self.MARKER)
            with self._db(create=True) as db:
                db.execute('CREATE TABLE fixtures (id TEXT PRIMARY KEY, checksum TEXT UNIQUE, record TEXT NOT NULL)')
                db.execute('CREATE TABLE consumptions (scenario TEXT, attempt INTEGER, id TEXT UNIQUE, context TEXT, receipt TEXT, PRIMARY KEY(scenario,attempt))')
                db.execute('CREATE TABLE revocations (id TEXT PRIMARY KEY, reason TEXT NOT NULL)')
                db.execute('CREATE TABLE starts (id TEXT PRIMARY KEY, context TEXT NOT NULL)')
                db.execute('CREATE TABLE events (seq INTEGER PRIMARY KEY, action TEXT, id TEXT, checksum TEXT)')

    def _commit(self,db):db.commit()

    @contextmanager
    def _db(self,*,create=False):
        if fingerprint(read_artifact(self.root/'synthetic_only.json'))!=fingerprint(self.MARKER):
            raise PermissionError('synthetic laboratory marker missing or altered')
        mode='rwc' if create else 'rw'
        db=sqlite3.connect(self.path.resolve().as_uri()+'?mode='+mode,uri=True,timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE')
            yield db;self._commit(db)
        except BaseException:db.rollback();raise
        finally:db.close()

    def _event(self,db,action,identity,value):
        db.execute('INSERT INTO events(action,id,checksum) VALUES(?,?,?)',(action,identity,fingerprint(value)))

    def register_fixture(self,record,context,*,now=None):
        validate_consent_fixture(record,context,now=now)
        with self._db() as db:
            existing=db.execute('SELECT checksum FROM fixtures WHERE id=?',(record['authorization_id'],)).fetchone()
            if existing:
                if existing[0]!=fingerprint(record):raise PermissionError('authorization ID already identifies another fixture')
                return {'registered':True,'simulation_only':True,'live_execution_enabled':False}
            db.execute('INSERT INTO fixtures VALUES(?,?,?)',(record['authorization_id'],fingerprint(record),json.dumps(record,allow_nan=False)))
            self._event(db,'registered',record['authorization_id'],record)
        return {'registered':True,'simulation_only':True,'live_execution_enabled':False}

    def _checked(self,db,identity,context,now):
        row=db.execute('SELECT checksum,record FROM fixtures WHERE id=?',(identity,)).fetchone()
        if row is None:raise PermissionError('fixture not registered')
        record=json.loads(row[1])
        if row[0]!=fingerprint(record):raise PermissionError('persistent fixture altered')
        validate_consent_fixture(record,context,now=now)
        if db.execute('SELECT 1 FROM revocations WHERE id=?',(identity,)).fetchone():raise PermissionError('fixture revoked')
        return record

    def consume_fixture(self,identity,context,*,now=None):
        with self._db() as db:
            self._checked(db,identity,context,now)
            base=dict(authorization_id=identity,context_sha256=fingerprint(context),simulation_only=True,
                      live_execution_enabled=False,consumed_at=(now or datetime.now(timezone.utc)).isoformat())
            receipt=dict(base,receipt_sha256=fingerprint(base))
            try:
                db.execute('INSERT INTO consumptions VALUES(?,?,?,?,?)',
                    (context['scenario_sha256'],context['attempt'],identity,fingerprint(context),json.dumps(receipt)))
            except sqlite3.IntegrityError:raise PermissionError('authorization or scenario/attempt already consumed') from None
            self._event(db,'consumed',identity,receipt)
        return receipt

    def revoke_fixture(self,identity,*,reason='synthetic_review_revoked'):
        identifier(reason)
        with self._db() as db:
            if not db.execute('SELECT 1 FROM fixtures WHERE id=?',(identity,)).fetchone():raise PermissionError('unknown fixture')
            if not db.execute('SELECT 1 FROM revocations WHERE id=?',(identity,)).fetchone():
                db.execute('INSERT INTO revocations VALUES(?,?)',(identity,reason))
                self._event(db,'revoked',identity,{'reason':reason})
        return {'revoked':True,'simulation_only':True,'consumption_erased':False}

    def record_simulated_start(self,receipt,context,*,now=None):
        """A database event only. No command, transport or user callback exists."""
        with self._db() as db:
            identity=receipt.get('authorization_id')
            self._checked(db,identity,context,now)
            row=db.execute('SELECT receipt,context FROM consumptions WHERE id=?',(identity,)).fetchone()
            if row is None or fingerprint(json.loads(row[0]))!=fingerprint(receipt) or row[1]!=fingerprint(context):
                raise PermissionError('exact consumed receipt required')
            try:db.execute('INSERT INTO starts VALUES(?,?)',(identity,fingerprint(context)))
            except sqlite3.IntegrityError:raise PermissionError('synthetic start already recorded; no replay') from None
            self._event(db,'synthetic_start',identity,receipt)
        return {'simulation_only':True,'real_start_requested':False,'live_execution_enabled':False}

    def inspect(self):
        with closing(sqlite3.connect(self.path.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            counts={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('fixtures','consumptions','revocations','starts','events')}
            pending=db.execute('SELECT count(*) FROM consumptions c LEFT JOIN starts s ON s.id=c.id WHERE s.id IS NULL').fetchone()[0]
        return dict(counts=counts,consumed_without_start_event=pending,automatic_restart=False,live_execution_enabled=False,simulation_only=True)

    def execute(self,*args,**kwargs):execution_gate()
