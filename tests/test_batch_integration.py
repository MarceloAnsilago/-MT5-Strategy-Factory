"""Deterministic fake-only integration. Fixtures are never executable approvals."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_control import BatchBlocked
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.batch_safety import scenario_payload
from strategy_factory.batch_integration import IntegrationBatchController
from strategy_factory.batch_offline import OfflineBatchController
from strategy_factory.integration_policy import ResourcePolicy,AcceptanceCriteria,controls_digest,check_individual_fixture,assess_acceptance
from strategy_factory.tester_adapter import FakeTesterAdapter,OperationalTesterAdapter
from strategy_factory.tester import TesterRunner
from strategy_factory.mcp import RicoMCP

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,23,12,tzinfo=timezone.utc)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.plan=read_artifact(ROOT/'config/batches/phase33a.synthetic.json')
        budget=self.plan['manifest']['budget']
        budget.update(max_attempts_per_test=2,max_backtests=4,timeout_batch_seconds=720)
        for scenario,run in zip(self.plan['scenarios'],self.plan['manifest']['runs']):
            scenario['scenario_sha256']=fingerprint(scenario_payload(self.plan['manifest'],run,scenario['stage']))
        self.resources=ResourcePolicy(timeout_attempt_seconds=3,timeout_batch_seconds=12,
                                     reconciliation_seconds=2,max_consecutive_failures=3)
        self.criteria=AcceptanceCriteria(min_trades=2,max_equity_drawdown_percent=10,max_balance_drawdown_percent=10)
        self.controller=IntegrationBatchController(self.root/'ledger');self.controller.plan(self.plan)
        self.batch=self.plan['manifest']['batch_id']

    def authorization(self,run_id,attempt=1,**changes):
        s=next(s for s in self.plan['scenarios'] if s['run_id']==run_id)
        return dict(dict(schema_version='3.3B-1',fixture_kind='synthetic_non_executable',
            scope='simulation_individual_attempt',authorization_id='synthetic-'+run_id+'-'+str(attempt),
            plan_sha256=fingerprint(self.plan),controls_sha256=controls_digest(self.resources,self.criteria),
            scenario_sha256=s['scenario_sha256'],run_id=run_id,attempt=attempt,issued_at=NOW.isoformat(),
            expires_at=(NOW+timedelta(minutes=1)).isoformat()),**changes)

    def adapter(self,fault='completed',name='fake'):
        return FakeTesterAdapter(self.root/name,fault=fault)

    def run_fake(self,adapter,records=None,resume=None):
        records=records if records is not None else {s['run_id']:self.authorization(s['run_id']) for s in self.plan['scenarios']}
        return self.controller.simulate_integration(self.batch,adapter,records,resources=self.resources,
                                                   criteria=self.criteria,now=NOW,resume=resume)

    def test_completed_uses_individual_runner_and_consolidator(self):
        a=self.adapter()
        original=TesterRunner.run
        calls=[]
        def wrapped(runner,*args,**kwargs):
            calls.append((type(runner).__name__,kwargs));return original(runner,*args,**kwargs)
        with patch.object(TesterRunner,'run',wrapped),patch.object(RicoMCP,'__init__',side_effect=AssertionError('real MCP forbidden')),patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            state=self.run_fake(a)
        self.assertEqual(len(calls),2)
        self.assertEqual(state['status'],'simulated');self.assertFalse(state['live_execution_enabled'])
        self.assertEqual(sum(n=='tester_run_backtest' for n,_ in a.calls),2)
        collection=state['integration_consolidation']
        self.assertEqual(len(collection['runs']),2);self.assertIsNone(collection['ranking'])
        self.assertTrue(all(s['evidence_kind']=='synthetic' for s in collection['runs']))
        self.assertFalse(list((a.sandbox/'locks').glob('*.lock')))

    def test_zero_trades_is_completed_execution_not_approved_strategy(self):
        state=self.run_fake(self.adapter('zero_trades'))
        self.assertEqual(state['status'],'simulated')
        assessment=read_artifact(self.root/'ledger'/self.batch/'runs/petr4-first/attempt_1/acceptance.json')
        self.assertEqual(assessment['checks']['trades'],'not_met')
        self.assertFalse(assessment['strategy_approved'])

    def test_failure_before_start_does_not_consume_attempt(self):
        a=self.adapter('before_start');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertEqual(s['runs']['petr4-first']['attempts'],[])
        self.assertEqual(a.inspect()['start_calls'],0)

    def test_failure_after_start_consumes_only_one_synthetic_attempt(self):
        a=self.adapter('after_start');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertEqual(a.inspect()['start_calls'],1)
        self.assertEqual(s['runs']['petr4-second']['attempts'],[])
        self.assertEqual(s['runs']['petr4-first']['attempts'][0]['status'],'failed')

    def test_timeout_requests_cooperative_stop_and_confirms_stopped(self):
        a=self.adapter('timeout');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed')
        result=s['runs']['petr4-first']['attempts'][0]['result']
        self.assertTrue(result['stop_requested']);self.assertFalse(result['ambiguous'])
        self.assertEqual(a.inspect()['status'],'stopped')
        self.assertTrue(any(n=='tester_stop' for n,_ in a.calls))

    def test_explicit_stop_requested_is_not_recorded_as_success(self):
        a=self.adapter('stop_requested');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertTrue(s['runs']['petr4-first']['attempts'][0]['result']['stop_requested'])

    def test_busy_remote_hash_duplicate_and_resource_block_before_start(self):
        for fault in ('busy','remote_agent','hash_mismatch','duplicate_reservation','resource_exceeded'):
            with self.subTest(fault=fault):
                # Fresh ledgers preserve independent deterministic cases.
                self.controller=IntegrationBatchController(self.root/('ledger-'+fault));self.controller.plan(self.plan)
                a=self.adapter(fault,name='fake-'+fault)
                with self.assertRaises(BatchBlocked):self.run_fake(a)
                self.assertEqual(a.inspect()['start_calls'],0)
                self.assertEqual(self.controller.status(self.batch)['runs']['petr4-first']['attempts'],[])

    def test_missing_expired_batch_or_old_authorization_is_rejected(self):
        variants=[{}, {'petr4-first':self.authorization('petr4-first',expires_at=NOW.isoformat())},
                  {'petr4-first':{'schema_version':'1.0','scope':'strategy_tester_backtests_only'}},
                  {'petr4-first':self.authorization('petr4-first',scope='batch_execution')}]
        for index,records in enumerate(variants):
            self.controller=IntegrationBatchController(self.root/('auth-ledger-'+str(index)));self.controller.plan(self.plan)
            a=self.adapter(name='auth-fake-'+str(index))
            with self.assertRaises((ValueError,PermissionError)):self.run_fake(a,records)
            self.assertEqual(a.inspect()['start_calls'],0)

    def test_individual_identity_and_controls_hashes_are_bound(self):
        for changes in ({'plan_sha256':'0'*64},{'scenario_sha256':'0'*64},{'controls_sha256':'0'*64},
                        {'attempt':True},{'fixture_kind':'real'},{'run_id':'petr4-second'}):
            with self.assertRaises(PermissionError):
                check_individual_fixture(self.plan,dict(self.authorization('petr4-first'),**changes),run_id='petr4-first',attempt=1,
                    resources=self.resources,criteria=self.criteria,now=NOW)

    def test_unknown_final_and_transport_losses_block_without_repeat(self):
        for fault in ('unknown_final','communication_lost','terminal_closed','stop_unconfirmed'):
            self.controller=IntegrationBatchController(self.root/('ledger-'+fault));self.controller.plan(self.plan)
            a=self.adapter(fault,name='fake-'+fault);s=self.run_fake(a)
            self.assertEqual(s['status'],'interrupted');self.assertTrue(s['integration_blocked'])
            self.assertEqual(a.inspect()['start_calls'],1)
            with self.assertRaises(BatchBlocked):self.run_fake(a)
            with self.assertRaises(BatchBlocked):self.controller.reconcile_simulation(self.batch,'petr4-first',stopped=True)
            self.assertTrue(list((a.sandbox/'locks').glob('*.lock')))

    def test_verified_reconciliation_never_restarts_and_requires_fresh_attempt(self):
        a=self.adapter('unknown_final');self.run_fake(a)
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',a)
        a.finish_simulated_run()
        reopened=FakeTesterAdapter(a.sandbox,reopen=True)
        s=self.controller.reconcile_integration(self.batch,'petr4-first',reopened)
        self.assertFalse(s['integration_blocked']);self.assertEqual(reopened.inspect()['start_calls'],1)
        with self.assertRaises(BatchBlocked):self.controller.resume_plan(self.batch,{'petr4-first':1})
        resume=self.controller.resume_plan(self.batch,{'petr4-first':2,'petr4-second':1})
        records={'petr4-first':self.authorization('petr4-first',2),'petr4-second':self.authorization('petr4-second')}
        self.assertEqual(self.run_fake(reopened,records,resume)['status'],'simulated')
        self.assertEqual(reopened.inspect()['start_calls'],3)

    def test_unrelated_reconciliation_observation_is_rejected(self):
        a=self.adapter('unknown_final');self.run_fake(a)
        other=self.adapter(name='other')
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',other)

    def test_invalid_audited_result_never_reaches_success(self):
        a=self.adapter('invalid_audit');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertNotIn('integration_consolidation',s)
        self.assertEqual(s['runs']['petr4-first']['attempts'][0]['status'],'failed')

    def test_incomplete_state_cannot_be_reinitialized_or_reconciled(self):
        a=self.adapter('unknown_final');self.run_fake(a)
        state=a.sandbox/'fake_state.json';state.write_text('{incomplete')
        with self.assertRaises(ValueError):FakeTesterAdapter(a.sandbox,reopen=True)
        with self.assertRaises(ValueError):self.controller.reconcile_integration(self.batch,'petr4-first',a)
        self.assertTrue(self.controller.status(self.batch)['integration_blocked'])

    def test_python_or_codex_interruption_reopens_without_automatic_restart(self):
        for fault in ('python_interrupted','codex_interrupted'):
            ledger=self.root/('ledger-'+fault)
            self.controller=IntegrationBatchController(ledger);self.controller.plan(self.plan)
            a=self.adapter(fault,name='fake-'+fault)
            with self.assertRaises(SystemExit):self.run_fake(a)
            starts=a.inspect()['start_calls'];self.assertEqual(starts,1)
            self.controller=IntegrationBatchController(ledger)
            self.assertTrue(self.controller.status(self.batch)['integration_blocked'])
            with self.assertRaises(BatchBlocked):self.run_fake(a)
            self.assertEqual(a.inspect()['start_calls'],starts)

    def test_consumed_reservation_and_old_resume_cannot_start_again(self):
        a=self.adapter('after_start');self.run_fake(a)
        with self.assertRaises(BatchBlocked):self.controller.resume_plan(self.batch,{'petr4-first':1})
        resume=self.controller.resume_plan(self.batch,{'petr4-first':2})
        a.fault='completed'
        records={'petr4-first':self.authorization('petr4-first',2)}
        self.assertEqual(self.run_fake(a,records,resume)['status'],'paused')
        with self.assertRaises(BatchBlocked):self.run_fake(a,records,resume)
        self.assertEqual(a.inspect()['start_calls'],2)

    def test_local_agent_count_cpu_and_memory_limits_fail_closed(self):
        a=self.adapter()
        with patch.object(a,'inspect',return_value=dict(a.inspect(),local_agents=24)):
            with self.assertRaises(BatchBlocked):self.run_fake(a)
        self.assertEqual(a.inspect()['start_calls'],0)

    def test_batch_deadline_prevents_second_start(self):
        self.resources=ResourcePolicy(timeout_attempt_seconds=3,timeout_batch_seconds=3,reconciliation_seconds=2,max_consecutive_failures=3)
        a=self.adapter()
        original=a.request
        def elapsed(*args,**kwargs):
            result=original(*args,**kwargs);result['elapsed_seconds']=3;return result
        with patch.object(a,'request',side_effect=elapsed):
            with self.assertRaises(BatchBlocked):self.run_fake(a)
        self.assertEqual(a.inspect()['start_calls'],1)
        self.assertEqual(self.controller.status(self.batch)['runs']['petr4-first']['status'],'simulated')

    def test_drawdown_and_scenario_mismatch_are_not_accepted(self):
        s=self.run_fake(self.adapter());summary=deepcopy(s['integration_consolidation']['runs'][0])
        summary['parameters']['deposit']=20000
        metric=summary['metrics']['equity_drawdown_relative']
        metric.update(value=20,availability='available')
        assessment=assess_acceptance(summary,self.plan,'petr4-first',self.criteria)
        self.assertEqual(assessment['classification'],'criteria_not_met')
        self.assertEqual(assessment['checks']['scenario'],'not_met')
        self.assertEqual(assessment['checks']['equity_drawdown_relative'],'not_met')

    def test_batch_cancel_during_monitoring_requests_individual_stop(self):
        a=self.adapter();original=a._fake_call
        def cancel_after_start(name,args):
            result=original(name,args)
            if name=='tester_run_backtest':self.controller.cancel(self.batch)
            return result
        with patch.object(a,'_fake_call',side_effect=cancel_after_start):s=self.run_fake(a)
        self.assertEqual(s['status'],'failed')
        self.assertTrue(s['runs']['petr4-first']['attempts'][0]['result']['stop_requested'])
        self.assertEqual(a.inspect()['start_calls'],1)

    def test_failed_summary_cannot_be_promoted_to_completed(self):
        a=self.adapter();original=a.request
        def corrupt(*args,**kwargs):
            result=original(*args,**kwargs)
            result['summary']['execution']['status']='failed'
            return result
        with patch.object(a,'request',side_effect=corrupt):
            with self.assertRaises(ValueError):self.run_fake(a)
        state=self.controller.status(self.batch)
        self.assertEqual(state['runs']['petr4-first']['status'],'interrupted')
        self.assertNotIn('integration_consolidation',state)

    def test_legacy_dry_run_cannot_bypass_integration_reconciliation(self):
        a=self.adapter('unknown_final');self.run_fake(a)
        with self.assertRaises(BatchBlocked):self.controller.simulate(self.batch)
        self.assertEqual(a.inspect()['start_calls'],1)

    def test_phase33a_ledger_is_not_repurposed(self):
        old=self.root/'phase33a';OfflineBatchController(old).plan(self.plan)
        before={p:p.read_bytes() for p in old.rglob('*') if p.is_file()}
        with self.assertRaises(BatchBlocked):IntegrationBatchController(old)
        self.assertEqual(before,{p:p.read_bytes() for p in old.rglob('*') if p.is_file()})

    def test_reconciliation_rejects_wrong_run_without_removing_locks(self):
        a=self.adapter('unknown_final');self.run_fake(a);a.finish_simulated_run()
        state=a._read_state();state['run_id']='another-fake-run';a._persist(state)
        before={p:p.read_bytes() for p in a.sandbox.rglob('*.lock')}
        with self.assertRaises(BatchBlocked):self.controller.reconcile_integration(self.batch,'petr4-first',a)
        self.assertEqual(before,{p:p.read_bytes() for p in a.sandbox.rglob('*.lock')})

    def test_operational_entry_and_adapter_injection_are_blocked(self):
        for method in (OperationalTesterAdapter().request,self.controller.execute):
            with self.assertRaises(PermissionError):method(enabled=True,authorization={'approved':True})
        with self.assertRaises(PermissionError):self.run_fake(OperationalTesterAdapter())
        class Impostor(FakeTesterAdapter):pass
        with self.assertRaises(PermissionError):self.run_fake(Impostor(self.root/'impostor'))

    def test_existing_simulation_lock_is_preserved(self):
        lock=self.root/'ledger/simulation.lock';lock.write_text('existing synthetic owner')
        with self.assertRaises(FileExistsError):self.run_fake(self.adapter())
        self.assertEqual(lock.read_text(),'existing synthetic owner')

    def test_no_operational_lock_namespace_used_by_new_harness(self):
        with patch.object(TesterRunner,'_terminal_lock_root',side_effect=AssertionError('operational lock namespace forbidden')):
            self.assertEqual(self.run_fake(self.adapter())['status'],'simulated')

    def test_post_start_resource_overrun_stops_cooperatively(self):
        a=self.adapter('resource_after_start');s=self.run_fake(a)
        self.assertEqual(s['status'],'failed');self.assertEqual(a.inspect()['status'],'stopped')
        self.assertTrue(s['runs']['petr4-first']['attempts'][0]['result']['stop_requested'])

    def test_attempt_and_batch_limits_are_enforced(self):
        with self.assertRaises(ValueError):ResourcePolicy(max_active_per_terminal=24)
        with self.assertRaises(ValueError):ResourcePolicy(max_cpu_percent=101)
        self.resources=ResourcePolicy(timeout_attempt_seconds=181)
        with self.assertRaises(BatchBlocked):self.run_fake(self.adapter())

    def test_failure_limit_blocks_manual_resume_without_new_review(self):
        self.resources=ResourcePolicy(timeout_attempt_seconds=3,timeout_batch_seconds=12,reconciliation_seconds=2,max_consecutive_failures=1)
        a=self.adapter('after_start');self.run_fake(a)
        resume=self.controller.resume_plan(self.batch,{'petr4-first':2})
        with self.assertRaises(BatchBlocked):self.run_fake(a,{'petr4-first':self.authorization('petr4-first',2)},resume)
        self.assertEqual(a.inspect()['start_calls'],1)

    def test_acceptance_keeps_unknown_costs_margin_history_and_no_profit_approval(self):
        s=self.run_fake(self.adapter());summary=s['integration_consolidation']['runs'][0]
        assessment=assess_acceptance(summary,self.plan,'petr4-first',AcceptanceCriteria())
        self.assertEqual(assessment['classification'],'insufficient_evidence')
        self.assertEqual(assessment['checks']['margin'],'unverifiable');self.assertFalse(assessment['strategy_approved'])
        self.assertFalse(assessment['costs_complete'])
        wrong=deepcopy(summary);wrong['execution_audit']['run_id']='unrelated'
        with self.assertRaises(ValueError):assess_acceptance(wrong,self.plan,'petr4-first',self.criteria)
        with self.assertRaises(ValueError):AcceptanceCriteria(max_equity_drawdown_percent=-1)


if __name__=='__main__':unittest.main()
