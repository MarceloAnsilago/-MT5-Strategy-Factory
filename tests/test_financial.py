"""Financial fixtures and journals are SYNTHETIC; no MT5 execution here."""
import copy
import configparser
import subprocess
import sys
import tempfile
import json
from pathlib import Path
import unittest

from strategy_factory.financial import journal_statistics, validate_financial
from strategy_factory.reports import analyze_report

FIXTURE = Path(__file__).parent / 'fixtures/financial_synthetic.json'
EA = Path(__file__).resolve().parents[1] / 'MQL5/Experts/MT5StrategyFactory/Homologacao_002/MT5SF_Homologacao_002.mq5'


class FinancialTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_text(encoding='utf-8'))

    def journal(self):
        return {'records':[{'message':f'MT5SF002 STAT name={k} value={v}'}
                           for k,v in self.fixture['statistics'].items()]}

    def test_synthetic_fixture_explicit_counts_remain_distinct(self):
        result = analyze_report(self.fixture)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual([result['metrics'][k] for k in ('trades','deals','orders','positions')],[4,9,7,3])
        self.assertEqual(result['metrics']['net_profit'],150)
        self.assertEqual(result['metrics']['winning_trades'],2)
        self.assertEqual(result['metrics']['losing_trades'],1)

    def test_complete_fixture_matches_independent_native_reference_and_journal(self):
        result = validate_financial(self.fixture,journal=self.journal(),run_id=self.fixture['run_id'],
                                    journal_run_id=self.fixture['run_id'],native_reference=copy.deepcopy(self.fixture),
                                    reference_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'verified')
        self.assertTrue(all(c['status']=='match' for c in result['checks']))
        self.assertEqual(result['checks'][-1]['unclassified_trades'],1)

    def test_synthetic_html_extraction_compares_with_native_values(self):
        html = '<table>' + ''.join('<tr><td>'+label+':</td><td>'+value+'</td></tr>' for label,value in [
            ('Initial Deposit','10000.00'),('Final Balance','10150.00'),
            ('Total Net Profit','150.00'),('Gross Profit','250.00'),('Gross Loss','-100.00'),
            ('Profit Factor','2.50'),('Expected Payoff','37.50'),('Total Trades','4'),
            ('Total Deals','9'),('Total Orders','7'),('Total Positions','3'),
            ('Profit Trades (% of Total)','2 (50.00%)'),('Loss Trades (% of Total)','1 (25.00%)'),
            ('Balance Drawdown Absolute','40.00'),('Balance Drawdown Relative','1.20% (120.00)'),
            ('Equity Drawdown Absolute','60.00'),('Equity Drawdown Relative','1.80% (180.00)'),
            ('History Quality','99.90%')]) + '</table>'
        result = validate_financial(html,native_reference=self.fixture,
                     run_id=self.fixture['run_id'],reference_run_id=self.fixture['run_id'])
        comparisons = [c for c in result['checks'] if c['source']=='native_reference']
        self.assertTrue(comparisons)
        self.assertTrue(all(c['status']=='match' for c in comparisons))
        self.assertEqual(result['status'],'inconclusive') # No period breakdown in HTML.

    def test_reference_disagreement_does_not_replace_report(self):
        reference = copy.deepcopy(self.fixture)
        reference['statistics']['net_profit']=149
        result = validate_financial(self.fixture,native_reference=reference,
                     run_id=self.fixture['run_id'],reference_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'divergent')
        self.assertEqual(result['report']['metrics']['net_profit'],150)

    def test_gross_net_pf_expectancy_and_win_rate_divergences(self):
        for metric in ('net_profit','profit_factor','expected_payoff','win_rate'):
            fixture = copy.deepcopy(self.fixture)
            fixture['statistics'][metric] += 2
            result = validate_financial(fixture)
            self.assertEqual(result['status'],'divergent')
            self.assertTrue(any(c['metric']==metric and c['status']=='divergent' for c in result['checks']))

    def test_report_and_journal_diverge_without_overwriting(self):
        journal = self.journal()
        journal['records'].append({'message':'final balance 9999.00 BRL'})
        result = validate_financial(self.fixture,journal=journal,run_id=self.fixture['run_id'],journal_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'divergent')
        self.assertEqual(result['report']['metrics']['final_balance'],10150)
        self.assertIsNone(result['journal']['metrics']['final_balance'])

    def test_journal_final_balance_comparison(self):
        result = validate_financial(self.fixture,journal='final balance 10149.00 BRL',run_id=self.fixture['run_id'],journal_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'divergent')
        self.assertTrue(any(c['metric']=='final_balance' and c['status']=='divergent' for c in result['checks']))

    def test_unlinked_or_cross_run_evidence_rejected(self):
        for run,linked in ((None,None),('a','b')):
            result = validate_financial(self.fixture,journal=self.journal(),run_id=run,journal_run_id=linked)
            self.assertEqual(result['status'],'divergent')
            self.assertIsNone(result['journal'])
        result = validate_financial(self.fixture,native_reference=self.fixture,run_id='different',reference_run_id='different')
        self.assertEqual(result['status'],'divergent')

    def test_native_reference_wrong_identifier_rejected(self):
        reference = copy.deepcopy(self.fixture)
        reference['run_id']='different'
        result = validate_financial(self.fixture,native_reference=reference,
                     run_id=self.fixture['run_id'],reference_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'divergent')
        self.assertIsNone(result['native_reference'])

    def test_infinite_undefined_and_sentinel_profit_factor(self):
        for profit, expected in ((100,'infinite'),(0,'undefined')):
            for pf in ('inf',float('inf'),1.7976931348623157e308,0,None):
                result = analyze_report({'statistics':{'gross_profit':profit,'gross_loss':0,'profit_factor':pf}})
                self.assertIsNone(result['metrics']['profit_factor'])
                self.assertEqual(result['availability']['profit_factor'],expected)
                json.dumps(result,allow_nan=False)

    def test_zero_trades_not_applicable_not_zero_win_rate(self):
        result = analyze_report({'statistics':{'trades':0,'win_rate':0,'expected_payoff':0}})
        for key in ('win_rate','expected_payoff'):
            self.assertIsNone(result['metrics'][key])
            self.assertEqual(result['availability'][key],'not_applicable')

    def test_html_winners_losers_and_quality(self):
        result = analyze_report('<tr><td>Negociações com Lucro (% of total):</td><td>2 (50.00%)</td>'
             '<td>Negociações com Perda (% of total):</td><td>1 (25.00%)</td></tr>'
             '<tr><td>Qualidade do Histórico:</td><td>99.90%</td><td>Ofertas Total:</td><td>9</td></tr>')
        self.assertEqual(result['metrics']['winning_trades'],2)
        self.assertEqual(result['metrics']['losing_trades'],1)
        self.assertEqual(result['metrics']['win_rate'],50)
        self.assertEqual(result['metrics']['history_quality'],99.9)
        self.assertEqual(result['metrics']['deals'],9)

    def test_drawdown_missing_duplicate_and_multiple_percentages(self):
        for raw in ('', '<tr><td>Balance Drawdown Absolute:</td><td>5</td><td>Balance Drawdown Absolute:</td><td>6</td></tr>',
                    '<tr><td>Balance Drawdown Relative:</td><td>5% / 6%</td></tr>'):
            result = analyze_report(raw)
            self.assertIsNone(result['metrics']['balance_drawdown_absolute'])
            self.assertIsNone(result['metrics']['balance_drawdown_relative'])

    def test_dd_absolute_is_not_maximum_peak_to_trough(self):
        result = analyze_report('<tr><td>Balance Drawdown Maximal:</td><td>150 (1.5%)</td>'
                                '<td>Balance Drawdown Relative:</td><td>1.5% (150)</td></tr>')
        self.assertIsNone(result['metrics']['balance_drawdown_absolute'])
        self.assertEqual(result['metrics']['balance_drawdown_relative'],1.5)

    def test_incomplete_report_no_balance_or_count_inference(self):
        result = validate_financial({'statistics':{'initial_balance':10000,'net_profit':150,'deals':8}})
        self.assertEqual(result['status'],'inconclusive')
        for key in ('final_balance','trades','orders','positions','winning_trades','profit_factor'):
            self.assertIsNone(result['report']['metrics'][key])

    def test_explicit_incomplete_report_and_truncated_journal_not_verified(self):
        self.fixture['complete']=False
        self.assertEqual(analyze_report(self.fixture)['status'],'inconclusive')
        del self.fixture['complete']
        journal = self.journal()
        journal['truncated']=True
        result = validate_financial(self.fixture,journal=journal,run_id=self.fixture['run_id'],
                                    journal_run_id=self.fixture['run_id'])
        self.assertEqual(result['status'],'inconclusive')
        self.assertIn('journal truncado; comparacao parcial',result['issues'])

    def test_count_sign_and_domain_validation(self):
        result = analyze_report({'statistics':{'deals':1.5,'winning_trades':-1,'gross_loss':100,'gross_profit':-10}})
        for key in ('deals','winning_trades','gross_loss','gross_profit'):
            self.assertIsNone(result['metrics'][key])

    def test_marker_unavailable_and_duplicate_equal_values(self):
        result,issues = journal_statistics('MT5SF002 STAT name=profit_factor value=UNAVAILABLE\n'
               'MT5SF002 STAT name=net_profit value=12\nMT5SF002 STAT name=net_profit value=12')
        self.assertFalse(issues)
        self.assertEqual(result['metrics']['net_profit'],12)
        self.assertIsNone(result['metrics']['profit_factor'])

    def test_journal_unrelated_messages_are_not_financial_evidence(self):
        result,issues = journal_statistics('profit 99\nOTHER STAT name=net_profit value=999')
        self.assertFalse(issues)
        self.assertIsNone(result['metrics']['net_profit'])

    def test_no_mutation_of_fixture(self):
        before = copy.deepcopy(self.fixture)
        validate_financial(self.fixture)
        self.assertEqual(self.fixture,before)

    def test_synthetic_fixture_is_labelled(self):
        self.assertIn('SYNTHETIC',self.fixture['fixture_kind'])

    def test_offline_cli_creates_exclusive_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'analysis.json'
            command=[sys.executable,'-m','strategy_factory.financial',str(FIXTURE),
                     '--run-id',self.fixture['run_id'],'--output',str(target)]
            first=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stderr)
            original=target.read_bytes()
            second=subprocess.run(command,capture_output=True,text=True)
            self.assertNotEqual(second.returncode,0)
            self.assertEqual(target.read_bytes(),original)


class HomologationSafetyContracts(unittest.TestCase):
    """Static guardrails, not substitutes for authorized MQL5 behavioral validation."""
    def test_tester_and_optimization_guard_before_initialization(self):
        source = EA.read_text(encoding='utf-8')
        init = source.split('int OnInit()')[1].split('void Halt')[0]
        self.assertLess(init.index('if(!TesterOnly())'),init.index('g_trade.SetExpertMagicNumber'))
        self.assertIn('MQL_TESTER',source)
        self.assertIn('!MQLInfoInteger(MQL_OPTIMIZATION)',source)
        self.assertIn('INIT_FAILED',init)

    def test_minimum_volume_closed_bars_and_no_scaling(self):
        source = EA.read_text(encoding='utf-8')
        self.assertIn('SYMBOL_VOLUME_MIN',source)
        self.assertIn('CopyBuffer(g_fast,0,1,2,fast)',source)
        self.assertIn('PositionsTotal()!=0 || OrdersTotal()!=0',source)
        self.assertEqual(source.count('g_trade.Buy('),1)
        self.assertNotIn('g_trade.Sell(',source)
        self.assertNotIn('WebRequest(',source)

    def test_correct_drawdown_statistic_and_cleanup_has_no_orders(self):
        source = EA.read_text(encoding='utf-8')
        self.assertIn('ReadStatistic(STAT_BALANCEMIN)',source)
        self.assertIn('MathMax(0,initial-balance_min)',source)
        self.assertIn('STAT_BALANCE_DDREL_PERCENT',source)
        cleanup = source.split('void OnDeinit')[1]
        self.assertNotIn('g_trade.',cleanup)
        self.assertNotIn('OrderSend(',cleanup)

    def test_pending_scenario_has_only_tester_settings_and_local_agents(self):
        ini = configparser.ConfigParser()
        ini.read(EA.parents[4] / 'config/tester/MT5SF_Homologacao_002_phase23.ini',encoding='utf-8')
        self.assertEqual(ini.sections(),['Tester'])
        section=ini['Tester']
        for key,value in {'UseLocal':'1','UseRemote':'0','UseCloud':'0','Optimization':'0',
                          'ForwardMode':'0','ReplaceReport':'0','ShutdownTerminal':'0'}.items():
            self.assertEqual(section[key],value)
        self.assertIn('Homologacao_002',section['Expert'])


if __name__=='__main__':
    unittest.main()
