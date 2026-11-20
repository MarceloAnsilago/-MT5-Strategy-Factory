"""SYNTHETIC fixtures only; summaries/comparisons cannot execute MT5."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import compare_runs, read_artifact, summarize_directory, summarize_run, write_artifact

ROOT = Path(__file__).resolve().parents[1]


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.report = read_artifact(ROOT/'tests/fixtures/financial_synthetic.json')
        self.parameters = dict(expert=r'C:\SYNTHETIC\Expert.ex5',symbol='PETR4',timeframe='M5',
            from_date='2026-11-03',to_date='2026-11-14',deposit=10000,currency='BRL',
            leverage=1,model='every tick',execution_delay=0)
        self.context = dict(terminal_build=6230,agents='local_only',
            history_fingerprint=hashlib.sha256(b'SYNTHETIC history').hexdigest(),
            costs_fingerprint=hashlib.sha256(b'SYNTHETIC costs').hexdigest())

    def summary(self, identity='synthetic-a', *, parameters=None, report=None, **kwargs):
        report = deepcopy(report or self.report)
        report['run_id'] = identity
        options = dict(parameters=parameters or self.parameters,run_id=identity,
            inputs={'InpFastPeriod':9},execution={'status':'completed'},synthetic=True,
            data_context=self.context,native_reference=deepcopy(report),reference_run_id=identity)
        options.update(kwargs)
        return summarize_run(report,**options)

    def test_schema_complete_financial_data_and_explicit_provenance(self):
        result = self.summary()
        self.assertEqual(result['schema_version'],'1.1')
        self.assertEqual(result['run_id'],'synthetic-a')
        self.assertEqual(result['evidence_kind'],'synthetic')
        self.assertEqual(result['strategy']['expert'],'Expert.ex5')
        self.assertEqual(result['metrics']['net_profit']['value'],150)
        self.assertEqual(result['metrics']['net_profit']['source'],'report')
        self.assertEqual(result['data_quality']['classification'],'complete')
        self.assertEqual(result['reconciliation']['classification'],'verified')
        self.assertFalse(result['data_quality']['profitability_assessed'])

    def test_quality_does_not_grade_profitability(self):
        losing = deepcopy(self.report)
        losing['statistics'].update(net_profit=-50,final_balance=9950,gross_profit=150,
            gross_loss=-200,profit_factor=0.75,winning_trades=1,losing_trades=3,win_rate=25,expected_payoff=-12.5)
        result = self.summary(report=losing)
        self.assertLess(result['metrics']['net_profit']['value'],0)
        self.assertEqual(result['data_quality']['classification'],'complete')
        self.assertEqual(result['reconciliation']['classification'],'verified')

    def test_missing_metrics_stay_null_and_warn(self):
        result = self.summary(report={'statistics':{'net_profit':0,'trades':0}})
        self.assertEqual(result['metrics']['net_profit']['value'],0)
        self.assertIsNone(result['metrics']['profit_factor']['value'])
        self.assertEqual(result['metrics']['win_rate']['availability'],'not_applicable')
        self.assertEqual(result['data_quality']['classification'],'partial')
        self.assertIn('metric_unavailable:profit_factor',result['warnings'])

    def test_no_external_evidence_is_not_reconciled(self):
        result = self.summary(native_reference=None,reference_run_id=None)
        self.assertEqual(result['reconciliation']['classification'],'not_reconciled')
        self.assertEqual(result['data_quality']['classification'],'complete')

    def test_divergence_preserves_candidates_and_blocks_selection(self):
        reference = deepcopy(self.report)
        reference['run_id']='synthetic-a'
        reference['statistics']['net_profit']=149
        result = self.summary(native_reference=reference)
        metric=result['metrics']['net_profit']
        self.assertIsNone(metric['value'])
        self.assertEqual(metric['availability'],'conflicting')
        self.assertEqual([c['value'] for c in metric['candidates']],[150,149])
        self.assertEqual(result['data_quality']['classification'],'invalid')
        self.assertEqual(result['reconciliation']['classification'],'divergent')

    def test_wrong_run_or_symbol_invalidates_evidence(self):
        result = summarize_run(self.report,parameters=self.parameters,run_id='wrong',execution={'status':'completed'})
        self.assertEqual(result['data_quality']['classification'],'invalid')
        self.assertTrue(all(m['value'] is None for m in result['metrics'].values()))
        report=deepcopy(self.report)
        report['symbol']='OTHER'
        self.assertEqual(self.summary(report=report)['data_quality']['classification'],'invalid')

    def test_requested_deposit_mismatch_invalidates_scenario(self):
        result=self.summary(parameters=dict(self.parameters,deposit=20000))
        self.assertEqual(result['data_quality']['classification'],'invalid')
        self.assertIn('requested_deposit_mismatch',result['warnings'])

    def test_scoped_journal_can_supply_value_with_named_source(self):
        report=deepcopy(self.report)
        del report['statistics']['final_balance']
        result=self.summary(report=report,journal='final balance 10150.00 BRL',journal_run_id='synthetic-a')
        self.assertEqual(result['metrics']['final_balance']['value'],10150)
        self.assertEqual(result['metrics']['final_balance']['source'],'journal')
        self.assertEqual(result['metrics']['final_balance']['report_availability'],'unavailable')
        self.assertEqual(result['reconciliation']['classification'],'partial')

    def test_unlinked_journal_is_never_used_as_fallback(self):
        report=deepcopy(self.report)
        del report['statistics']['final_balance']
        result=self.summary(report=report,journal='final balance 10150.00 BRL',journal_run_id='other')
        self.assertIsNone(result['metrics']['final_balance']['value'])
        self.assertEqual(result['reconciliation']['classification'],'divergent')

    def test_truncated_journal_and_explicit_incomplete_report_are_partial(self):
        report=deepcopy(self.report)
        report['complete']=False
        self.assertEqual(self.summary(report=report)['data_quality']['classification'],'partial')
        journal={'truncated':True,'records':[]}
        self.assertEqual(self.summary(journal=journal,journal_run_id='synthetic-a')['data_quality']['classification'],'partial')

    def test_native_derived_metrics_are_labelled(self):
        native=dict(run_id='synthetic-a',generated_bars=10,generated_ticks=100,
            initial_deposit=10000,profit=-50,trades=4,profit_trades=1,balance_min=9900)
        result=self.summary(report=native,native_reference=None)
        self.assertEqual(result['metrics']['balance_drawdown_absolute']['value'],100)
        self.assertEqual(result['metrics']['balance_drawdown_absolute']['availability'],'derived')
        self.assertIn('formula',result['metrics']['balance_drawdown_absolute']['candidates'][0])

    def test_simulation_and_failed_run_are_not_completed(self):
        for status in ('failed','simulated','unknown'):
            result=summarize_run(None,parameters=self.parameters,local_run_id='local-synthetic',execution={'status':status})
            self.assertIsNone(result['run_id'])
            self.assertEqual(result['execution']['status'],status)
            self.assertEqual(result['data_quality']['classification'],'unavailable')

    def test_sensitive_keys_and_nonfinite_inputs_rejected(self):
        for inputs in ({'api_token':'SYNTHETIC'}, {'nested':{}}, {'InpValue':float('inf')}):
            with self.assertRaises(ValueError):
                self.summary(inputs=inputs)

    def test_parameters_are_allowlisted_and_unknown_inputs_explicit(self):
        parameters=dict(self.parameters,token='SYNTHETIC_NOT_A_SECRET')
        result=self.summary(parameters=parameters,inputs=None)
        self.assertNotIn('token',result['parameters'])
        self.assertIn('strategy_inputs_unavailable',result['warnings'])
        self.assertEqual(result['data_quality']['classification'],'partial')

    def test_comparable_pair_has_deltas_without_ranking(self):
        a,b=self.summary('a'),self.summary('b')
        b['strategy']['inputs']['InpFastPeriod']=5
        result=compare_runs([a,b])
        self.assertEqual(result['pairs'][0]['classification'],'conditional')
        self.assertIsNone(result['pairs'][0]['delta_right_minus_left']['net_profit'])
        self.assertIsNone(result['ranking'])
        self.assertFalse(result['execution_enabled'])

    def test_different_scenarios_are_not_comparable(self):
        for key,value in (('symbol','OTHER'),('currency','USD'),('model','real ticks'),('deposit',20000),('from_date','2026-11-04')):
            with self.subTest(key=key):
                parameters=dict(self.parameters,**{key:value})
                report=deepcopy(self.report)
                if key=='deposit':
                    report['statistics'].update(initial_balance=value,final_balance=value+150)
                result=compare_runs([self.summary('a'),self.summary('b',parameters=parameters,report=report)])
                self.assertEqual(result['pairs'][0]['classification'],'not_comparable')
                self.assertTrue(all(v is None for v in result['pairs'][0]['delta_right_minus_left'].values()))

    def test_unknown_and_different_context(self):
        a,b=self.summary('a'),self.summary('b',data_context={})
        self.assertEqual(compare_runs([a,b])['pairs'][0]['classification'],'conditional')
        b=self.summary('b',data_context=dict(self.context,terminal_build=9999))
        self.assertEqual(compare_runs([a,b])['pairs'][0]['classification'],'not_comparable')
        b=self.summary('b',parameters=dict(self.parameters,timeframe=None))
        self.assertEqual(compare_runs([a,b])['pairs'][0]['classification'],'insufficient_context')

    def test_partial_and_failed_evidence_not_promoted(self):
        a=self.summary('a')
        b=self.summary('b',native_reference=None)
        self.assertEqual(compare_runs([a,b])['pairs'][0]['classification'],'conditional')
        b=self.summary('b',execution={'status':'failed'})
        self.assertEqual(compare_runs([a,b])['pairs'][0]['classification'],'excluded')

    def test_synthetic_and_observed_results_not_mixed(self):
        observed=deepcopy(self.report)
        del observed['fixture_kind']
        result=compare_runs([self.summary('a'),self.summary('b',report=observed,synthetic=False)])
        self.assertEqual(result['pairs'][0]['classification'],'not_comparable')

    def test_duplicates_and_malformed_summaries_rejected(self):
        with self.assertRaises(ValueError):
            compare_runs([self.summary('a'),self.summary('a')])
        for malformed in (None,{},dict(schema_version='2.0'),dict(schema_version='1.0',artifact_type='run_summary')):
            with self.assertRaises(ValueError):
                compare_runs([malformed])
        broken=self.summary()
        broken['metrics']['net_profit']['value']=float('nan')
        with self.assertRaises(ValueError):
            compare_runs([broken])
        broken=self.summary()
        broken['data_context']['history_fingerprint']='invalid'
        with self.assertRaises(ValueError):
            compare_runs([broken])
        broken=self.summary()
        broken['metrics']['net_profit']['value']=None
        with self.assertRaises(ValueError):
            compare_runs([broken])

    def test_empty_and_single_collections_do_not_execute(self):
        self.assertEqual(compare_runs([])['pairs'],[])
        self.assertEqual(compare_runs([self.summary()])['pairs'],[])

    def test_summary_and_comparison_do_not_mutate_sources(self):
        before=deepcopy(self.report)
        a,b=self.summary('a'),self.summary('b')
        original=deepcopy(a)
        result=compare_runs([a,b])
        result['runs'][0]['metrics']['net_profit']['value']=999
        self.assertEqual(a,original)
        self.assertEqual(self.report,before)

    def test_offline_directory_summary_and_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_artifact(root/'request.json',self.parameters)
            write_artifact(root/'report.json',self.report)
            write_artifact(root/'remote_run.json',{'run_id':self.report['run_id']})
            write_artifact(root/'result.json',{'status':'completed'})
            original=(root/'report.json').read_bytes()
            with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
                result=summarize_directory(root)
            output=root/'summary.json'
            write_artifact(output,result)
            with self.assertRaises(FileExistsError):
                write_artifact(output,result)
            self.assertEqual((root/'report.json').read_bytes(),original)

    def test_strict_json_and_mcp_envelopes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'artifact.json'
            for text in ('{"x":1,"x":2}','{"value":NaN}','{"value":1e999}','{"isError":true}'):
                path.write_text(text,encoding='utf-8')
                with self.assertRaises(ValueError):
                    read_artifact(path)
            path.write_text(json.dumps({'content':[{'type':'text','text':'{"run_id":"synthetic"}'}]}),encoding='utf-16')
            self.assertEqual(read_artifact(path),{'run_id':'synthetic'})
            output=Path(folder)/'bad.json'
            with self.assertRaises(ValueError):
                write_artifact(output,{'value':float('inf')})
            self.assertFalse(output.exists())

    def test_cli_summarize_and_compare_offline(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            write_artifact(root/'request.json',self.parameters)
            write_artifact(root/'report.json',self.report)
            write_artifact(root/'result.json',{'status':'completed'})
            summary=root/'summary.json'
            command=[sys.executable,'-m','strategy_factory.analysis','summarize',str(root),'--output',str(summary)]
            result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(read_artifact(summary)['evidence_kind'],'synthetic')
            output=root/'comparison.json'
            result=subprocess.run([sys.executable,'-m','strategy_factory.analysis','compare',str(summary),'--output',str(output)],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(read_artifact(output)['execution_enabled'])


if __name__=='__main__':
    unittest.main()
