"""Read-only transport and persistent synthetic recovery; never connect to MT5."""
from copy import deepcopy
from contextlib import closing
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock,patch

import test_batch_integration as prior
from strategy_factory.analysis import read_artifact
from strategy_factory.batch_control import BatchBlocked
from strategy_factory.batch_integration import IntegrationBatchController
from strategy_factory.batch_manifest import fingerprint,validate_manifest
from strategy_factory.homologation_transport import HomologationTransport,Operation,assess_probe_observations
from strategy_factory.mcp import RicoQueryMCP
from strategy_factory.readiness import assess_readiness,FIELDS
from strategy_factory.recovery_inspection import inspect_recovery
from strategy_factory.supervised_proposal import propose_supervised_batch,validate_proposal
from strategy_factory.tester_adapter import FakeTesterAdapter,LogicalClock
from strategy_factory.tester import BacktestConfig

ROOT=Path(__file__).resolve().parents[1]


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.clock=LogicalClock()
        def call(server,name,args):
            if name=='get_workspace_info':return {'structuredContent':{'workspace':{'mql5_folder':r'C:\SYNTHETIC\MQL5'}}}
            return {'structuredContent':{'tester_status':'stopped','run_id':'0'}}
        self.call=Mock(side_effect=call)
        self.transport=HomologationTransport(self.call,clock=self.clock)

    def test_separate_workspace_preflight_and_no_network(self):
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            with self.assertRaises(PermissionError):self.transport.monitor('historical')
            self.transport.query('metaeditor','get_workspace_info',{})
            with self.assertRaises(PermissionError):self.transport.monitor('historical')
            self.transport.query('terminal','get_workspace_info',{})
            self.assertEqual(self.transport.monitor('historical')['tester_status'],'stopped')

    def test_operational_tools_and_methods_never_reach_transport(self):
        for name in ('tester_prepare_config','tester_run_backtest','run_backtest','compile_file','tester_stop'):
            with self.assertRaises(PermissionError):self.transport.query('terminal',name,{})
        self.transport.live_execution_enabled=True  # A lone flag cannot unlock dispatch.
        for method in (self.transport.reserve,self.transport.start,self.transport.stop):
            with self.assertRaises(PermissionError):method(enabled=True,authorization={'approved':True})
        self.call.assert_not_called()

    def test_query_client_rejects_operational_allowlist(self):
        client=object.__new__(RicoQueryMCP);client._rpc=Mock(return_value={})
        with self.assertRaises(PermissionError):client('tester_run_backtest',{})
        client._rpc.assert_not_called()
        client('get_workspace_info',{});self.assertEqual(client._rpc.call_count,1)

    def test_connection_loss_is_latched_no_retry_no_sensitive_audit(self):
        self.call.side_effect=ConnectionError('SYNTHETIC secret must not enter audit')
        with self.assertRaises(ConnectionError):self.transport.query('terminal','get_workspace_info',{})
        self.assertTrue(self.transport.blocked);self.assertEqual(self.call.call_count,1)
        self.assertNotIn('secret',str(self.transport.audit))
        with self.assertRaises(PermissionError):self.transport.monitor('old')

    def test_delayed_query_never_counts_as_success(self):
        def delayed(*args):
            self.clock.sleep(16);return {'structuredContent':{'workspace':{'mql5_folder':'SYNTHETIC'}}}
        self.call.side_effect=delayed
        with self.assertRaises(TimeoutError):self.transport.query('terminal','get_workspace_info',{})
        self.assertEqual(self.transport.audit[0]['outcome'],'failed');self.assertEqual(self.call.call_count,1)

    def test_error_envelope_and_unknown_state_fail_closed(self):
        self.transport.query('terminal','get_workspace_info',{})
        self.call.side_effect=lambda *args:{'structuredContent':{'tester_status':'unknown'}}
        with self.assertRaises(ValueError):self.transport.monitor('old')
        self.assertTrue(self.transport.blocked)
        self.call.side_effect=lambda *args:{'isError':True,'content':[]}
        with self.assertRaises(RuntimeError):self.transport.query('terminal','get_workspace_info',{})

    def test_reconciliation_is_observation_without_lock_or_attempt_mutation(self):
        self.transport.query('terminal','get_workspace_info',{})
        result=self.transport.reconcile('old')
        self.assertFalse(result['locks_released']);self.assertFalse(result['attempts_changed'])
        self.assertEqual(result['operation'],Operation.RECONCILIATION.value)
        audit=self.transport.audit;audit.clear();self.assertEqual(len(self.transport.audit),2)

    def test_preparation_only_returns_arguments(self):
        config=BacktestConfig(r'C:\SYNTHETIC\MQL5\Experts\safe.ex5','PETR4','M5','2026-11-01','2026-11-02')
        result=self.transport.prepare_offline(config)
        self.assertTrue(result['simulation_only']);self.assertFalse(result['arguments']['optimization'])
        self.call.assert_not_called()

    def test_invalid_query_arguments_are_not_forwarded(self):
        for server,name,args in (('terminal','get_workspace_info',{'path':'bad'}),
                                 ('terminal','tester_get_status',{'run_id':''}),
                                 ('terminal','get_marketwatch_symbols',{'limit':True})):
            with self.assertRaises(ValueError):self.transport.query(server,name,args)
        self.call.assert_not_called()

    def test_probe_identity_and_idle_snapshot_are_required_but_never_enable_execution(self):
        w=dict(workspace={'mql5_folder':r'C:\SYNTHETIC\MQL5'},compiler={'compiler_mql5_build':6230})
        a=dict(account={'server':'Rico-DEMO','type':'demo'},terminal={'build':6230,'program_name':'Rico - MetaTrader 5','server_connected':True})
        agents=dict(use_local=True,use_remote=False,use_cloud=False,visible_status='ready')
        c=dict(metatester_processes=0,project_locks=0,shared_terminal_locks=0)
        def probe():return assess_probe_observations(w,w,a,{'tester_status':'stopped'},agents,c,expected_mql5=r'C:\SYNTHETIC\MQL5',expected_build=6230)
        self.assertTrue(probe()['query_homologation_ready']);self.assertFalse(probe()['live_execution_enabled'])
        a['account']['type']='real'
        self.assertFalse(probe()['query_homologation_ready'])


class PersistentRecoveryTests(unittest.TestCase):
    setUp=prior.IntegrationTests.setUp
    authorization=prior.IntegrationTests.authorization
    adapter=prior.IntegrationTests.adapter
    run_fake=prior.IntegrationTests.run_fake

    def inspect(self):return inspect_recovery(self.controller.root,self.batch)

    def test_read_only_reconstruction_is_idempotent(self):
        self.run_fake(self.adapter())
        before={p:p.read_bytes() for p in self.controller.root.rglob('*') if p.is_file()}
        a=self.inspect();b=self.inspect()
        self.assertEqual(a,b);self.assertEqual(a['classification'],'requires_fresh_preflight')
        self.assertEqual(len(a['attempts']),2);self.assertFalse(a['automatic_restart'])
        self.assertEqual(before,{p:p.read_bytes() for p in self.controller.root.rglob('*') if p.is_file()})

    def test_lost_or_late_start_response_keeps_attempt_and_locks(self):
        for fault in ('start_response_lost','delayed_response'):
            self.controller=IntegrationBatchController(self.root/('ledger-'+fault));self.controller.plan(self.plan)
            a=self.adapter(fault,name='fake-'+fault);s=self.run_fake(a)
            self.assertTrue(s['integration_blocked']);self.assertEqual(a.inspect()['start_calls'],1)
            self.assertEqual(self.inspect()['classification'],'blocked_ambiguous')
            with self.assertRaises(BatchBlocked):self.run_fake(a)
            self.assertTrue(list(a.sandbox.rglob('*.lock')))

    def test_reservation_transaction_failure_blocks_without_inventing_attempt(self):
        a=self.adapter('reservation_failure');s=self.run_fake(a)
        self.assertTrue(s['integration_blocked']);self.assertEqual(s['runs']['petr4-first']['attempts'],[])
        self.assertEqual(a.inspect()['start_calls'],0)
        self.assertTrue(self.inspect()['manual_review_required'])
        with self.assertRaises(BatchBlocked):self.run_fake(a)
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',a)

    def test_interruption_after_durable_reservation_keeps_unique_identity(self):
        a=self.adapter('reservation_interrupted')
        with self.assertRaises(SystemExit):self.run_fake(a)
        report=self.inspect();self.assertEqual(report['classification'],'blocked_ambiguous')
        self.assertEqual(len(report['attempts']),1);self.assertEqual(a.inspect()['start_calls'],0)
        attempt=self.controller.status(self.batch)['runs']['petr4-first']['attempts'][0]
        self.assertEqual(attempt['attempt_id'],attempt['request_sha256'])
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',a)

    def test_computer_restart_reopens_state_without_starting(self):
        a=self.adapter('computer_restarted')
        with self.assertRaises(SystemExit):self.run_fake(a)
        ledger=self.controller.root
        self.controller=IntegrationBatchController(ledger)
        reopened=FakeTesterAdapter(a.sandbox,reopen=True)
        self.assertEqual(self.inspect()['classification'],'blocked_ambiguous')
        with self.assertRaises(BatchBlocked):self.run_fake(reopened)
        self.assertEqual(reopened.inspect()['start_calls'],1)

    def test_report_collection_failure_is_failed_not_completed(self):
        a=self.adapter('report_failure');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertEqual(a.inspect()['status'],'stopped')
        self.assertNotIn('integration_consolidation',s)
        self.assertEqual(self.inspect()['classification'],'requires_fresh_preflight')

    def test_controller_tester_divergence_never_stops_someone_else(self):
        a=self.adapter('state_divergence');s=self.run_fake(a)
        self.assertTrue(s['integration_blocked'])
        self.assertFalse(any(n=='tester_stop' for n,_ in a.calls))
        a.finish_simulated_run()
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',a)

    def test_reconciliation_is_idempotent_without_additional_events(self):
        a=self.adapter('unknown_final');self.run_fake(a);a.finish_simulated_run()
        first=self.controller.reconcile_integration(self.batch,'petr4-first',a)
        count=self.inspect()['event_count']
        self.assertEqual(first,self.controller.reconcile_integration(self.batch,'petr4-first',a))
        self.assertEqual(count,self.inspect()['event_count']);self.assertEqual(a.inspect()['start_calls'],1)

    def test_cancel_is_idempotent(self):
        self.controller.cancel(self.batch);before=self.inspect()
        self.controller.cancel(self.batch);self.assertEqual(before,self.inspect())

    def test_missing_database_never_creates_files(self):
        target=self.root/'missing'
        self.assertEqual(inspect_recovery(target,self.batch)['classification'],'blocked_incomplete')
        self.assertFalse(target.exists())

    def test_incomplete_or_divergent_persistent_state_is_blocked(self):
        self.run_fake(self.adapter('unknown_final'))
        with closing(sqlite3.connect(self.controller.root/'control.sqlite')) as db:
            db.execute('UPDATE batches SET state=? WHERE id=?',('{incomplete',self.batch))
            db.commit()
        report=self.inspect();self.assertEqual(report['classification'],'blocked_incomplete')
        self.assertTrue(report['manual_review_required']);self.assertFalse(report['locks_released'])

    def test_old_33b_request_hash_reconstructs_attempt_without_migration(self):
        self.run_fake(self.adapter())
        import json
        with closing(sqlite3.connect(self.controller.root/'control.sqlite')) as db:
            for seq,encoded in db.execute('SELECT seq,state FROM events').fetchall():
                state=json.loads(encoded)
                for run in state['runs'].values():
                    for a in run['attempts']:a.pop('attempt_id',None)
                db.execute('UPDATE events SET state=? WHERE seq=?',(json.dumps(state),seq))
            last=db.execute('SELECT state FROM events ORDER BY seq DESC LIMIT 1').fetchone()[0]
            db.execute('UPDATE batches SET state=?',(last,));db.commit()
        before=(self.controller.root/'control.sqlite').read_bytes()
        self.assertEqual(len(self.inspect()['attempts']),2)
        self.assertEqual(before,(self.controller.root/'control.sqlite').read_bytes())

    def test_erased_attempt_history_is_detected_even_if_last_snapshot_matches(self):
        self.run_fake(self.adapter())
        import json
        with closing(sqlite3.connect(self.controller.root/'control.sqlite')) as db:
            seq,encoded=db.execute('SELECT seq,state FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            state=json.loads(encoded);state['runs']['petr4-first']['attempts']=[]
            text=json.dumps(state);db.execute('UPDATE events SET state=? WHERE seq=?',(text,seq))
            db.execute('UPDATE batches SET state=?',(text,));db.commit()
        self.assertEqual(self.inspect()['classification'],'blocked_incomplete')


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.scope=dict(environment='demo',symbol='PETR4',from_date='2026-11-01',to_date='2026-11-02',model='every tick')
        self.payload={'observed':100}
        self.sources={'native':dict(payload=self.payload,sha256=fingerprint(self.payload),kind='observed')}
        self.fact=dict(source='native',locator=['observed'],value=100,scope=deepcopy(self.scope),
                       observed_at='2026-11-23T12:00:00-03:00',coverage='effective',limitations=[],incompatible=False)

    def report(self,observations):return assess_readiness(self.sources,observations,scope=self.scope)

    def test_missing_information_stays_unknown(self):
        result=self.report({})
        self.assertTrue(all(v['classification']=='unknown' for v in result['checks'].values()))
        self.assertFalse(result['ready_for_execution'])

    def test_effective_scoped_observation_and_partial_metadata_are_distinct(self):
        self.assertEqual(self.report({'volume_constraints':[self.fact]})['checks']['volume_constraints']['classification'],'confirmed')
        self.fact['coverage']='metadata'
        self.assertEqual(self.report({'volume_constraints':[self.fact]})['checks']['volume_constraints']['classification'],'partially_confirmed')

    def test_demo_evidence_cannot_certify_real_conditions(self):
        self.scope['environment']='real'
        self.assertEqual(self.report({'short_permission':[self.fact]})['checks']['short_permission']['classification'],'incompatible')

    def test_zero_cost_or_margin_does_not_prove_absence(self):
        self.payload['observed']=0;self.sources['native']['sha256']=fingerprint(self.payload);self.fact['value']=0
        for field in ('commission','swap','margin_required'):
            self.assertEqual(self.report({field:[self.fact]})['checks'][field]['classification'],'partially_confirmed')

    def test_synthetic_evidence_cannot_be_operational_confirmation(self):
        self.sources['native']['kind']='synthetic'
        self.assertEqual(self.report({'history_sufficiency':[self.fact]})['checks']['history_sufficiency']['classification'],'partially_confirmed')

    def test_hash_locator_and_scope_tampering_fail_closed(self):
        self.fact['value']=101
        with self.assertRaises(ValueError):self.report({'commission':[self.fact]})
        self.fact['value']=100;self.sources['native']['sha256']='0'*64
        with self.assertRaises(ValueError):self.report({'commission':[self.fact]})

    def test_unknown_period_cannot_be_confirmed(self):
        self.scope['from_date']=None
        self.assertEqual(self.report({'tick_availability':[self.fact]})['checks']['tick_availability']['classification'],'partially_confirmed')
        self.scope.update(from_date='2026-11-03',to_date='2026-11-02')
        with self.assertRaises(ValueError):self.report({'period_integrity':[self.fact]})

    def test_conflicting_observed_values_are_incompatible(self):
        other=deepcopy(self.fact);other['source']='other';other['value']=101
        self.sources['other']=dict(payload={'observed':101},sha256=fingerprint({'observed':101}),kind='observed')
        self.assertEqual(self.report({'slippage':[self.fact,other]})['checks']['slippage']['classification'],'incompatible')


class ProposalTests(unittest.TestCase):
    def proposal(self):
        directories=sorted((ROOT/'MQL5/Experts/MT5StrategyFactory/Generated').glob('g1_*'))
        return propose_supervised_batch(directories,{p.name:('a' if i==0 else 'b' if i==1 else 'c')*64 for i,p in enumerate(directories)})

    def test_proposal_preserves_candidates_without_dates_or_authorizations(self):
        p=self.proposal();self.assertEqual(len(p['scenarios']),3)
        self.assertTrue(p['proposal_only']);self.assertFalse(p['live_execution_enabled'])
        self.assertTrue(all(v is None for v in p['periods'].values()))
        self.assertEqual(p['resources']['max_active_per_terminal'],1)
        self.assertTrue(all(s['inputs']=={} and s['max_attempts']==1 for s in p['scenarios']))
        actual=validate_proposal(read_artifact(ROOT/'config/batches/phase33c.supervised.proposal.json'))
        self.assertEqual([s['spec'] for s in p['scenarios']],[s['spec'] for s in actual['scenarios']])
        with self.assertRaises(ValueError):validate_manifest(actual)

    def test_modified_manifest_or_execution_toggle_is_rejected(self):
        for mutation in ('hash','enabled','period','parameters'):
            p=self.proposal()
            if mutation=='hash':p['scenarios'][0]['source_sha256']='0'*64
            if mutation=='enabled':p['live_execution_enabled']=True
            if mutation=='period':p['periods']['development']={'from_date':'2027-01-01'}
            if mutation=='parameters':p['scenarios'][0]['spec']['risk']['sl_percent']=2
            with self.assertRaises(ValueError):validate_proposal(p)


if __name__=='__main__':unittest.main()
