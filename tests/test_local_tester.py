"""SF-O07: no terminal, network, native inventory or production locks are used."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.local_tester import (
    BUILD, DATA, EA_SHA256, EXE_SHA256, EXPERT, INSTALLATION, SOURCE_SHA256,
    LocalTesterExecutor, evaluate, render_ini, sanitize_journal,
    InstallationLock, recover_lock, verify_run_artifacts,
)
from strategy_factory.tester import BacktestConfig

FIXTURE = Path(__file__).parent / 'fixtures/local_tester'
OLD_RUN = 'controlled_tester_9c4fa87c3c0b46d8a082b8ef69013bf3'


def config():
    return BacktestConfig(str(EXPERT), 'EURUSD', 'M5', '2023-11-01', '2023-11-02',
                          currency='USD', model='m1 ohlc')


def snapshot():
    return dict(installation=str(INSTALLATION), data=str(DATA), origin_matches=True,
                busy=False, demo_verified=True, startup_safe=True, ea_exists=True, ea_sha256=EA_SHA256,
                source_sha256=SOURCE_SHA256, build=BUILD, exe_sha256=EXE_SHA256)


class FakeBackend:
    simulated = True

    def __init__(self, root):
        self.lock_path = root / 'locks/installation.lock'
        self.before = snapshot(); self.after = snapshot()
        self.calls = 0; self.collected = None; self.quiescent = True
        self.terminal = (FIXTURE / 'terminal.txt').read_text(encoding='utf-8')
        self.tester = (FIXTURE / 'tester.txt').read_text(encoding='utf-8')
        self.report = (FIXTURE / 'report.htm').read_text(encoding='utf-8')
        self.fail = False

    def inspect(self):
        return self.after if self.calls else self.before

    def launch(self, directory, *, timeout):
        self.calls += 1
        self.terminal = self.terminal.replace(OLD_RUN, directory.name)
        if self.fail:
            raise RuntimeError('password=NEVER_PERSIST_THIS')

    def collect(self, directory):
        return dict(terminal=self.terminal, tester=self.tester, report=self.report,
                    quiescent=self.quiescent)


class LocalTesterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend(self.root)

    def run_fake(self):
        path = LocalTesterExecutor(self.backend).run(config(), state_root=self.root / 'runs')
        return path, json.loads((path / 'result.json').read_text())

    def test_preserved_evidence_hashes_and_success(self):
        manifest = json.loads((FIXTURE / 'provenance.json').read_text())
        for name, digest in manifest['sha256'].items():
            self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), digest)
        path, result = self.run_fake()
        self.assertEqual(result['status'], 'completed')
        self.assertTrue(result['simulation'])
        self.assertEqual(result['metrics']['trades'], 0)
        self.assertEqual(result['metrics']['deals'], 0)
        self.assertEqual(self.backend.calls, 1)
        self.assertFalse(self.backend.lock_path.exists())
        summary = json.loads((path / 'run_summary.json').read_text())
        self.assertTrue(summary)  # Uses the existing summary/traceability API.
        manifest = json.loads((path / 'artifact_sha256.json').read_text())
        for name, digest in manifest.items():
            self.assertEqual(hashlib.sha256((path / name).read_bytes()).hexdigest(), digest)

    def test_preflight_blocks_all_unsafe_states_without_launch(self):
        cases = [('demo_verified', False), ('startup_safe', False), ('ea_exists', False), ('ea_sha256', '0' * 64),
                 ('source_sha256', '0' * 64), ('busy', True), ('busy', None),
                 ('origin_matches', False), ('build', 6362),
                 ('exe_sha256', '0' * 64), ('installation', 'C:\\other'),
                 ('data', 'C:\\other')]
        for field, value in cases:
            with self.subTest(field=field):
                self.backend.before = dict(snapshot(), **{field: value})
                _, result = self.run_fake()
                self.assertEqual(result['status'], 'blocked')
                self.assertEqual(self.backend.calls, 0)
                self.assertFalse(self.backend.lock_path.exists())

    def test_invalid_ini_requests_rejected_before_outputs(self):
        for kwargs in (dict(symbol='EURUSD\nLogin=123'), dict(timeframe='M0'),
                       dict(from_date='2023-11-02'), dict(model='invalid'),
                       dict(expert='C:\\other\\bad.ex5')):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                c = replace(config(), **kwargs)
                LocalTesterExecutor(self.backend).run(c, state_root=self.root / 'runs')
        self.assertFalse((self.root / 'runs').exists())

    def test_caller_hash_is_not_authority(self):
        with self.assertRaises(ValueError):
            LocalTesterExecutor(self.backend).run(config(), state_root=self.root,
                                                 expected_sha256='0' * 64)

    def test_ini_has_no_credentials_and_only_local_agents(self):
        import configparser
        ini = render_ini(config(), 'local_' + 'a' * 32 + '.htm')
        parsed = configparser.ConfigParser(); parsed.read_string(ini)
        self.assertNotIn('Common', parsed)
        for section in parsed.sections():
            self.assertFalse({'login', 'password', 'server', 'token'} & set(parsed[section]))
        for key in ('Optimization', 'ForwardMode', 'UseRemote', 'UseCloud', 'Visual'):
            self.assertEqual(parsed['Tester'][key], '0')
        self.assertEqual(parsed['Tester']['Model'], '1')
        with self.assertRaises(ValueError): render_ini(config(), '../outside.htm')

    def test_missing_report_keeps_lock(self):
        self.backend.report = None
        _, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertTrue(result['lock_retained'])
        self.assertTrue(self.backend.lock_path.exists())

    def test_incomplete_journal_and_wrong_scenario(self):
        for bad in ('', self.backend.tester.replace('automatic testing finished', ''),
                    self.backend.tester.replace('2023.11.01', '2023.10.31')):
            with self.subTest(journal=bad[:20]):
                backend = FakeBackend(self.root)
                backend.lock_path = self.root / ('lock-' + str(len(bad)))
                backend.tester = bad
                path = LocalTesterExecutor(backend).run(config(), state_root=self.root / 'runs')
                self.assertEqual(json.loads((path/'result.json').read_text())['status'], 'inconclusive')

    def test_failure_classified_without_retry(self):
        self.backend.tester = 'test failed'
        _, result = self.run_fake()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.backend.calls, 1)

    def test_build_update_never_silently_passes(self):
        self.backend.after['build'] = 6362
        _, result = self.run_fake()
        self.assertEqual(result['reason'], 'unexpected_build_change')
        self.assertTrue(result['lock_retained'])

    def test_running_or_unknown_process_retains_lock(self):
        self.backend.quiescent = False
        _, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertTrue(result['lock_retained'])

    def test_process_reappearing_after_collection_retains_lock(self):
        self.backend.after['busy'] = True
        _, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertTrue(result['lock_retained'])

    def test_final_environment_divergence_is_inconclusive(self):
        for i, (field, value) in enumerate((('installation', 'C:\\other'),
                                           ('data', 'C:\\other'),
                                           ('demo_verified', False), ('origin_matches', False),
                                           ('startup_safe', False))):
            self.backend = FakeBackend(self.root)
            self.backend.lock_path = self.root / ('final-lock-' + str(i))
            self.backend.after[field] = value
            _, result = self.run_fake()
            self.assertEqual(result['reason'], 'final_identity_not_verified')
            self.assertTrue(result['lock_retained'])

    def test_launch_failure_consumes_attempt_and_hides_secrets(self):
        self.backend.fail = True
        path, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertTrue((path / 'attempt.json').exists())
        self.assertTrue(result['lock_retained'])
        self.assertNotIn('NEVER_PERSIST_THIS', (path / 'result.json').read_text())

    def test_installation_lock_spans_different_output_roots(self):
        self.backend.lock_path.parent.mkdir()
        self.backend.lock_path.write_text('other owner')
        for root in (self.root/'a', self.root/'b'):
            path = LocalTesterExecutor(self.backend).run(config(), state_root=root)
            self.assertEqual(json.loads((path/'result.json').read_text())['reason'], 'installation_locked')
        self.assertEqual(self.backend.calls, 0)
        self.assertEqual(self.backend.lock_path.read_text(), 'other owner')

    def test_default_never_invokes_native_backend(self):
        self.backend.simulated = False
        with patch.object(self.backend, 'inspect', side_effect=AssertionError('OS access')):
            with self.assertRaises(PermissionError):
                LocalTesterExecutor(self.backend).run(config(), state_root=self.root)
            with self.assertRaises(PermissionError):
                LocalTesterExecutor(self.backend).run(config(), state_root=self.root, simulate=False)

    def test_privacy_discards_network_and_raw_identity_rows(self):
        self.backend.report = self.backend.report.replace('<table', '<table', 1) + '<table><tr><td>Name:</td><td>PRIVATE_NAME</td></tr></table>'
        self.backend.terminal += '\nAA\t0\t12:00\tNetwork\tPRIVATE_NAME password=PRIVATE_PASSWORD'
        path, _ = self.run_fake()
        for f in path.iterdir():
            if f.is_file():
                self.assertNotIn(b'PRIVATE_NAME', f.read_bytes())
                self.assertNotIn(b'PRIVATE_PASSWORD', f.read_bytes())

    def test_report_identity_and_trade_count_must_match(self):
        for old, new in (('EURUSD', 'GBPUSD'), ('M5 (2023.11.01', 'M1 (2023.11.01')):
            self.backend = FakeBackend(self.root)
            self.backend.lock_path = self.root / ('lock-' + new[:3])
            self.backend.report = self.backend.report.replace(old, new)
            _, result = self.run_fake()
            self.assertEqual(result['reason'], 'report_scenario_mismatch')

    def test_trade_activity_and_missing_counts(self):
        import re
        for replacement, status in (('1', 'failed'), ('UNAVAILABLE', 'inconclusive')):
            self.backend = FakeBackend(self.root)
            self.backend.lock_path = self.root / ('counts-' + replacement)
            self.backend.report, count = re.subn(
                r'(Total de Negocia[^<]+</td>\s*<td[^>]*>\s*<b>)0(</b>)',
                lambda m: m[1] + replacement + m[2], self.backend.report)
            self.assertEqual(count, 1)
            _, result = self.run_fake()
            self.assertEqual(result['status'], status)

    def test_two_completed_tests_are_not_accepted(self):
        self.backend.tester += '\nautomatic testing finished'
        _, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')

    def test_changed_ea_during_run_is_inconclusive(self):
        self.backend.after['ea_sha256'] = 'f' * 64
        _, result = self.run_fake()
        self.assertEqual(result['reason'], 'ea_changed_during_run')

    def test_hardlinked_output_is_rejected(self):
        # Simulate filesystem metadata: the protected MXC mirror itself forbids
        # creating links. The production rejection remains unchanged.
        from types import SimpleNamespace
        original = self.root / 'original'
        original.write_text('x')
        actual_stat = Path.stat
        def linked_stat(path, *args, **kwargs):
            value = actual_stat(path, *args, **kwargs)
            if path == original:
                return SimpleNamespace(st_mode=value.st_mode, st_nlink=2,
                                       st_file_attributes=getattr(value, 'st_file_attributes', 0))
            return value
        with patch.object(Path, 'stat', linked_stat), self.assertRaises(ValueError):
            LocalTesterExecutor(self.backend).run(config(), state_root=original)

    def test_final_inspection_failure_still_preserves_captured_evidence(self):
        actual = self.backend.inspect
        def inspect():
            if self.backend.calls: raise RuntimeError('private account details')
            return actual()
        with patch.object(self.backend, 'inspect', side_effect=inspect):
            path, result = self.run_fake()
        self.assertEqual(result['status'], 'inconclusive')
        self.assertTrue(result['lock_retained'])
        self.assertTrue((path / 'report.json').is_file())
        self.assertTrue((path / 'tester.journal.txt').is_file())

    def test_old_journals_cannot_approve_new_run_id(self):
        def launch_without_rebinding(directory, *, timeout):
            self.backend.calls += 1
        with patch.object(self.backend, 'launch', side_effect=launch_without_rebinding):
            _, result = self.run_fake()
        self.assertEqual(result['reason'], 'run_identity_not_proven')
        self.assertTrue(result['lock_retained'])

    def test_guard_and_reservation_are_held_until_receipt_is_written(self):
        executor = LocalTesterExecutor(self.backend)
        finish = executor._finish
        def checked_finish(directory, config, result):
            self.assertTrue(self.backend.lock_path.exists())
            other = InstallationLock(self.backend.lock_path)
            self.assertFalse(other.enter_guard())
            return finish(directory, config, result)
        with patch.object(executor, '_finish', side_effect=checked_finish):
            directory = executor.run(config(), state_root=self.root/'runs')
        self.assertTrue(verify_run_artifacts(directory)['verified'])
        self.assertFalse(self.backend.lock_path.exists())

    def test_final_evidence_write_failure_retains_recoverable_lock(self):
        executor = LocalTesterExecutor(self.backend)
        with patch.object(executor, '_finish', side_effect=OSError('disk unavailable')):
            with self.assertRaises(OSError):
                executor.run(config(), state_root=self.root/'runs')
        directory = next((self.root/'runs').glob('local_*'))
        digest = hashlib.sha256(self.backend.lock_path.read_bytes()).hexdigest()
        self.assertTrue(recover_lock(self.backend, directory, expected_lock_sha256=digest,
                                     authorized=True).exists())


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.backend = FakeBackend(self.root)

    def retained(self):
        self.backend.report = None
        directory = LocalTesterExecutor(self.backend).run(config(), state_root=self.root / 'runs')
        digest = hashlib.sha256(self.backend.lock_path.read_bytes()).hexdigest()
        return directory, digest

    def test_recovery_requires_explicit_review_and_never_retries(self):
        directory, digest = self.retained()
        before = (directory / 'result.json').read_bytes()
        with self.assertRaises(PermissionError):
            recover_lock(self.backend, directory, expected_lock_sha256=digest)
        receipt = recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
        self.assertTrue(receipt.is_file())
        self.assertFalse(self.backend.lock_path.exists())
        self.assertEqual(self.backend.calls, 1)
        self.assertEqual((directory / 'result.json').read_bytes(), before)
        self.assertEqual(verify_run_artifacts(directory)['status'], 'inconclusive')
        self.assertTrue(self.backend.lock_path.with_name(self.backend.lock_path.name+'.guard').exists())

    def test_running_terminal_blocks_recovery(self):
        directory, digest = self.retained()
        self.backend.after['busy'] = True
        with self.assertRaisesRegex(ValueError, 'environment_not_safe'):
            recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
        self.assertTrue(self.backend.lock_path.exists())
        self.assertEqual(list(directory.glob('recovery_*.json')), [])

    def test_live_executor_guard_blocks_recovery_and_other_runs(self):
        directory, digest = self.retained()
        active = InstallationLock(self.backend.lock_path)
        self.assertTrue(active.enter_guard())
        try:
            with self.assertRaisesRegex(RuntimeError, 'executor_still_active'):
                recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
            second = LocalTesterExecutor(self.backend).run(config(), state_root=self.root / 'other')
            self.assertEqual(json.loads((second/'result.json').read_text())['status'], 'blocked')
            self.assertEqual(self.backend.calls, 1)
        finally:
            active.close()

    def test_recovery_rejects_wrong_hash_or_run(self):
        directory, digest = self.retained()
        with self.assertRaisesRegex(ValueError, 'lock_hash_mismatch'):
            recover_lock(self.backend, directory, expected_lock_sha256='0'*64, authorized=True)
        other = directory.parent / ('local_'+'a'*32); other.mkdir()
        with self.assertRaisesRegex(ValueError, 'context_mismatch'):
            recover_lock(self.backend, other, expected_lock_sha256=digest, authorized=True)
        self.assertTrue(self.backend.lock_path.exists())

    def test_recovery_rejects_changed_environment(self):
        directory, digest = self.retained()
        for field, value in (('demo_verified', False), ('build', 6362),
                             ('installation', 'C:\\other'), ('ea_sha256', 'f'*64)):
            with self.subTest(field=field):
                self.backend.after = dict(snapshot(), **{field: value})
                with self.assertRaisesRegex(ValueError, 'environment_not_safe'):
                    recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
                self.assertTrue(self.backend.lock_path.exists())

    def test_tampered_input_or_evidence_keeps_reservation(self):
        directory, digest = self.retained()
        ini = directory/'tester.ini'; original = ini.read_bytes()
        ini.write_bytes(original+b'\n')
        with self.assertRaisesRegex(ValueError, 'input_integrity'):
            recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
        ini.write_bytes(original)
        (directory/'tester.journal.txt').write_text('tampered')
        with self.assertRaisesRegex(ValueError, 'evidence_integrity'):
            recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
        self.assertTrue(self.backend.lock_path.exists())

    def test_crash_before_final_result_can_be_abandoned_explicitly(self):
        with patch.object(self.backend, 'launch', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                LocalTesterExecutor(self.backend).run(config(), state_root=self.root/'runs')
        directory = next((self.root/'runs').glob('local_*'))
        self.assertFalse((directory/'result.json').exists())
        digest = hashlib.sha256(self.backend.lock_path.read_bytes()).hexdigest()
        receipt = recover_lock(self.backend, directory, expected_lock_sha256=digest, authorized=True)
        self.assertIsNone(json.loads(receipt.read_text())['final_manifest_sha256'])
        self.assertFalse((directory/'result.json').exists())

    def test_receipts_are_unique_and_detect_independent_tampering(self):
        runner = LocalTesterExecutor(self.backend)
        one = runner.run(config(), state_root=self.root/'runs')
        self.backend = FakeBackend(self.root)
        two = LocalTesterExecutor(self.backend).run(config(), state_root=self.root/'runs')
        self.assertNotEqual(one.name, two.name)
        for directory in (one, two):
            self.assertTrue(verify_run_artifacts(directory)['verified'])
        receipt = one.parent/'receipts'/(one.name+'.json')
        data = json.loads(receipt.read_text()); data['result_sha256'] = '0'*64
        receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'independent_receipt'):
            verify_run_artifacts(one)

    def test_owner_never_deletes_replaced_lock(self):
        directory = self.root/('local_'+'b'*32); directory.mkdir()
        (directory/'tester.ini').write_text('ini'); (directory/'request.json').write_text('{}')
        lock = InstallationLock(self.backend.lock_path)
        self.assertTrue(lock.acquire(directory))
        try:
            self.backend.lock_path.write_text('replacement')
            with self.assertRaisesRegex(ValueError, 'lock_identity_changed'):
                lock.release()
            self.assertEqual(self.backend.lock_path.read_text(), 'replacement')
        finally:
            lock.close()


class NativeBackendOfflineTests(unittest.TestCase):
    """Backend policy tests with temporary files; all native OS calls are mocked."""
    def test_native_backend_refuses_default_and_direct_unauthorized_launch(self):
        from strategy_factory.local_process import NativeLocalBackend
        with self.assertRaises(PermissionError):
            NativeLocalBackend()
        b = NativeLocalBackend.__new__(NativeLocalBackend)
        with self.assertRaises(PermissionError):
            b.launch(Path('never-accessed'), timeout=1)

    def test_native_text_handles_utf16_and_windows_ini_newlines(self):
        from strategy_factory.local_process import read_text
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'tester.ini'
            p.write_bytes('[Tester]\r\nModel=1\r\n'.encode('utf-16'))
            self.assertEqual(read_text(p), '[Tester]\nModel=1\n')

    def test_preexisting_report_is_rejected_without_native_calls(self):
        from strategy_factory.local_process import require_fresh_report
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'old.htm'
            require_fresh_report(report)
            report.write_text('previous result')
            with self.assertRaisesRegex(ValueError, 'report_already_exists'):
                require_fresh_report(report)

    def test_collection_reads_only_bytes_after_saved_offset(self):
        from strategy_factory.local_process import NativeLocalBackend
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); logs=data/'Tester/logs'; logs.mkdir(parents=True)
            log=logs/'20261127.log'
            old='old completed test\n'.encode('utf-16')
            new='new journal fragment\n'.encode('utf-16le')
            log.write_bytes(old+new)
            b=NativeLocalBackend.__new__(NativeLocalBackend)
            b.data=data; b._offsets={log:len(old)}; b._account=('123','MetaQuotes-Demo')
            with patch.object(b,'_logs',return_value=iter([log])), \
                 patch.object(b,'_busy',return_value=False), \
                 patch.object(b,'_identity',return_value=b._account):
                captured=b.collect(data/'local_test')
            self.assertEqual(captured['tester'],'new journal fragment\n')
            self.assertEqual(captured['journal_ranges'][0]['offset'],len(old))
            self.assertEqual(captured['journal_ranges'][0]['sha256'],hashlib.sha256(new).hexdigest())

    def test_demo_attestation_rejects_real_server_or_different_identity(self):
        from strategy_factory.local_process import NativeLocalBackend
        from datetime import datetime
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp); (data / 'logs').mkdir()
            now = datetime.now()
            (data / 'logs' / (now.strftime('%Y%m%d') + '.log')).write_text(
                "AA\t0\t" + now.strftime('%H:%M:%S.%f') + "\tNetwork\t'123': authorized on MetaQuotes-Demo\n"
                "AA\t0\t12:00\tNetwork\t'123': trading enabled, demo account\n", encoding='utf-8')
            b = NativeLocalBackend.__new__(NativeLocalBackend)
            b.data = data; b._account = None
            with patch.object(b, '_identity', return_value=('123', 'Real-Server')):
                self.assertFalse(b._demo())
            with patch.object(b, '_identity', return_value=('', 'MetaQuotes-Demo')):
                self.assertFalse(b._demo())
            with patch.object(b, '_identity', return_value=('123', 'MetaQuotes-Demo')):
                self.assertTrue(b._demo())
            with patch.object(b, '_identity', return_value=('456', 'MetaQuotes-Demo')):
                self.assertFalse(b._demo())
            with patch.object(b, '_identity', return_value=('123', 'MetaQuotes-Demo')):
                with patch('strategy_factory.local_process.time.time', return_value=now.timestamp()+901):
                    self.assertFalse(b._demo())

    def test_native_inventory_commands_are_fixed_and_do_not_terminate(self):
        from strategy_factory.local_process import NativeLocalBackend
        b = NativeLocalBackend.__new__(NativeLocalBackend)
        with patch.object(b, '_powershell', return_value='1') as call:
            self.assertTrue(b._busy())
        command = call.call_args.args[0]
        self.assertIn(str(INSTALLATION), command)
        self.assertNotIn('Stop-Process', command)
        self.assertNotIn('Rico', command)


if __name__ == '__main__':
    unittest.main()
