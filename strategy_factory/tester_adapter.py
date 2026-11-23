"""Isolated fake adapter exercising TesterRunner; operational entry always denies."""
from copy import deepcopy
from dataclasses import asdict
import json
import os
from pathlib import Path, PureWindowsPath
from typing import Protocol

from .analysis import read_artifact, summarize_run
from .batch_manifest import fingerprint
from .batch_safety import execution_gate
from .execution_audit import attach_execution_audit
from .tester import TesterRunner, payload


class IndividualTesterAdapter(Protocol):
    def request(self,config,*,inputs,request_identity,resources,before_start,should_stop): ...


class OperationalTesterAdapter:
    live_execution_enabled=False

    def request(self,*args,**kwargs):
        execution_gate()  # No transport, endpoint or executable approval accepted.


class LogicalClock:
    def __init__(self):self.value=0.0
    def __call__(self):return self.value
    def sleep(self,seconds):self.value+=seconds


class _FakeRunner(TesterRunner):
    def __init__(self,*args,lock_root,**kwargs):
        super().__init__(*args,**kwargs)
        self.fake_lock_root=lock_root

    def _terminal_lock_root(self):return self.fake_lock_root


class FakeTesterAdapter:
    """No socket, MCP client, subprocess, real EA bytes or operational locks.

    A newly created exclusive sandbox or a validated existing sandbox is required.
    State and attempts are explicitly synthetic. No authorization issuer exists.
    """
    live_execution_enabled=False
    FAULTS={'completed','zero_trades','before_start','after_start','timeout','stop_requested',
            'busy','remote_agent','hash_mismatch','duplicate_reservation','unknown_final',
            'communication_lost','terminal_closed','invalid_audit','resource_exceeded','resource_after_start','stop_unconfirmed',
            'python_interrupted','codex_interrupted','computer_restarted','delayed_response','start_response_lost',
            'reservation_failure','reservation_interrupted','report_failure','state_divergence'}

    def __init__(self,sandbox,*,fault='completed',reopen=False):
        if fault not in self.FAULTS:raise ValueError('unknown fake fault')
        self.sandbox=Path(sandbox)
        self.fault=fault
        self.calls=[]
        self.clock=LogicalClock()
        if reopen:
            self._read_state()  # Never initialize over damaged or unrelated state.
        else:
            self.sandbox.mkdir(parents=True,exist_ok=False)
            self._persist(dict(terminal_id=fingerprint(str(self.sandbox.resolve())),status='stopped',
                               run_id=None,request_sha256=None,start_calls=0))

    def _persist(self,state):
        document=dict(kind='synthetic_tester_state',state=state,sha256=fingerprint(state))
        target=self.sandbox/'fake_state.json';temporary=self.sandbox/'fake_state.pending'
        with temporary.open('x',encoding='utf-8') as stream:
            json.dump(document,stream,allow_nan=False);stream.flush();os.fsync(stream.fileno())
        temporary.replace(target)

    def _read_state(self):
        doc=read_artifact(self.sandbox/'fake_state.json')
        if (not isinstance(doc,dict) or set(doc)!={'kind','state','sha256'} or
            doc['kind']!='synthetic_tester_state' or doc['sha256']!=fingerprint(doc['state']) or
            set(doc['state'])!={'terminal_id','status','run_id','request_sha256','start_calls'} or
            doc['state']['terminal_id']!=fingerprint(str(self.sandbox.resolve()))):
            raise ValueError('incomplete or altered synthetic terminal state')
        return doc['state']

    def inspect(self):
        state=self._read_state()
        return dict(state,local_agents=1,use_remote=self.fault=='remote_agent',use_cloud=False,
                    busy=self.fault=='busy' or state['status']!='stopped',
                    memory_bytes=2**40 if self.fault=='resource_exceeded' or (self.fault=='resource_after_start' and state['status']=='running') else 67108864,cpu_percent=10)

    def finish_simulated_run(self):
        """Explicit fake-only external reconciliation action; never touches MT5."""
        state=self._read_state();state['status']='stopped';self._persist(state)
        self.fault='completed'

    def request(self,config,*,inputs,request_identity,resources,before_start,should_stop):
        self.clock=LogicalClock()
        directory=self.sandbox/'individual'/request_identity
        directory.mkdir(parents=True,exist_ok=True)
        state=self._read_state()
        if state['status']!='stopped':raise RuntimeError('synthetic terminal is not stopped')
        self.request_id=request_identity
        self.config=config
        self.inputs=deepcopy(inputs)
        self.owned_run='fake-'+request_identity[:24]
        self.start_requested=False
        self.stop_requested=False
        self.cached_stop=None
        self.before_start=before_start
        self.should_stop=should_stop
        self.resources=resources
        runner=_FakeRunner(directory,self._guarded_call,clock=self.clock,sleep=self.clock.sleep,
                           lock_root=self.sandbox/'locks')
        try:
            output=runner.run(config,simulate=False,authorized=True,
                timeout=resources.timeout_attempt_seconds,poll_interval=1,
                prepared_config_path=str(self._mql5()/'Profiles'/'Tester'/'synthetic.ini'))
            report=read_artifact(output/'report.json')
            summary=summarize_run(report,parameters=asdict(config),run_id=self.owned_run,
                                  inputs=self.inputs,execution={'status':'completed'},synthetic=True)
            summary=attach_execution_audit(summary,self._audit_evidence())
            summary['integration_context']=dict(simulation_only=True,request_sha256=request_identity,
                                                live_execution_enabled=False)
            if summary['data_quality']['classification']=='invalid' or summary['execution_audit']['status']=='inconsistent':
                raise ValueError('invalid synthetic audited result')
            return dict(status='completed',summary=summary,elapsed_seconds=self.clock(),
                        start_requested=True,stop_requested=False,ambiguous=False,
                        synthetic_run_id=self.owned_run,request_sha256=request_identity)
        except Exception as exc:
            observation=self.inspect()
            retained=(directory/'terminal.lock').exists() or any((self.sandbox/'locks').glob('*.lock'))
            ambiguous=(self.start_requested and observation['status']!='stopped') or retained
            return dict(status='interrupted' if ambiguous else 'failed',summary=None,
                        error_type=type(exc).__name__,elapsed_seconds=self.clock(),
                        start_requested=self.start_requested,stop_requested=self.stop_requested,
                        ambiguous=ambiguous,synthetic_run_id=self.owned_run if self.start_requested else None,
                        request_sha256=request_identity)

    def _guarded_call(self,name,args):
        if name=='tester_run_backtest':
            if self.start_requested:raise PermissionError('one start only')
            self.before_start()  # Atomic reservation and fresh checks UNDER runner locks.
            if self.fault=='reservation_interrupted':raise SystemExit('synthetic interruption after durable reservation')
            self.start_requested=True
        if name=='tester_get_status' and self.start_requested and not self.stop_requested:
            if self.fault=='stop_requested' or self.should_stop():raise InterruptedError('synthetic cancellation')
            observed=self.inspect()
            if (observed['memory_bytes']>self.resources.max_memory_bytes or observed['cpu_percent']>self.resources.max_cpu_percent or
                observed['use_remote'] is not False or observed['use_cloud'] is not False or observed['local_agents']>self.resources.max_local_agents):
                raise RuntimeError('synthetic resource budget exceeded')
        if name=='tester_stop':
            self.stop_requested=True
            deadline=self.clock()+self.resources.reconciliation_seconds
            observed=payload(self._fake_call('tester_get_status',args))
            if observed.get('tester_status')=='stopped':
                self.cached_stop={'structuredContent':observed};return {'structuredContent':{'already_stopped':True}}
            if observed.get('run_id')!=args['run_id'] or observed.get('tester_status')!='running':
                raise RuntimeError('ownership/final state unknown; no stop issued')
            response=self._fake_call(name,args)
            while self.clock()<deadline:
                status=self._fake_call('tester_get_status',args)
                data=payload(status)
                if data.get('tester_status')=='stopped':self.cached_stop=status;return response
                if data.get('run_id')!=args['run_id']:raise RuntimeError('ownership lost')
                self.clock.sleep(min(1,deadline-self.clock()))
            raise TimeoutError('synthetic stop not confirmed')
        if name=='tester_get_status' and self.cached_stop is not None:return self.cached_stop
        return self._fake_call(name,args)

    def _fake_call(self,name,args):
        self.calls.append((name,deepcopy(args)))
        state=self._read_state()
        if name=='get_workspace_info':
            if self.fault=='before_start':raise RuntimeError('synthetic failure before start')
            mql5=str(self._mql5())
            data=dict(capabilities={'can_run_backtest':True},workspace={'mql5_folder':mql5},
                      permissions=dict(read_roots=[mql5],write_roots=[mql5]))
        elif name=='tester_run_backtest':
            state.update(status='running',run_id=self.owned_run,request_sha256=self.request_id,start_calls=state['start_calls']+1)
            self._persist(state);data={'run_id':self.owned_run}
            if self.fault in ('start_response_lost','delayed_response'):
                if self.fault=='delayed_response':self.clock.sleep(self.resources.timeout_attempt_seconds+1)
                raise TimeoutError('synthetic start response unavailable')
        elif name=='tester_get_status':
            if self.fault in ('python_interrupted','codex_interrupted','computer_restarted') and self.start_requested:
                raise SystemExit('synthetic process interruption')
            if self.fault in ('communication_lost','terminal_closed') and self.start_requested:
                raise ConnectionError('synthetic transport unavailable')
            if self.fault=='state_divergence' and self.start_requested:
                state.update(status='running',run_id='another-fake-run');self._persist(state)
            elif self.fault=='unknown_final' and self.start_requested:
                state['status']='unknown';self._persist(state)
            elif self.fault not in ('timeout','stop_requested','stop_unconfirmed'):
                state['status']='stopped';self._persist(state)
            data=dict(tester_status=state['status'],run_id=state['run_id'] or '0')
            if self.fault=='after_start':data['success']=False
        elif name=='tester_stop':
            if self.fault!='stop_unconfirmed':state['status']='stopped';self._persist(state)
            data={'stop_requested':True}
        elif name=='tester_get_report':
            if self.fault=='report_failure':raise ConnectionError('synthetic report collection failure')
            zero=self.fault=='zero_trades'
            data=dict(run_id=self.owned_run,fixture_kind='SYNTHETIC integration result',
                statistics=dict(net_profit=0 if zero else 1,trades=0 if zero else 1,
                    initial_balance=self.config.deposit,final_balance=self.config.deposit+(0 if zero else 1),
                    gross_profit=0 if zero else 1,gross_loss=0,winning_trades=0 if zero else 1,
                    losing_trades=0,win_rate=0 if zero else 100,profit_factor=None,
                    equity_drawdown_relative=0,balance_drawdown_relative=0))
        else:raise PermissionError('tool outside fake allowlist')
        return {'structuredContent':data,'isError':False}

    def _mql5(self):
        for parent in PureWindowsPath(self.config.expert).parents:
            if parent.name.lower()=='mql5':return parent
        raise ValueError('synthetic expert path requires an MQL5 ancestor')

    def _audit_evidence(self):
        source=dict(run_id=self.owned_run,fixture_kind='SYNTHETIC normalized fills')
        ref=dict(source='fake',locator='synthetic normalized rows')
        zero=self.fault=='zero_trades'
        orders=[] if zero else [dict(id=str(i),symbol=self.config.symbol,side=side,requested_volume=1,
                   filled_volume=1,requested_price=price,state='filled',evidence=ref) for i,side,price in ((1,'buy',100),(2,'sell',101))]
        deals=[] if zero else [dict(id=str(i),order_id=str(i),symbol=self.config.symbol,side=side,
                   entry=entry,volume=1,price=price,profit=profit,commission=0,swap=0,fees=None,evidence=ref)
                   for i,side,entry,price,profit in ((1,'buy','in',100,0),(2,'sell','out',101,1))]
        evidence=dict(schema_version='1.0',run_id=self.owned_run,sources={'fake':dict(payload=source,sha256=fingerprint(source))},
            orders=orders,deals=deals,groups=[] if zero else [dict(id='1',direction='long',entry_deals=['1'],exit_deals=['2'],
            pairing_provenance='synthetic explicit pairing',evidence=ref)],exit_events=[],counts_complete=True,
            costs_complete=False,reported_net_profit=0 if zero else 1,contract_size=1)
        if self.fault=='invalid_audit':evidence['sources']['fake']['sha256']='0'*64
        return evidence
