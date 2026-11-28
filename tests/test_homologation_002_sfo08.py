"""Reference vectors and source/integration contracts; no MQL compiler or terminal."""
import configparser
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.homologation_002 import (
    MAGIC, SOURCE, SPEC_SHA256, STRATEGY_ID, TARGET, ReferenceSession, SimulatedPosition,
    assess_evidence, closed_cross, prepare_offline, render, specification, volume_allowed,
)
from strategy_factory.local_tester import LocalTesterExecutor, render_ini, validate_request
from strategy_factory.tester import BacktestConfig

PROJECT = Path(__file__).resolve().parents[1]
RUN = 'local_'+'1'*32


def evidence(*, run_id=RUN, rejected=0, trades=2, gross_loss=-5):
    stats = dict(trades=trades, deals=4 if trades else 0, net_profit=5,
                 balance_drawdown_absolute=1, equity_drawdown_absolute=2,
                 balance_drawdown_relative=1, equity_drawdown_relative=2,
                 gross_profit=10, gross_loss=gross_loss, orders=4, owned_market_deals=4,
                 profit_factor=2 if gross_loss else None)
    report = dict(run_id=run_id,strategy_id=STRATEGY_ID,symbol='EURUSD',timeframe='M5',
                  from_date='2023-11-01',to_date='2023-11-02',statistics=stats)
    journal = f'SFO08 INIT strategy={STRATEGY_ID} run={run_id} spec={SPEC_SHA256} magic={MAGIC} symbol=EURUSD timeframe=M5\n'
    for key in ('trades','deals','net_profit','orders','owned_market_deals','balance_drawdown_absolute',
                'equity_drawdown_absolute','balance_drawdown_relative','equity_drawdown_relative','profit_factor'):
        value=stats[key] if stats[key] is not None else 'UNAVAILABLE'
        journal+=f'SFO08 STAT strategy={STRATEGY_ID} run={run_id} name={key} value={value}\n'
    for i,action in enumerate(('buy','close','sell','close'),1):
        journal+=f'SFO08 ORDER strategy={STRATEGY_ID} run={run_id} action={action} sent=1 retcode=10009 deal={i} order={i}\n'
    journal+=f'SFO08 END strategy={STRATEGY_ID} run={run_id} requests=4 rejected={rejected} errors=0 buys=1 sells=1 closes=2 halted=0'
    return report,journal


class SignalAndPositionTests(unittest.TestCase):
    def test_buy_sell_and_no_cross_vectors(self):
        self.assertEqual(closed_cross((.9,1.1),(1,1)),'buy')
        self.assertEqual(closed_cross((1.1,.9),(1,1)),'sell')
        self.assertEqual(closed_cross((1,1.1),(1,1)),'buy')
        self.assertEqual(closed_cross((1,.9),(1,1)),'sell')
        for fast in ((1.1,1.2),(.9,.8),(1,1),(1.1,1)):
            self.assertIsNone(closed_cross(fast,(1,1)))

    def test_current_candle_is_not_an_input(self):
        with self.assertRaises(ValueError): closed_cross((.9,1.1,99),(1,1,0))
        for value in (float('nan'),float('inf'),0,-1,1e100):
            with self.assertRaises(ValueError):closed_cross((value,1.1),(1,1))

    def test_buy_close_deferred_sell_never_overlap_or_repeat_bar(self):
        session=ReferenceSession()
        self.assertEqual(session.tick(1,(.9,1.1),(1,1)),'buy')
        self.assertIsNone(session.tick(1,(1.1,.9),(1,1)))
        self.assertEqual(session.tick(2,(1.1,.9),(1,1)),'close')
        self.assertIsNone(session.position)
        self.assertIsNone(session.tick(2,(1.1,.9),(1,1)))
        self.assertEqual(session.tick(3,(.9,.8),(1,1)),'sell')
        self.assertEqual(session.position.side,'sell')
        self.assertEqual([e['action'] for e in session.events],['buy','close','sell'])
        self.assertEqual({e['volume'] for e in session.events},{.01})

    def test_sell_close_deferred_buy_and_cancel_invalidated_reversal(self):
        session=ReferenceSession()
        self.assertEqual(session.tick(1,(1.1,.9),(1,1)),'sell')
        self.assertEqual(session.tick(2,(.9,1.1),(1,1)),'close')
        self.assertIsNone(session.tick(3,(1,1),(1,1)))
        self.assertIsNone(session.deferred)
        self.assertEqual(session.tick(4,(.9,1.1),(1,1)),'buy')

    def test_deferred_buy_uses_next_closed_confirmation(self):
        session=ReferenceSession();session.tick(1,(1.1,.9),(1,1))
        session.tick(2,(.9,1.1),(1,1))
        self.assertEqual(session.tick(3,(1.1,1.2),(1,1)),'buy')
        self.assertEqual(session.position.side,'buy')

    def test_no_cross_no_request_and_already_consumed_bar_cannot_change_signal(self):
        session=ReferenceSession()
        self.assertIsNone(session.tick(1,(1.1,1.2),(1,1)))
        self.assertIsNone(session.tick(1,(.9,1.1),(1,1)))
        self.assertEqual(session.events,[])

    def test_single_position_and_foreign_position_guards(self):
        for state in (SimulatedPosition('buy',magic=MAGIC+1),SimulatedPosition('buy',symbol='GBPUSD'),
                      SimulatedPosition('buy',volume=.02),SimulatedPosition('unknown')):
            session=ReferenceSession();session.position=state
            self.assertIsNone(session.tick(1,(1.1,.9),(1,1)))
            self.assertTrue(session.halted);self.assertEqual(session.events,[])
        for kwargs in ({'pending':1},{'extra_positions':1}):
            session=ReferenceSession();session.tick(1,(.9,1.1),(1,1),**kwargs)
            self.assertTrue(session.halted);self.assertEqual(session.events,[])

    def test_rejections_partial_and_ambiguous_retcode_halt_without_retry(self):
        for options in ({'sent':False},{'retcode':10030},{'retcode':10010},{'retcode':10008},{'filled_volume':.005}):
            session=ReferenceSession();session.tick(1,(.9,1.1),(1,1),**options)
            self.assertTrue(session.halted)
            self.assertIsNone(session.tick(2,(.9,1.1),(1,1)))
            self.assertEqual(len(session.events),1)

    def test_rejected_close_does_not_reverse(self):
        session=ReferenceSession();session.tick(1,(.9,1.1),(1,1))
        session.tick(2,(1.1,.9),(1,1),retcode=10030)
        self.assertTrue(session.halted);self.assertIsNone(session.deferred)
        self.assertEqual(session.position.side,'buy')
        self.assertIsNone(session.tick(3,(.9,.8),(1,1)))

    def test_real_chart_real_account_optimization_forward_block(self):
        for options in ({'tester':False},{'demo':False},{'optimization':True},{'forward':True}):
            with self.assertRaises(ValueError):ReferenceSession(**options)

    def test_fixed_volume_rejects_incompatible_symbol_never_rounds_up(self):
        self.assertTrue(volume_allowed(.01,100,.01))
        self.assertTrue(volume_allowed(.001,100,.001))
        for rules in ((.1,100,.1),(.01,.005,.01),(.01,1,.03),(0,1,.01),(.01,1,0),(float('nan'),1,.01)):
            self.assertFalse(volume_allowed(*rules))
        with self.assertRaises(ValueError):ReferenceSession(minimum=.1,step=.1)


class SourceAndIntegrationTests(unittest.TestCase):
    def test_materialized_source_matches_deterministic_render_and_metadata(self):
        source,metadata=render()
        self.assertEqual(SOURCE.read_bytes(),source.encode())
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),metadata['source_sha256'])
        from strategy_factory.local_profiles import SF_O08
        self.assertEqual(metadata['compiled_sha256'], SF_O08.compiled_sha256)
        self.assertFalse(metadata['live_execution_enabled'])
        self.assertNotEqual(MAGIC,20261123002)

    def test_mql_guards_and_closed_buffer_contract(self):
        source,_=render()
        init=source.split('int OnInit()')[1].split('bool ClosedBuffer')[0]
        self.assertLess(init.index('if(!TesterOnly())'),init.index('g_fast=iMA'))
        self.assertIn('ACCOUNT_TRADE_MODE_DEMO',source)
        self.assertIn('!MQLInfoInteger(MQL_FORWARD)',source)
        self.assertIn('CopyBuffer(handle,0,1,2,values)',source)
        self.assertIn('bar<=g_last_bar',source)
        tick=source.split('void OnTick()')[1].split('double Statistic')[0]
        self.assertLess(tick.index('g_last_bar=bar'),tick.index('CloseOwned(ticket)'))
        self.assertIn('if(!g_halted) g_deferred=up ? 1 : -1',tick)
        self.assertIn('PositionSelectByTicket',source)
        self.assertIn('code!=TRADE_RETCODE_DONE',source)
        self.assertIn('g_trade.ResultVolume()',source)
        self.assertIn('SetAsyncMode(false)',source)
        for token in ('WebRequest','#import','ACCOUNT_LOGIN','ACCOUNT_NAME','SetAsyncMode(true)'):
            self.assertNotIn(token,source)
        self.assertNotIn('g_trade.',source.split('void OnDeinit')[1])

    def test_offline_package_unique_credentials_free_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory(dir=PROJECT/'artifacts') as tmp:
            root=Path(tmp)
            one=prepare_offline(root/'one');two=prepare_offline(root/'two')
            a=json.loads((one/'manifest.json').read_text());b=json.loads((two/'manifest.json').read_text())
            self.assertNotEqual(a['run_id'],b['run_id'])
            self.assertEqual(a['source_sha256'],b['source_sha256'])
            for directory in (one,two):
                manifest=json.loads((directory/'manifest.json').read_text())
                ini=configparser.ConfigParser();ini.read(directory/'tester.ini')
                self.assertNotIn('Common',ini)
                self.assertEqual(ini['Tester']['Model'],'1')
                self.assertEqual(ini['Tester']['UseCloud'],'0')
                self.assertEqual(ini['Tester']['UseRemote'],'0')
                self.assertIn('SFO08',ini['Tester']['Expert'])
                self.assertEqual((directory/manifest['inputs_file']).read_text(),'InpRunId='+manifest['run_id']+'\n')
                for name,digest in json.loads((directory/'artifact_sha256.json').read_text()).items():
                    self.assertEqual(hashlib.sha256((directory/name).read_bytes()).hexdigest(),digest)
            with self.assertRaises(FileExistsError):prepare_offline(one)

    def test_package_refuses_external_output_and_altered_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):prepare_offline(Path(tmp)/'out')
        with tempfile.TemporaryDirectory(dir=PROJECT/'artifacts') as tmp:
            original = Path.read_bytes
            def read(path):return b'tampered' if path==SOURCE else original(path)
            with patch.object(Path,'read_bytes',read):
                with self.assertRaisesRegex(ValueError,'source_integrity'):prepare_offline(Path(tmp)/'out')

    def test_sf_o07_live_allowlist_is_not_widened_by_ini_preparation(self):
        config=BacktestConfig(str(TARGET),'EURUSD','M5','2023-11-01','2023-11-02',model='m1 ohlc')
        with self.assertRaisesRegex(ValueError,'unreviewed_EA'):validate_request(config,'0'*64)
        with self.assertRaises(ValueError):render_ini(config,'local_'+'a'*32+'.htm')

    def test_homologacao_001_is_untouched(self):
        source=PROJECT/'MQL5/Experts/MT5StrategyFactory/Homologacao_001/MT5SF_Homologacao_001.mq5'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),
                         '78bd1d4b04ebe2805738081a193148df2a8bc2777820f27fc27b7a2eb3f6d22c')


class EvidenceTests(unittest.TestCase):
    def test_consistent_simulated_evidence_is_not_native_approval(self):
        result=assess_evidence(*evidence(),run_id=RUN)
        self.assertEqual(result['status'],'offline_evidence_consistent')
        self.assertFalse(result['native_homologation_approved'])
        self.assertEqual(result['metrics']['trades'],2)

    def test_zero_trades_never_passes(self):
        result=assess_evidence(*evidence(trades=0),run_id=RUN)
        self.assertIn('positive_trade_counts_required',result['issues'])

    def test_rejected_orders_and_mismatched_run_fail_closed(self):
        report,journal=evidence(rejected=1)
        self.assertIn('order_rejection_or_error',assess_evidence(report,journal,run_id=RUN)['issues'])
        report,journal=evidence()
        result=assess_evidence(report,journal.replace(RUN,'local_'+'2'*32),run_id=RUN)
        self.assertIn('telemetry_identity_mismatch',result['issues'])

    def test_missing_report_metrics_are_not_invented(self):
        report,journal=evidence();del report['statistics']['net_profit']
        result=assess_evidence(report,journal,run_id=RUN)
        self.assertIsNone(result['metrics']['net_profit'])
        self.assertIn('net_profit_report_unavailable',result['issues'])

    def test_unknown_profit_factor_remains_unknown(self):
        report,journal=evidence(gross_loss=0)
        report['statistics']['gross_profit']=5
        result=assess_evidence(report,journal,run_id=RUN)
        self.assertIsNone(result['metrics']['profit_factor'])
        self.assertIsNone(result['telemetry']['profit_factor'])
        self.assertNotIn('calculable_profit_factor_unavailable',result['issues'])

    def test_incomplete_and_duplicate_journal_do_not_pass(self):
        report,journal=evidence()
        for broken in ('',journal+'\n'+journal,journal.replace('sells=1','sells=0'),
                       journal.replace('retcode=10009','retcode=10010')):
            self.assertEqual(assess_evidence(report,broken,run_id=RUN)['status'],'inconclusive')

    def test_old_or_wrong_report_identity_is_rejected(self):
        for key,value in (('run_id','local_'+'9'*32),('strategy_id','legacy-002'),('symbol','GBPUSD'),
                          ('timeframe','M1'),('from_date','2023-10-31')):
            report,journal=evidence();report[key]=value
            self.assertIn('report_context_mismatch',assess_evidence(report,journal,run_id=RUN)['issues'])

    def test_invalid_or_nonintegral_telemetry_is_not_accepted(self):
        report,journal=evidence()
        for value in ('1.5','-1','9'*400):
            broken=journal.replace('name=orders value=4','name=orders value='+value)
            result=assess_evidence(report,broken,run_id=RUN)
            self.assertIn('invalid_stat_value',result['issues'])


class ProfileReconciliationTests(unittest.TestCase):
    def test_plan_profile_package_and_compilation_are_consistent(self):
        from strategy_factory.local_profiles import SF_O08, validate_scenario
        plan = json.loads((PROJECT/'config/tester/sf_o08_homologation.plan.json').read_text())
        self.assertEqual(plan['metadata']['compiled_sha256'], SF_O08.compiled_sha256)
        self.assertEqual(plan['metadata']['source_sha256'], SF_O08.source_sha256)
        self.assertEqual(plan['compilation']['errors'], 0)
        self.assertEqual(plan['compilation']['warnings'], 0)
        self.assertFalse(plan['native_execution_authorized'])
        self.assertEqual(plan['sf_mcp_restrict'], 'blocked')
        with tempfile.TemporaryDirectory(dir=PROJECT/'artifacts') as tmp:
            package = prepare_offline(Path(tmp)/'out')
            manifest = json.loads((package/'manifest.json').read_text())
            config = BacktestConfig(**manifest['config'])
            validate_scenario(config, SF_O08)
            self.assertEqual(config.from_date, plan['scenario']['from_date'])
            self.assertEqual(config.to_date, plan['scenario']['to_date_exclusive'])
            self.assertEqual((package/manifest['inputs_file']).read_bytes(),
                             ('InpRunId='+manifest['run_id']+'\n').encode('ascii'))
            from dataclasses import replace
            with self.assertRaisesRegex(ValueError, 'scenario_not_reviewed'):
                validate_scenario(replace(config, to_date='2023-11-15'), SF_O08)

    def test_profile_preflight_keeps_identity_and_hash_guards(self):
        from strategy_factory.local_profiles import SF_O08
        from strategy_factory.local_tester import preflight, INSTALLATION, DATA, BUILD, EXE_SHA256
        snapshot = dict(installation=str(INSTALLATION), data=str(DATA), origin_matches=True,
                        busy=False, demo_verified=True, startup_safe=True, ea_exists=True,
                        ea_sha256=SF_O08.compiled_sha256, source_sha256=SF_O08.source_sha256,
                        build=BUILD, exe_sha256=EXE_SHA256)
        self.assertIsNone(preflight(snapshot, profile=SF_O08))
        for key, value in (('installation', 'C:/other'), ('data', 'C:/other'),
                           ('origin_matches', False), ('demo_verified', False), ('busy', True),
                           ('startup_safe', False), ('ea_sha256', '0'*64),
                           ('source_sha256', '0'*64), ('build', 0), ('exe_sha256', '0'*64)):
            with self.subTest(key=key):
                self.assertIsNotNone(preflight(dict(snapshot, **{key:value}), profile=SF_O08))

    def test_stage_inputs_is_exact_run_bound_and_never_overwrites(self):
        from strategy_factory.local_process import stage_inputs
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); data = root/'dedicated'; run = root/RUN; run.mkdir()
            target = data/'MQL5/Profiles/Tester'; target.mkdir(parents=True)
            name = 'sf_o08_'+RUN[6:]+'.set'
            source = run/name
            source.write_bytes(('InpRunId='+RUN+'\n').encode('ascii'))
            with patch('strategy_factory.local_process.DATA', data):
                stage_inputs(run, data)
                self.assertEqual((target/name).read_bytes(), source.read_bytes())
                with self.assertRaises(FileExistsError): stage_inputs(run, data)
                source.write_bytes(b'InpRunId=wrong\n')
                with self.assertRaisesRegex(ValueError, 'prepared_inputs_changed'):
                    stage_inputs(run, data)
                with self.assertRaisesRegex(ValueError, 'data_directory_not_allowed'):
                    stage_inputs(run, root/'other')

    def test_profile_selection_never_grants_native_authorization(self):
        from strategy_factory.local_profiles import SF_O08, checked_profile
        from strategy_factory.local_process import NativeLocalBackend
        from strategy_factory.local_tester import LocalTesterExecutor
        self.assertIs(checked_profile(SF_O08), SF_O08)
        with patch('strategy_factory.local_process.regular_path') as disk:
            with self.assertRaises(PermissionError):
                NativeLocalBackend(profile=SF_O08)
            disk.assert_not_called()
        backend = type('UnauthorizedBackend', (), {'simulated': False, 'profile': SF_O08})()
        config = BacktestConfig(str(TARGET), 'EURUSD', 'M5', '2023-11-01',
                                '2023-11-02', currency='USD', model='m1 ohlc')
        with tempfile.TemporaryDirectory() as tmp:
            for approval in (False, None, 1, 'true'):
                with self.assertRaises(PermissionError):
                    LocalTesterExecutor(backend).run(config, state_root=Path(tmp)/'untouched',
                                                    simulate=False, authorized=approval)
            self.assertEqual(list(Path(tmp).iterdir()), [])


class NativeReportWhitespaceTests(unittest.TestCase):
    # Numeric rows only, extracted from the existing native HTML (no account data).
    # Source SHA-256: f70a7abfcb8da971ca75b9e0524b2b899f58a5eb07f43d9d1a68fa1d7f52706b
    NATIVE_DRAWDOWN_ROWS = '<table><tr><td>Lucro L\xedquido Total:</td><td>-2.82</td><td>Rebaixamento Absoluto do Saldo :</td><td>5.23</td><td>Rebaixamento Absoluto do Capital L\xedquido:</td><td>5.59</td></tr><tr><td>Lucro Bruto:</td><td>4.36</td><td>Rebaixamento M\xe1ximo do Saldo :</td><td>6.47 (0.06%)</td><td>Rebaixamento M\xe1ximo do Capital L\xedquido:</td><td>8.47 (0.08%)</td></tr><tr><td>Perda Bruta:</td><td>-7.18</td><td>Rebaixamento Relativo do Saldo :</td><td>0.06% (6.47)</td><td>Rebaixamento Relativo do Capital L\xedquido:</td><td>0.08% (8.47)</td></tr></table>'

    def test_native_balance_and_equity_absolute_and_relative_are_distinct(self):
        from strategy_factory.reports import analyze_report
        parsed = analyze_report(self.NATIVE_DRAWDOWN_ROWS)
        expected = dict(balance_drawdown_absolute=5.23, balance_drawdown_relative=.06,
                        equity_drawdown_absolute=5.59, equity_drawdown_relative=.08)
        for key, value in expected.items():
            self.assertEqual(parsed['metrics'][key], value)
        self.assertEqual(parsed['source_values']['balance_drawdown_relative'], ['0.06% (6.47)'])
        self.assertNotEqual(parsed['metrics']['balance_drawdown_absolute'], 6.47)
        self.assertIsNone(parsed['metrics']['orders'])

    def test_native_rounding_matches_without_replacing_report_precision(self):
        from strategy_factory.financial import validate_financial
        reference = {'statistics':dict(balance_drawdown_absolute=5.23,
            balance_drawdown_relative=.0646919782, equity_drawdown_absolute=5.59,
            equity_drawdown_relative=.0846756134)}
        result = validate_financial(self.NATIVE_DRAWDOWN_ROWS, run_id='offline-fixture',
            native_reference=reference, reference_run_id='offline-fixture')
        for key in reference['statistics']:
            check = next(c for c in result['checks'] if c['source']=='native_reference' and c['metric']==key)
            self.assertEqual(check['status'], 'match')
        self.assertEqual(result['report']['metrics']['balance_drawdown_relative'], .06)
        self.assertEqual(result['report']['metrics']['equity_drawdown_relative'], .08)
        self.assertIsNone(result['report']['metrics']['deals'])

    def test_label_whitespace_is_general_across_all_aliases(self):
        from strategy_factory.reports import ALIASES, normalized
        for aliases in ALIASES.values():
            for label in aliases:
                for spacing in (' ', '\t', '\u00a0'):
                    self.assertEqual(normalized(spacing+label+spacing+':'+spacing), label)

    def test_comma_decimal_duplicate_and_missing_labels_fail_closed(self):
        from strategy_factory.reports import analyze_report
        html = '<table><tr><td>Balance Drawdown Relative : </td><td>0,06% (6,47)</td></tr></table>'
        self.assertEqual(analyze_report(html)['metrics']['balance_drawdown_relative'], .06)
        self.assertIsNone(analyze_report(html+html)['metrics']['balance_drawdown_relative'])
        self.assertIsNone(analyze_report(html.replace('Relative', 'Maximal'))['metrics']['balance_drawdown_relative'])
        self.assertIsNone(analyze_report(html.replace('0,06%', '0,06% 0,08%'))['metrics']['balance_drawdown_relative'])


if __name__=='__main__': unittest.main()
