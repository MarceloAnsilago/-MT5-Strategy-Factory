"""Offline contracts and fault injection; no operational authorization is issued."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact, summarize_run
from strategy_factory.batch_control import BatchController, BatchBlocked, check_transition, RUN_TRANSITIONS, BATCH_TRANSITIONS
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.batch_safety import validate_plan, scenario_payload, CONTROLS, check_planning_authorization, execution_gate, verify_ea_files
from strategy_factory.batch_offline import OfflineBatchController
from strategy_factory.batch_consolidation import consolidate
from strategy_factory.execution_audit import attach_execution_audit

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'config/batches/phase33a.synthetic.json'
NOW=datetime(2026,11,23,tzinfo=timezone.utc)


def rehash(plan):
    for scenario,run in zip(plan['scenarios'],plan['manifest']['runs']):
        scenario['scenario_sha256']=fingerprint(scenario_payload(plan['manifest'],run,scenario['stage']))
    return plan


def planning_record(plan):
    return dict(schema_version='3.3A-1',scope='planning_only',authorization_id='synthetic',
        plan_sha256=fingerprint(plan),controls_sha256=fingerprint(CONTROLS),
        scenario_sha256=plan['scenarios'][0]['scenario_sha256'],run_id='petr4-first',attempt=1,
        issued_at=NOW.isoformat(),expires_at=(NOW+timedelta(minutes=5)).isoformat())


def summaries():
    """Documented regression values, explicitly synthetic; no raw private evidence."""
    result=[]
    params=read_artifact(EXAMPLE)['manifest']['runs'][0]['parameters']
    for label,trades,net in (('ema',6,-143),('rsi',1,-52),('trend',14,369)):
        identity='synthetic-'+label
        report=dict(fixture_kind='SYNTHETIC regression reference',statistics=dict(trades=trades,net_profit=net))
        summary=summarize_run(report,parameters=dict(params,expert='SYNTHETIC.ex5'),
                              run_id=identity,inputs={},execution={'status':'completed'},synthetic=True)
        evidence=dict(schema_version='1.0',run_id=identity,sources={'fixture':dict(payload=report,sha256=fingerprint(report))},
                      orders=None,deals=None,groups=None,exit_events=[],costs_complete=False,counts_complete=False)
        result.append(attach_execution_audit(summary,evidence))
    return result


class SafetyTests(unittest.TestCase):
    def setUp(self):
        self.plan=read_artifact(EXAMPLE)
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)

    def controller(self,retries=1):
        budget=self.plan['manifest']['budget']
        budget.update(max_attempts_per_test=retries,max_backtests=2*retries,timeout_batch_seconds=360*retries)
        rehash(self.plan)
        c=OfflineBatchController(self.root);c.plan(self.plan)
        return c,self.plan['manifest']['batch_id']

    def test_valid_contract_does_not_select_final_period(self):
        self.assertEqual(validate_plan(self.plan),self.plan)
        self.assertIsNone(self.plan['periods']['final_test'])

    def test_missing_or_incorrect_hashes(self):
        for key in ('source_sha256','compiled_sha256'):
            p=deepcopy(self.plan);p['manifest']['strategies'][0]['ea'][key]=None
            with self.assertRaises(ValueError):validate_plan(p)
        self.plan['scenarios'][0]['scenario_sha256']='0'*64
        with self.assertRaises(ValueError):validate_plan(self.plan)

    def test_parameters_controls_resources_and_stage_are_hash_bound(self):
        for mutate in (lambda p:p['manifest']['runs'][0]['parameters'].update(deposit=123),
                       lambda p:p['manifest']['budget'].update(max_artifact_bytes=2000000),
                       lambda p:p['scenarios'][0].update(stage='final_test'),
                       lambda p:p['controls'].update(execution_enabled=True)):
            p=deepcopy(self.plan);mutate(p)
            with self.assertRaises(ValueError):validate_plan(p)

    def test_duplicate_scenario_or_ea_alias_rejected(self):
        self.plan['scenarios'][1]=deepcopy(self.plan['scenarios'][0])
        with self.assertRaises(ValueError):validate_plan(self.plan)
        p=read_artifact(EXAMPLE);m=p['manifest'];m['budget']['max_strategies']=2
        alias=deepcopy(m['strategies'][0]);alias['strategy_id']='alias';m['strategies'].append(alias)
        with self.assertRaises(ValueError):validate_plan(rehash(p))

    def test_overlap_warmup_leakage_and_result_selection_rejected(self):
        for changes in ({'warmup_from':'2026-11-06'}, {'selection_basis':'selected_after_results'},
                        {'history_status':'assumed_complete'}):
            p=deepcopy(self.plan);p['periods']['out_of_sample'].update(changes)
            with self.assertRaises(ValueError):validate_plan(p)

    def test_run_cannot_escape_declared_period(self):
        self.plan['manifest']['runs'][0]['parameters']['to_date']='2026-11-08'
        with self.assertRaises(ValueError):validate_plan(rehash(self.plan))

    def test_optional_file_hash_check(self):
        binary=self.root/'ea.ex5';source=self.root/'ea.mq5'
        binary.write_bytes(b'SYNTHETIC binary');source.write_bytes(b'SYNTHETIC source')
        ea=self.plan['manifest']['strategies'][0]['ea']
        ea.update(path=str(binary),compiled_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
        rehash(self.plan);self.assertTrue(verify_ea_files(self.plan))
        source.write_bytes(b'tampered')
        with self.assertRaises(ValueError):verify_ea_files(self.plan)

    def test_explicit_state_machine_rejects_illegal_success(self):
        for graph,before,after in ((RUN_TRANSITIONS,'failed','simulated'),(BATCH_TRANSITIONS,'failed','simulated'),
                                   (RUN_TRANSITIONS,'simulated','simulating'),(RUN_TRANSITIONS,'bogus','pending')):
            with self.assertRaises(BatchBlocked):check_transition(before,after,graph)
        c,b=self.controller()
        with c._db() as db:
            _,state=c._load(db,b);state['runs']['petr4-first']['status']='simulated'
            with self.assertRaises(BatchBlocked):c._save(db,b,state)

    def test_dry_run_network_and_runner_are_unreachable(self):
        c,b=self.controller()
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')),patch('strategy_factory.tester.TesterRunner.run',side_effect=AssertionError('runner forbidden')):
            state=c.simulate(b)
        self.assertEqual(state['status'],'simulated');self.assertFalse(state['live_execution_enabled'])
        summary=read_artifact(self.root/b/'runs/petr4-first/attempt_1/run_summary.json')
        self.assertEqual(summary['schema_version'],'1.1')
        self.assertEqual(summary['batch_context']['scenario_sha256'],self.plan['scenarios'][0]['scenario_sha256'])
        self.assertEqual(summary['evidence_kind'],'simulation')
        self.assertIsNone(summary['metrics']['net_profit']['value'])

    def test_before_start_failure_is_not_success_and_stops_queue(self):
        c,b=self.controller()
        s=c.simulate(b,outcomes={'petr4-first':{'status':'failed_before_start'}})
        self.assertEqual(s['status'],'failed')
        self.assertFalse(s['runs']['petr4-first']['attempts'][0]['synthetic_start_requested'])
        self.assertEqual(s['runs']['petr4-second']['attempts'],[])

    def test_ambiguous_start_requires_reconciliation_and_new_attempt(self):
        c,b=self.controller(2)
        s=c.simulate(b,outcomes={'petr4-first':{'status':'ambiguous'}})
        self.assertEqual(s['status'],'interrupted')
        with self.assertRaises(BatchBlocked):c.resume_plan(b,{'petr4-first':2})
        with self.assertRaises(BatchBlocked):c.reconcile_simulation(b,'petr4-first',stopped=False)
        c.reconcile_simulation(b,'petr4-first',stopped=True)
        with self.assertRaises(BatchBlocked):c.resume_plan(b,{'petr4-first':1})
        resume=c.resume_plan(b,{'petr4-first':2,'petr4-second':1})
        self.assertEqual(c.simulate(b,resume=resume)['status'],'simulated')

    def test_crash_recovery_never_replays_ambiguous_attempt(self):
        c,b=self.controller(2)
        with patch.object(c,'_write',side_effect=SystemExit):
            with self.assertRaises(SystemExit):c.simulate(b)
        c.recover_interrupted(b)
        with self.assertRaises(BatchBlocked):c.resume_plan(b,{'petr4-first':2})

    def test_expired_missing_legacy_and_consumed_planning_records(self):
        record=planning_record(self.plan)
        check=lambda r,**kw:check_planning_authorization(self.plan,r,run_id='petr4-first',attempt=1,now=NOW,**kw)
        self.assertFalse(check(record)['live_execution_enabled'])
        with self.assertRaises(PermissionError):check(None)
        with self.assertRaises(ValueError):check({'schema_version':'1.0','scope':'strategy_tester_backtests_only'})
        expired=dict(record,expires_at=NOW.isoformat())
        with self.assertRaises(PermissionError):check(expired)
        with self.assertRaises(PermissionError):check(record,consumed=[('petr4-first',1)])

    def test_planning_record_cannot_authorize_other_controls_or_attempt(self):
        for changes in ({'controls_sha256':'0'*64},{'scenario_sha256':'0'*64},{'attempt':True},
                        {'scope':'execution'},{'plan_sha256':'0'*64}):
            with self.assertRaises(PermissionError):
                check_planning_authorization(self.plan,dict(planning_record(self.plan),**changes),run_id='petr4-first',attempt=1,now=NOW)

    def test_execution_is_unconditionally_disabled(self):
        c,b=self.controller()
        for gate in (execution_gate,c.execute):
            with self.assertRaises(PermissionError):gate(b,authorization=planning_record(self.plan),enabled=True)
        with self.assertRaises(PermissionError):c.authorization(b)

    def test_controller_checks_planning_scope_against_persisted_attempts(self):
        c,b=self.controller()
        record=planning_record(self.plan)
        self.assertTrue(c.check_authorization(b,record,run_id='petr4-first',attempt=1,now=NOW)['valid_for_planning'])
        c.simulate(b,outcomes={'petr4-first':{'status':'failed'}})
        with self.assertRaises(PermissionError):c.check_authorization(b,record,run_id='petr4-first',attempt=1,now=NOW)

    def test_concurrent_lock_preserved_and_no_attempt_consumed(self):
        c,b=self.controller();lock=self.root/'simulation.lock';lock.write_text('existing owner')
        with self.assertRaises(FileExistsError):c.simulate(b)
        self.assertEqual(lock.read_text(),'existing owner')
        self.assertEqual(c.status(b)['runs']['petr4-first']['attempts'],[])

    def test_historical_ledger_cannot_be_migrated(self):
        BatchController(self.root)
        before=(self.root/'control.sqlite').read_bytes()
        with self.assertRaises(BatchBlocked):OfflineBatchController(self.root)
        self.assertEqual(before,(self.root/'control.sqlite').read_bytes())

    def test_envelope_tampering_is_detected(self):
        c,b=self.controller();p=self.root/b/'safe_plan.json'
        doc=read_artifact(p);doc['periods']['final_test']=dict(doc['periods']['out_of_sample'],from_date='2026-11-16',to_date='2026-11-20',warmup_from='2026-11-16')
        p.write_text(json.dumps(doc))
        with self.assertRaises(BatchBlocked):c.simulate(b)

    def test_idempotent_plan_and_no_automatic_repeat(self):
        c,b=self.controller();self.assertEqual(c.plan(self.plan),c.status(b))
        c.simulate(b)
        with self.assertRaises(BatchBlocked):c.simulate(b)

    def test_cli_dry_run_and_validate(self):
        for command in ('validate','dry-run'):
            args=[sys.executable,'-B','-m','strategy_factory.batch_offline',command,str(EXAMPLE)]
            if command=='dry-run':args+=['--root',str(self.root)]
            result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            doc=json.loads(result.stdout)
            self.assertFalse(doc.get('execution_enabled',doc.get('live_execution_enabled')))


class ConsolidationTests(unittest.TestCase):
    def test_documented_regression_values_are_preserved_without_portfolio(self):
        items=summaries();before=deepcopy(items);report=consolidate(items)
        self.assertEqual([(r['metrics']['trades']['value'],r['reported_mt5_net_profit']['value']) for r in report['rows']],[(6,-143),(1,-52),(14,369)])
        self.assertEqual(items,before);self.assertEqual(report['runs'],before)
        self.assertIsNone(report['ranking']);self.assertIsNone(report['portfolio_total'])
        self.assertTrue(all(r['sample_status']=='small' for r in report['rows']))
        self.assertTrue(all(r['all_costs_net_profit'] is None and r['effective_margin'] is None for r in report['rows']))

    def test_costs_history_and_configuration_differences_remain_visible(self):
        items=summaries();items[1]['parameters']['to_date']='2026-11-08'
        report=consolidate(items)
        self.assertIn('different_parameter:to_date',report['pairs'][0]['reasons'])
        self.assertTrue(report['rows'][0]['unverified_costs'])
        self.assertIn('commission_zero_does_not_prove_absence_of_costs',report['warnings'])

    def test_legacy_unaudited_duplicate_and_wrong_audit_rejected(self):
        for mode in ('legacy','unaudited','duplicate','wrong_audit'):
            items=summaries()
            if mode=='legacy':items[0]['schema_version']='1.0'
            if mode=='unaudited':del items[0]['execution_audit']
            if mode=='duplicate':items[1]=deepcopy(items[0])
            if mode=='wrong_audit':items[0]['execution_audit']['run_id']='wrong'
            with self.assertRaises(ValueError):consolidate(items)

    def test_local_historical_summaries_read_only_when_available(self):
        paths=[ROOT/'runs'/p/'run_summary_1_1_audited.json' for p in (
            'phase32d_audit_20261121','phase32f_execution_fcb7f99b53c86641_attempt1',
            'phase32h_execution_a7e690b3b483dde0_attempt1')]
        if not all(p.exists() for p in paths):
            self.skipTest('private historical evidence is intentionally not distributed')
        before={p:p.read_bytes() for p in paths}
        report=consolidate(read_artifact(p) for p in paths)
        self.assertEqual([(r['metrics']['trades']['value'],r['reported_mt5_net_profit']['value']) for r in report['rows']],[(6,-143),(1,-52),(14,369)])
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_generated_sources_match_frozen_historical_hashes(self):
        hashes={
            'ff2190c4549a31aa':'4741ade1f856db724c591de8817fdc4ebb739a159f554658f4d11be52a8d0b8f',
            'fcb7f99b53c86641':'d1ccbba691a8346951e1df676ef30ca7d7cc93fdcc9133f0d8acc597408a29c0',
            'a7e690b3b483dde0':'2341c37562b7887a49309d29018827ece9bc00efa46bb730fcc6af02735d1805'}
        for candidate,expected in hashes.items():
            source=ROOT/'MQL5/Experts/MT5StrategyFactory/Generated'/('g1_'+candidate)/('MT5SF_G_'+candidate+'.mq5')
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),expected)


if __name__=='__main__':
    unittest.main()
