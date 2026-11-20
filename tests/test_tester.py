"""Offline tests only: all tester calls are fakes, no authenticated connection."""
from dataclasses import replace
import json
import io
from pathlib import Path
import tempfile
import hashlib
import ntpath
import unittest
from unittest.mock import patch

from strategy_factory.mcp import RicoMCP
from strategy_factory.reports import analyze_report
from strategy_factory.tester import BacktestConfig, TesterError, TesterRunner, payload, write_new


def config():
    return BacktestConfig(r'C:\lab\MQL5\Experts\safe.ex5', 'PETR4', 'M5', '2026-11-16', '2026-11-18')


class FakeMCP:
    def __init__(self, statuses=None, fail=None):
        self.calls = []
        self.statuses = list(statuses or ['completed'])
        self.fail = fail

    def __call__(self, name, args):
        self.calls.append((name, args))
        if self.fail == name:
            raise RuntimeError('sensitive exception must not be persisted')
        if name == 'get_workspace_info':
            data = {'capabilities': {'can_run_backtest': True},
                    'workspace': {'mql5_folder': r'C:\lab\MQL5'},
                    'permissions': {'read_roots': [r'C:\lab\MQL5'], 'write_roots': [r'C:\lab\MQL5']}}
        elif name == 'tester_run_backtest':
            data = {'run_id': 'fake-1'}
        elif name == 'tester_get_status':
            data = {'status': self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]}
        elif name == 'tester_get_report':
            data = {'statistics': {'net_profit': 85, 'trades': 4}}
        else:
            data = {}
        return {'structuredContent': data, 'isError': False}


class TesterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        identity = hashlib.sha256(ntpath.normcase(r'C:\lab\MQL5').encode()).hexdigest()
        self.shared_lock = Path(tempfile.gettempdir()) / 'mt5-strategy-factory-locks' / (identity + '.lock')
        self.addCleanup(lambda: self.shared_lock.unlink(missing_ok=True))

    def test_validation(self):
        for changes in ({'expert': 'relative.ex5'}, {'expert': r'C:\lab\x.mq5'},
                        {'timeframe': 'M7'}, {'symbol': 'PETR4\nLogin=x'},
                        {'from_date': '2026-11-18'}, {'deposit': float('nan')},
                        {'deposit': 0}, {'currency': 'brl'}, {'model': 'math calculations'},
                        {'spread': 10}, {'execution_delay': 600001}, {'leverage': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(config(), **changes)

    def test_config_explicit_no_optimization(self):
        args = config().prepare_arguments(r'C:\lab\MQL5\Profiles\Tester\unique.ini')
        self.assertFalse(args['optimization'])
        self.assertFalse(args['genetic'])
        self.assertEqual(args['forward_mode'], 0)
        self.assertEqual(args['from_date'], '2026-11-16T00:00:00')
        self.assertEqual(args['deposit_currency'], 'BRL')
        self.assertNotIn('spread', args)

    def test_simulation_never_calls_mcp(self):
        fake = FakeMCP()
        one = TesterRunner(self.root, fake).run(config())
        two = TesterRunner(self.root, fake).run(config())
        self.assertNotEqual(one, two)
        self.assertEqual(fake.calls, [])
        self.assertEqual(json.loads((one / 'result.json').read_text())['status'], 'simulated')

    def test_authorization_required(self):
        with self.assertRaises(PermissionError):
            TesterRunner(self.root, FakeMCP()).run(config(), simulate=False)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_prepared_config_and_inputs_are_not_overwritten(self):
        fake = FakeMCP()
        ini = r'C:\lab\MQL5\Profiles\Tester\exclusive.ini'
        inputs = r'C:\lab\MQL5\Profiles\Tester\exclusive.set'
        TesterRunner(self.root,fake).run(config(),simulate=False,authorized=True,
                                       prepared_config_path=ini,inputs_path=inputs)
        self.assertNotIn('tester_prepare_config',[n for n,_ in fake.calls])
        request = next(args for name,args in fake.calls if name=='tester_run_backtest')
        self.assertEqual(request,{'config_path':ini,'inputs_path':inputs,'wait':False})

    def test_prepared_config_outside_tester_folder_is_rejected(self):
        fake = FakeMCP()
        with self.assertRaises(TesterError):
            TesterRunner(self.root,fake).run(config(),simulate=False,authorized=True,
                         prepared_config_path=r'C:\lab\MQL5\wrong.ini')
        self.assertNotIn('tester_run_backtest',[n for n,_ in fake.calls])

    def test_prepared_config_still_requires_authorization(self):
        with self.assertRaises(PermissionError):
            TesterRunner(self.root,FakeMCP()).run(config(),simulate=False,
                         prepared_config_path=r'C:\lab\MQL5\Profiles\Tester\exclusive.ini')

    def test_success_archives_report_and_releases_lock(self):
        fake = FakeMCP(['started', 'completed'])
        directory = TesterRunner(self.root, fake, sleep=lambda _: None).run(config(), simulate=False, authorized=True)
        self.assertEqual(fake.calls[0][0], 'get_workspace_info')
        self.assertTrue((directory / 'report.json').exists())
        self.assertTrue((directory / 'analysis.json').exists())
        self.assertTrue((directory / 'financial_validation.json').exists())
        self.assertFalse((self.root / 'terminal.lock').exists())
        self.assertEqual([a for n, a in fake.calls if n == 'tester_run_backtest'][0]['wait'], False)

    def test_concurrent_lock_and_no_overwrite(self):
        lock = self.root / 'terminal.lock'
        lock.write_text('other run')
        fake = FakeMCP()
        with self.assertRaises(FileExistsError):
            TesterRunner(self.root, fake).run(config(), simulate=False, authorized=True)
        self.assertEqual(lock.read_text(), 'other run')
        self.assertEqual(fake.calls, [])
        path = self.root / 'report.json'
        write_new(path, {'original': True})
        with self.assertRaises(FileExistsError):
            write_new(path, {'replacement': True})
        self.assertEqual(json.loads(path.read_text()), {'original': True})

    def test_timeout_stops_owned_run_and_keeps_lock_if_uncertain(self):
        fake = FakeMCP(['running'])
        tick = [0]
        def sleep(seconds):
            tick[0] += seconds
        with self.assertRaises(TesterError):
            TesterRunner(self.root, fake, clock=lambda: tick[0], sleep=sleep).run(
                config(), simulate=False, authorized=True, timeout=2)
        self.assertIn('tester_stop', [n for n, _ in fake.calls])
        self.assertTrue((self.root / 'terminal.lock').exists())

    def test_unknown_status_does_not_fetch_stale_report(self):
        fake = FakeMCP(['mystery'])
        with self.assertRaises(TesterError):
            TesterRunner(self.root, fake).run(config(), simulate=False, authorized=True)
        self.assertNotIn('tester_get_report', [n for n, _ in fake.calls])

    def test_native_tester_status_field(self):
        fake = FakeMCP()
        def native(name, args):
            result = fake(name, args)
            if name == 'tester_get_status':
                data = result['structuredContent']
                data['tester_status'] = data.pop('status')
                data['run_id'] = '0'
            return result
        directory = TesterRunner(self.root, native).run(config(), simulate=False, authorized=True)
        self.assertTrue((directory / 'report.json').exists())

    def test_report_for_another_run_is_rejected_and_preserved(self):
        fake = FakeMCP()
        def wrong_report(name, args):
            if name == 'tester_get_report':
                return {'structuredContent': {'run_id':'another', 'profit':123}}
            return fake(name, args)
        with self.assertRaises(TesterError):
            TesterRunner(self.root, wrong_report).run(config(), simulate=False, authorized=True)
        self.assertTrue(next(self.root.glob('*/report.json')).exists())
        self.assertFalse(list(self.root.glob('*/analysis.json')))

    def test_other_active_run_is_never_stopped(self):
        fake = FakeMCP()
        def native(name, args):
            if name == 'tester_get_status':
                return {'structuredContent': {'tester_status':'started', 'run_id':'other'}}
            return fake(name, args)
        with self.assertRaises(TesterError):
            TesterRunner(self.root, native).run(config(), simulate=False, authorized=True)
        self.assertNotIn('tester_stop', [name for name, _ in fake.calls])
        self.assertTrue(self.shared_lock.exists())

    def test_timeout_confirmed_stop_releases_both_locks(self):
        fake = FakeMCP(['running', 'stopped'])
        tick = [0]
        def sleep(seconds):
            tick[0] += seconds
        with self.assertRaises(TesterError):
            TesterRunner(self.root, fake, clock=lambda: tick[0], sleep=sleep).run(
                config(), simulate=False, authorized=True, timeout=1)
        self.assertFalse((self.root / 'terminal.lock').exists())
        self.assertFalse(self.shared_lock.exists())
        self.assertNotIn('tester_get_report', [n for n, _ in fake.calls])

    def test_prepare_failure_is_sanitized_and_unlocks(self):
        fake = FakeMCP(fail='tester_prepare_config')
        with self.assertRaises(TesterError):
            TesterRunner(self.root, fake).run(config(), simulate=False, authorized=True)
        diagnostic = next(self.root.glob('*/failure.json')).read_text()
        self.assertNotIn('sensitive exception', diagnostic)
        self.assertFalse((self.root / 'terminal.lock').exists())

    def test_ambiguous_start_keeps_lock(self):
        with self.assertRaises(TesterError):
            TesterRunner(self.root, FakeMCP(fail='tester_run_backtest')).run(config(), simulate=False, authorized=True)
        self.assertTrue((self.root / 'terminal.lock').exists())

    def test_same_terminal_different_roots_conflict(self):
        with self.assertRaises(TesterError):
            TesterRunner(self.root / 'one', FakeMCP(fail='tester_run_backtest')).run(config(), simulate=False, authorized=True)
        second = FakeMCP()
        with self.assertRaises(TesterError):
            TesterRunner(self.root / 'two', second).run(config(), simulate=False, authorized=True)
        self.assertEqual([name for name, _ in second.calls], ['get_workspace_info'])

    def test_permissions_fail_closed(self):
        with self.assertRaises(TesterError):
            TesterRunner(self.root, FakeMCP()).run(replace(config(), expert=r'C:\elsewhere\x.ex5'), simulate=False, authorized=True)

    def test_envelope(self):
        self.assertEqual(payload({'content': [{'type': 'text', 'text': '{"run_id":"x"}'}]}), {'run_id': 'x'})
        for invalid in ({'isError': True}, {}, {'content': [{'type':'text','text':'unknown'}]}):
            with self.assertRaises(TesterError):
                payload(invalid)

    def test_http_endpoint_rejects_remote_and_credentials(self):
        for endpoint in ('https://example.com/mcp', 'http://user:pass@localhost/mcp', 'http://localhost/mcp?token=x'):
            with self.assertRaises(ValueError):
                RicoMCP(endpoint)

    def test_http_protocol_and_allowlist_offline(self):
        calls = []
        def rpc(client, method, params, notification=False):
            calls.append(method)
            return {'protocolVersion': '2025-03-26'} if method == 'initialize' else {}
        with patch.dict('os.environ', {'MT5_TERMINAL_TOKEN': 'synthetic-test-value'}), patch.object(RicoMCP, '_rpc', rpc):
            client = RicoMCP('http://127.0.0.1:22346/mcp')
            client('get_workspace_info', {})
            with self.assertRaises(PermissionError):
                client('order_send', {})
        self.assertEqual(calls, ['initialize', 'notifications/initialized', 'tools/call'])

    def test_http_json_and_sse_wire_responses_offline(self):
        class Response(io.BytesIO):
            def __init__(self, body, content_type):
                super().__init__(body)
                self.headers = {'Content-Type': content_type, 'Mcp-Session-Id': 'synthetic-session'}
        class Opener:
            def open(self, request, timeout):
                message = json.loads(request.data)
                result = {'protocolVersion': '2025-03-26'} if message['method'] == 'initialize' else {'structuredContent': {'status': 'stopped'}}
                reply = json.dumps({'jsonrpc':'2.0', 'id':message.get('id'), 'result': result}).encode()
                if message['method'] == 'tools/call':
                    return Response(b'data: ' + reply + b'\n\n', 'text/event-stream')
                return Response(reply, 'application/json')
        with patch.dict('os.environ', {'MT5_TERMINAL_TOKEN': 'synthetic-test-value'}), patch('strategy_factory.mcp.build_opener', return_value=Opener()):
            client = RicoMCP('http://127.0.0.1:22346/mcp')
            self.assertEqual(client('tester_get_status', {'run_id':'fake'})['structuredContent']['status'], 'stopped')
            self.assertEqual(client._session, 'synthetic-session')


class ReportTests(unittest.TestCase):
    def test_native_rico_profit_and_missing_statistics(self):
        native = {'run_id':'synthetic', 'generated_bars':12, 'generated_ticks':120,
                  'initial_deposit':10000, 'profit':0, 'deals':0, 'trades':0}
        result = analyze_report(native)
        self.assertEqual(result['metrics']['net_profit'], 0)
        self.assertEqual(result['metrics']['trades'], 0)
        for key in ('profit_factor', 'expected_payoff', 'win_rate', 'balance_drawdown_absolute'):
            self.assertIsNone(result['metrics'][key])
        self.assertIsNone(analyze_report({'profit':999})['metrics']['net_profit'])

    def test_historical_html_read_only(self):
        path = Path(__file__).resolve().parents[1] / 'MT5StrategyFactoryPOC/reports/EMA_EURUSD_M15_2025Q1.html'
        report = analyze_report(path)
        self.assertEqual(report['metrics']['net_profit'], -112.94)
        self.assertEqual(report['metrics']['trades'], 271)
        self.assertIsNone(report['period_results'])

    def test_localized_html_percent_and_decimal(self):
        report = analyze_report('<table><tr><td>Lucro Líquido Total:</td><td>1.234,56</td>'
                                '<td>Profit Trades (% of Total):</td><td>2 (50.00%)</td></tr>'
                                '<tr><td>Balance Drawdown Relative:</td><td>10.25% (100.00)</td></tr></table>')
        self.assertEqual(report['metrics']['net_profit'], 1234.56)
        self.assertEqual(report['metrics']['win_rate'], 50)
        self.assertEqual(report['metrics']['balance_drawdown_relative'], 10.25)

    def test_missing_unknown_duplicate_and_nonfinite(self):
        for report in ({'unknown_schema': 3}, {'statistics': {'net_profit': float('inf')}},
                       '<tr><td>Total Net Profit:</td><td>1</td><td>Total Net Profit:</td><td>2</td></tr>'):
            result = analyze_report(report)
            self.assertIsNone(result['metrics']['net_profit'])
            self.assertEqual(result['status'], 'inconclusive')

    def test_json_does_not_invent_metrics(self):
        result = analyze_report({'statistics': {'net_profit': 0, 'trades': 0}})
        self.assertEqual(result['metrics']['net_profit'], 0)
        self.assertIsNone(result['metrics']['win_rate'])
        self.assertIsNone(result['metrics']['profit_factor'])

    def test_explicit_periods_preserved_and_invalid_periods_inconclusive(self):
        result = analyze_report({'period_results': [{'period':'2026-11', 'net_profit':85, 'trades':4}]})
        self.assertEqual(result['period_results'][0]['net_profit'], 85)
        self.assertIsNone(result['period_results'][0]['win_rate'])
        result = analyze_report({'period_results': [{'period':'2026-11', 'trades':-1}]})
        self.assertIsNone(result['period_results'])


if __name__ == '__main__':
    unittest.main()
