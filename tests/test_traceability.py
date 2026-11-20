"""All fixtures here are SYNTHETIC. No MT5 calls, backtests or account access."""
from copy import deepcopy
import hashlib
from pathlib import Path
import unittest

from strategy_factory.analysis import summarize_run,compare_runs,read_artifact
from strategy_factory.traceability import build_traceability,digest,parse_ini,parse_set

ROOT=Path(__file__).resolve().parents[1]


class TraceabilityTests(unittest.TestCase):
    def setUp(self):
        self.parameters=dict(expert=r'C:\SYNTHETIC\Example.ex5',symbol='PETR4',timeframe='M5',
            from_date='2026-11-03',to_date='2026-11-14',deposit=10000,currency='BRL',
            leverage=1,model='every tick',execution_delay=0)
        self.run_id='synthetic-trace'
        self.inputs={'InpFastPeriod':9,'InpEnabled':False,'InpName':'001'}
        messages=[
            'PETR4,M5 (SYNTHETIC-DEMO): testing of Experts\\Example.ex5 from 2026.11.03 00:00 to 2026.11.14 00:00 started with inputs:',
            '  InpFastPeriod=9','  InpEnabled=false','  InpName=001',
            'initial deposit 10000.00 BRL, leverage 1:1',
            'PETR4,M5 (SYNTHETIC-DEMO): every tick generating',
            'quality of analyzed history is 100%','cloud network mode is off',
            'agent process started on 127.0.0.1:3000','authorized (agent build 6230)',
            'PETR4: history synchronized from 2025.01.02 to 2026.11.13']
        self.journal={'truncated':False,'records_count':len(messages),'records':[{'message':m} for m in messages]}
        self.report=read_artifact(ROOT/'tests/fixtures/financial_synthetic.json')
        self.report['run_id']=self.run_id
        self.report['statistics']['history_quality']=100
        self.history_hash=hashlib.sha256(b'SYNTHETIC history').hexdigest()
        self.cost_hash=hashlib.sha256(b'SYNTHETIC costs').hexdigest()

    def trace(self,**kwargs):
        args=dict(parameters=self.parameters,inputs=self.inputs,report=self.report,
            run_id=self.run_id,journal=self.journal,journal_run_id=self.run_id)
        args.update(kwargs)
        return build_traceability(**args)

    def complete_report(self,identity=None):
        report=deepcopy(self.report)
        report['run_id']=identity or self.run_id
        report['tester_settings']=dict(self.parameters,optimization=False,forward_mode=0,
            visual=False,use_local=True,use_remote=False,use_cloud=False,terminal_build=6230)
        report['inputs']=dict(self.inputs)
        report['costs']=dict(currency='BRL',spread_model='synthetic_variable',commission_model='synthetic_none',
            swap_model='synthetic_none',fee_model='synthetic_none',configuration_sha256=self.cost_hash,
            commission_total=0,swap_total=0,fees_total=0)
        report['history']=dict(origin='SYNTHETIC',available_from='2026-11-03',available_to='2026-11-14',
            quality_percent=100,generated_bars=100,generated_ticks=1000,tick_source='generated',
            coverage_complete=True,content_sha256=self.history_hash)
        return report

    def summary(self,identity):
        report=self.complete_report(identity)
        return summarize_run(report,parameters=self.parameters,inputs=self.inputs,
            execution={'status':'completed'},run_id=identity,native_reference=deepcopy(report),
            reference_run_id=identity,synthetic=True,data_context=dict(terminal_build=6230,
            agents='local_only',history_fingerprint=self.history_hash,costs_fingerprint=self.cost_hash))

    def test_journal_confirms_inputs_and_scenario_fields(self):
        result=self.trace()
        for key in ('expert','symbol','timeframe','from_date','to_date','deposit','currency','leverage','model'):
            self.assertEqual(result['parameters'][key]['status'],'confirmed',key)
        self.assertEqual(result['inputs']['InpFastPeriod']['status'],'confirmed')
        self.assertEqual(result['inputs']['InpFastPeriod']['requested'],9)
        self.assertEqual(result['inputs']['InpFastPeriod']['confirmed'],'9')
        self.assertEqual(result['inputs']['InpEnabled']['confirmed'],'false')
        self.assertEqual(result['inputs']['InpName']['confirmed'],'001')
        self.assertEqual(result['parameters']['execution_delay']['status'],'unverifiable')

    def test_requested_snapshots_are_not_effective_evidence(self):
        result=self.trace(journal=None,tester_ini='[Tester]\nExecutionMode=0\nOptimization=0\nUseLocal=1\nUseRemote=0\nUseCloud=0',
                          inputs_set='InpFastPeriod=9||9||1||21||N')
        self.assertEqual(result['tester_settings']['optimization']['requested'],False)
        self.assertIsNone(result['tester_settings']['optimization']['confirmed'])
        self.assertEqual(result['inputs']['InpFastPeriod']['status'],'unverifiable')
        self.assertFalse(result['readiness']['inputs'])

    def test_requested_effective_mismatch_retains_both_values(self):
        result=self.trace(inputs=dict(self.inputs,InpFastPeriod=10))
        field=result['inputs']['InpFastPeriod']
        self.assertEqual(field['status'],'mismatch')
        self.assertEqual(field['requested'],10)
        self.assertEqual(field['confirmed'],'9')
        self.assertEqual(result['classification'],'divergent')

    def test_duplicate_or_multiple_input_blocks_are_not_confirmed(self):
        journal=deepcopy(self.journal)
        journal['records'].insert(2,{'message':'  InpFastPeriod=9'})
        journal['records_count']=len(journal['records'])
        self.assertEqual(self.trace(journal=journal)['inputs']['InpFastPeriod']['status'],'conflicting')
        journal['records'].append(journal['records'][0])
        journal['records_count']=len(journal['records'])
        result=self.trace(journal=journal)
        self.assertIn('multiple_input_blocks',result['warnings'])
        self.assertIsNone(result['inputs']['InpFastPeriod']['confirmed'])

    def test_unbound_or_truncated_journal_is_unverifiable(self):
        for changes in ({'journal_run_id':None},{'journal_run_id':'other'},
                        {'journal':dict(self.journal,truncated=True)},
                        {'journal':dict(self.journal,records_count=999)}):
            result=self.trace(**changes)
            self.assertEqual(result['inputs']['InpFastPeriod']['status'],'unverifiable')

    def test_outside_input_block_lines_do_not_confirm(self):
        result=self.trace(journal='  InpFastPeriod=9\n2026.11.13 MT5SF002 InpFastPeriod=9')
        self.assertIsNone(result['inputs']['InpFastPeriod']['confirmed'])
        journal='PETR4,M5 (SYNTHETIC-DEMO): started with inputs:\n  InpFastPeriod=9'
        result=self.trace(journal=journal)
        self.assertFalse(result['input_block_complete'])
        self.assertFalse(result['readiness']['inputs'])

    def test_leading_zero_string_and_boolean_are_not_numeric_aliases(self):
        result=self.trace(inputs=dict(self.inputs,InpName='1',InpEnabled=0))
        self.assertEqual(result['inputs']['InpName']['status'],'mismatch')
        self.assertEqual(result['inputs']['InpEnabled']['status'],'mismatch')

    def test_costs_absent_are_not_zero_and_snapshots_not_charges(self):
        result=self.trace(symbol_snapshot={'symbols':[{'symbol':'PETR4','swap_long':0,'swap_short':0,'volume_min':100}]})
        self.assertIsNone(result['costs']['swap_total']['confirmed'])
        self.assertEqual(result['observations']['symbol_snapshot']['values']['swap_long'],0)
        self.assertEqual(result['observations']['symbol_snapshot']['status'],'not_execution_confirmed')
        self.assertFalse(result['readiness']['cost_configuration'])

    def test_explicit_native_zero_cost_is_confirmed(self):
        result=self.trace(report=self.complete_report(),journal=None)
        self.assertEqual(result['costs']['commission_total']['confirmed'],0)
        self.assertEqual(result['costs']['commission_total']['status'],'confirmed')
        self.assertTrue(result['readiness']['cost_configuration'])
        report=self.complete_report()
        report['costs']['commission_total']=1.7976931348623157e308
        self.assertIsNone(self.trace(report=report,journal=None)['costs']['commission_total']['confirmed'])

    def test_net_gross_identity_does_not_imply_zero_commission(self):
        result=self.trace()
        self.assertEqual(self.report['statistics']['net_profit'],150)
        self.assertIsNone(result['costs']['commission_total']['confirmed'])

    def test_history_quality_and_sync_are_not_full_content_proof(self):
        result=self.trace(history_snapshot={'symbol':'PETR4','period':'M5','data_available_from':'2021-01-01','history':[{'time':'2026-11-03T10:00:00'}]})
        self.assertEqual(result['history']['quality_percent']['confirmed'],100)
        self.assertEqual(result['history']['synchronization_origin']['confirmed'],'terminal_to_tester_agent')
        self.assertEqual(result['history']['tick_source']['confirmed'],'generated')
        self.assertFalse(result['readiness']['history_content'])
        self.assertIsNone(result['history']['content_sha256']['confirmed'])
        self.assertEqual(result['observations']['history_snapshot']['values']['returned_records'],1)

    def test_local_agent_observed_does_not_prove_remote_agents_disabled(self):
        result=self.trace()
        self.assertTrue(result['tester_settings']['local_agent_observed']['confirmed'])
        self.assertFalse(result['tester_settings']['use_cloud']['confirmed'])
        self.assertIsNone(result['tester_settings']['use_remote']['confirmed'])
        self.assertEqual(result['tester_settings']['agent_build']['confirmed'],6230)
        self.assertIsNone(result['tester_settings']['terminal_build']['confirmed'])

    def test_source_hashes_and_locators_are_reproducible(self):
        before=deepcopy(self.report)
        result=self.trace()
        source=result['inputs']['InpFastPeriod']['evidence'][0]
        self.assertEqual(source['artifact_sha256'],digest(self.journal))
        self.assertIn('records[',source['locator'])
        self.assertEqual(self.report,before)
        changed=deepcopy(self.journal)
        changed['records'][1]['message']='  InpFastPeriod=10'
        self.assertNotEqual(digest(changed),digest(self.journal))

    def test_source_conflicts_not_silently_preferred(self):
        report=self.complete_report()
        report['inputs']['InpFastPeriod']=10
        self.assertEqual(self.trace(report=report)['inputs']['InpFastPeriod']['status'],'conflicting')

    def test_requested_ini_and_set_disagreements_are_visible(self):
        result=self.trace(tester_ini='[Tester]\nDeposit=20000',inputs_set='InpFastPeriod=10')
        self.assertEqual(result['classification'],'divergent')
        self.assertIn('requested_ini_disagreement:deposit',result['warnings'])
        self.assertIn('requested_set_disagreement:InpFastPeriod',result['warnings'])

    def test_sensitive_inputs_rejected_or_omitted_without_values(self):
        with self.assertRaises(ValueError):
            parse_set('api_token=SYNTHETIC_PRIVATE_VALUE')
        report=self.complete_report()
        report['inputs']['api_token']='SYNTHETIC_PRIVATE_VALUE'
        result=self.trace(report=report,journal=None)
        self.assertNotIn('api_token',result['inputs'])
        self.assertNotIn('SYNTHETIC_PRIVATE_VALUE',str(result))
        self.assertFalse(result['readiness']['inputs'])

    def test_ini_ignores_non_tester_sections(self):
        result=parse_ini('[Common]\nLogin=SYNTHETIC\n[Tester]\nDeposit=10000\nUseRemote=0')
        self.assertEqual(result,{'deposit':10000,'use_remote':False})
        with self.assertRaises(ValueError):
            parse_set('InpFast=9\nInpFast=10')

    def test_confirmed_evidence_enables_comparison(self):
        a,b=self.summary('a'),self.summary('b')
        self.assertEqual(a['traceability']['classification'],'confirmed')
        result=compare_runs([a,b])
        self.assertEqual(result['pairs'][0]['classification'],'comparable')
        self.assertEqual(result['pairs'][0]['delta_right_minus_left']['net_profit'],0)

    def test_unverified_legacy_context_cannot_enable_comparison(self):
        a,b=self.summary('a'),self.summary('b')
        for s in (a,b):
            s['schema_version']='1.0'
            del s['traceability']
        result=compare_runs([a,b])
        self.assertEqual(result['pairs'][0]['classification'],'conditional')
        self.assertIn('legacy_traceability_unavailable',result['pairs'][0]['reasons'])

    def test_parameter_mismatch_invalidates_summary_without_losing_candidates(self):
        report=self.complete_report()
        report['tester_settings']['timeframe']='M15'
        result=summarize_run(report,parameters=self.parameters,inputs=self.inputs,run_id=self.run_id,
                             execution={'status':'completed'})
        self.assertEqual(result['data_quality']['classification'],'invalid')
        self.assertEqual(result['traceability']['parameters']['timeframe']['status'],'mismatch')
        self.assertIsNone(result['metrics']['net_profit']['value'])
        self.assertTrue(result['metrics']['net_profit']['candidates'])

    def test_similar_totals_without_cost_configuration_remain_conditional(self):
        a,b=self.summary('a'),self.summary('b')
        b['traceability']['readiness']['cost_configuration']=False
        b['traceability']['costs']['configuration_sha256']['confirmed']=None
        b['traceability']['costs']['configuration_sha256']['status']='unverifiable'
        pair=compare_runs([a,b])['pairs'][0]
        self.assertEqual(pair['classification'],'conditional')
        self.assertEqual(pair['traceability_comparison']['costs']['spread_points']['classification'],'unverifiable')
        self.assertEqual(pair['traceability_comparison']['costs']['swap_total']['classification'],'same')


if __name__=='__main__':
    unittest.main()
