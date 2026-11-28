"""Dedicated native Tester orchestration; no MCP, account setup or process termination.

All OS interaction is supplied by a backend. The default API refuses real execution;
simulation backends must identify themselves explicitly. Unknown state retains the lock.
"""
from dataclasses import asdict
from datetime import date, datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import uuid

from .analysis import summarize_run, write_artifact
from .reports import analyze_report, normalized, TableCells
from .tester import BacktestConfig
from .local_profiles import HOMOLOGATION_001, checked_profile, profile_record, validate_scenario

INSTALLATION = PureWindowsPath('C:/estrategia/infra/mt5-factory')
DATA = PureWindowsPath('C:/Users/User/AppData/Roaming/MetaQuotes/Terminal/AEF1E6F57078EAB3775179FCBD94D671')
EXPERT = DATA / 'MQL5/Experts/MT5StrategyFactory/Homologacao_001/MT5SF_Homologacao_001.ex5'
EA_SHA256 = '9ed2ebeb5b6803eb4698bbf49cec643f876623bed9005b4d5278d2655b142854'
SOURCE_SHA256 = '78bd1d4b04ebe2805738081a193148df2a8bc2777820f27fc27b7a2eb3f6d22c'
BUILD = 6361
EXE_SHA256 = 'f6d0c0eb61ae90a3849b72b5459a7bbce9a51ed42d7bee5c80629738a7c98b9c'
MODELS = {'every tick': 0, 'm1 ohlc': 1, 'open prices': 2, 'real ticks': 4}


def sha(data):
    return hashlib.sha256(data).hexdigest()


class InstallationLock:
    """Durable reservation plus a nonblocking OS guard; no stale-lock deletion.

    The guard inode is never removed. A running owner holds its byte lock, so a
    recovery request cannot race a still-active executor between preflight/start.
    A crash releases the OS guard but leaves the reservation for explicit review.
    """
    def __init__(self, path):
        self.path = regular_path(path)
        self.stream = None
        self.digest = None

    def enter_guard(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        guard = regular_path(self.path.with_name(self.path.name + '.guard'))
        self.stream = guard.open('a+b')
        self.stream.seek(0, 2)
        if self.stream.tell() == 0:
            self.stream.write(b'0'); self.stream.flush()
        self.stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.stream.close(); self.stream = None
            return False
        return True

    def acquire(self, directory):
        if not self.enter_guard():
            return False
        record = {'schema_version': 1, 'run_id': directory.name,
                  'installation': str(INSTALLATION), 'data': str(DATA),
                  'token': uuid.uuid4().hex,
                  'created_at_utc': datetime.now(timezone.utc).isoformat(),
                  'inputs': {name: sha((directory / name).read_bytes())
                             for name in ('request.json', 'tester.ini', 'profile.json',
                                          'sf_o08_' + directory.name[6:] + '.set')
                             if (directory / name).exists()}}
        encoded = json.dumps(record, sort_keys=True).encode('utf-8')
        try:
            with self.path.open('xb') as stream:
                stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        except FileExistsError:
            self.close()
            return False
        except BaseException:
            self.close()
            raise
        self.digest = sha(encoded)
        return True

    def release(self):
        if self.stream is None or self.digest != sha(regular_path(self.path).read_bytes()):
            raise ValueError('lock_identity_changed')
        self.path.unlink()

    def close(self):
        if self.stream is not None:
            self.stream.seek(0)
            try:
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.stream, fcntl.LOCK_UN)
            finally:
                self.stream.close(); self.stream = None


def recover_lock(backend, directory, *, expected_lock_sha256, authorized=False):
    """Explicitly abandon an idle reservation; never rerun or change old results.

    Requires reviewed lock hash, verified inputs, intact final evidence if present,
    and two safe identity observations. Native use needs a separate human approval.
    Unknown/legacy lock schemas and active executors remain blocked.
    """
    if authorized is not True:
        raise PermissionError('lock_recovery_requires_explicit_review')
    directory = regular_path(directory)
    if not backend.simulated and directory.parent != Path('C:/estrategia/runs').absolute():
        raise ValueError('native_output_directory_not_allowed')
    lock = InstallationLock(backend.lock_path)
    if not lock.enter_guard():
        raise RuntimeError('executor_still_active')
    try:
        raw = regular_path(lock.path).read_bytes()
        if sha(raw) != expected_lock_sha256:
            raise ValueError('lock_hash_mismatch')
        record = json.loads(raw)
        if (record.get('schema_version') != 1 or record.get('run_id') != directory.name or
                not re.fullmatch(r'local_[0-9a-f]{32}', directory.name) or
                record.get('installation') != str(INSTALLATION) or record.get('data') != str(DATA) or
                not {'request.json', 'tester.ini'} <= set(record.get('inputs', {})) or
                not set(record.get('inputs', {})) <= {'request.json', 'tester.ini', 'profile.json',
                                                     'sf_o08_' + directory.name[6:] + '.set'}):
            raise ValueError('lock_context_mismatch')
        for name, expected in record['inputs'].items():
            if sha(regular_path(directory / name).read_bytes()) != expected:
                raise ValueError('recovery_input_integrity_mismatch')
        manifest = directory / 'artifact_sha256.json'
        if manifest.exists():
            for name, expected in json.loads(regular_path(manifest).read_text(encoding='utf-8')).items():
                if Path(name).name != name or '/' in name or '\\' in name:
                    raise ValueError('invalid_artifact_name')
                if sha(regular_path(directory / name).read_bytes()) != expected:
                    raise ValueError('recovery_evidence_integrity_mismatch')
            receipt = directory.parent / 'receipts' / (directory.name + '.json')
            if receipt.exists():
                verify_run_artifacts(directory)
        for _ in range(2):
            if preflight(backend.inspect(), profile=getattr(backend, 'profile', HOMOLOGATION_001)) is not None:
                raise ValueError('recovery_environment_not_safe')
        # Receipt is written first. If interrupted, the reservation stays in place
        # and a later recovery must again verify its exact hash and environment.
        receipt = {'action': 'abandon_reservation_without_retry', 'run_id': directory.name,
                   'lock_sha256': expected_lock_sha256, 'token': record['token'],
                   'simulation': backend.simulated, 'previous_result_unchanged': True,
                   'final_manifest_sha256': sha(manifest.read_bytes()) if manifest.exists() else None,
                   'reviewed_at_utc': datetime.now(timezone.utc).isoformat()}
        path = directory / ('recovery_' + uuid.uuid4().hex + '.json')
        write_artifact(path, receipt)
        lock.digest = expected_lock_sha256
        lock.release()
        return path
    finally:
        lock.close()


def verify_run_artifacts(directory):
    """Independently check a run against its external receipt, without any backend.

    This detects inconsistent/missing artifacts; hashes are not a digital signature
    and do not protect against a party able to replace the entire evidence set.
    """
    directory = regular_path(directory)
    receipt_path = regular_path(directory.parent / 'receipts' / (directory.name + '.json'))
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    manifest = regular_path(directory / 'artifact_sha256.json')
    if (receipt.get('run_id') != directory.name or
            receipt.get('artifact_manifest_sha256') != sha(manifest.read_bytes()) or
            receipt.get('result_sha256') != sha(regular_path(directory / 'result.json').read_bytes())):
        raise ValueError('independent_receipt_mismatch')
    for name, expected in json.loads(manifest.read_text(encoding='utf-8')).items():
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('invalid_artifact_name')
        if sha(regular_path(directory / name).read_bytes()) != expected:
            raise ValueError('artifact_integrity_mismatch')
    return {'run_id': directory.name, 'verified': True, 'status': receipt['status']}


def regular_path(path):
    """Reject redirections before traversing or creating an output path."""
    path = Path(path).absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('redirected_path')
        if part.exists():
            stat = part.stat()
            if getattr(stat, 'st_file_attributes', 0) & 0x400:
                raise ValueError('redirected_path')
            if part.is_file() and stat.st_nlink != 1:
                raise ValueError('hardlinked_file')
    return path


def validate_request(config, expected_sha256, *, profile=HOMOLOGATION_001):
    if not isinstance(config, BacktestConfig):
        raise ValueError('BacktestConfig_required')
    checked_profile(profile)
    if PureWindowsPath(config.expert) != profile.expert or expected_sha256 != profile.compiled_sha256:
        raise ValueError('unreviewed_EA_or_installation')
    if '..' in PureWindowsPath(config.expert).parts:
        raise ValueError('path_traversal')
    for value in (config.from_date, config.to_date):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('canonical_ISO_date_required')
    validate_scenario(config, profile)


def render_ini(config, report_name, *, profile=HOMOLOGATION_001):
    validate_request(config, checked_profile(profile).compiled_sha256, profile=profile)
    inputs = 'sf_o08_' + report_name[6:-4] + '.set' if profile.positive_operations else None
    return render_dedicated_ini(config, report_name, inputs_name=inputs)


def render_dedicated_ini(config, report_name, *, inputs_name=None):
    """Pure offline renderer; does not admit an EA to the runtime allowlist."""
    if not isinstance(config, BacktestConfig):
        raise ValueError('BacktestConfig_required')
    path = PureWindowsPath(config.expert)
    if '..' in path.parts or not path.is_relative_to(DATA / 'MQL5/Experts'):
        raise ValueError('expert_outside_dedicated_installation')
    for value in (config.from_date, config.to_date):
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError('canonical_ISO_date_required')
    if not re.fullmatch(r'local_[0-9a-f]{32}\.htm', report_name):
        raise ValueError('invalid_report_name')
    if inputs_name is not None and not re.fullmatch(r'sf_o08_[0-9a-f]{32}\.set', inputs_name):
        raise ValueError('invalid_inputs_name')
    expert = path.relative_to(DATA / 'MQL5/Experts')
    settings = dict(Expert=str(expert), Symbol=config.symbol, Period=config.timeframe,
                    FromDate=config.from_date.replace('-', '.'),
                    ToDate=config.to_date.replace('-', '.'), Model=MODELS[config.model],
                    Deposit=config.deposit, Currency=config.currency,
                    Leverage=f'1:{config.leverage}', ExecutionMode=config.execution_delay,
                    Optimization=0, ForwardMode=0, UseLocal=1, UseRemote=0,
                    UseCloud=0, Visual=0, Report=report_name, ReplaceReport=0,
                    ShutdownTerminal=1)
    if inputs_name is not None:
        settings['ExpertParameters'] = inputs_name
    return ('[Experts]\nAllowLiveTrading=0\nAllowDllImport=0\nEnabled=0\n'
            'Account=1\nProfile=1\n[Tester]\n' +
            ''.join(f'{key}={value}\n' for key, value in settings.items()))


def preflight(snapshot, *, profile=HOMOLOGATION_001):
    """Only fixed safe fields reach disk; account identifiers never leave backend."""
    checked_profile(profile)
    if snapshot.get('installation') != str(INSTALLATION) or snapshot.get('data') != str(DATA):
        return 'installation_mismatch'
    if snapshot.get('origin_matches') is not True:
        return 'origin_mismatch'
    if snapshot.get('busy') is not False:
        return 'process_already_running_or_unknown'
    if snapshot.get('demo_verified') is not True:
        return 'demo_not_verified'
    if snapshot.get('startup_safe') is not True:
        return 'startup_services_not_reviewed'
    if snapshot.get('ea_exists') is not True:
        return 'ea_missing'
    if snapshot.get('ea_sha256') != profile.compiled_sha256 or snapshot.get('source_sha256') != profile.source_sha256:
        return 'ea_hash_mismatch'
    if snapshot.get('build') != BUILD or snapshot.get('exe_sha256') != EXE_SHA256:
        return 'unreviewed_build_or_executable'
    return None


def sanitize_journal(text):
    # Preserve execution evidence, discard entire account/network/UI lines rather
    # than guessing the shape of names, identifiers, IPs or credentials.
    allowed = ('Tester', 'AutoTesting', 'Terminal', 'Startup', 'Core 01')
    result = []
    for line in text.splitlines():
        fields = line.split('\t', 4)
        if len(fields) != 5 or fields[3] not in allowed:
            continue
        if re.search(r'account|login|password|token|apikey|authorization|balance management', fields[4], re.I):
            continue
        if re.search(r"'\d+'", fields[4]):
            continue
        result.append(line)
    return '\n'.join(result)


def report_context_matches(report, *, expert, symbol, timeframe, from_date, to_date):
    """Shared strict PT/EN HTML context check; duplicate labels fail closed."""
    cells = TableCells(); cells.feed(report)
    labels = {}
    for row in cells.rows:
        for i in range(len(row) - 1):
            if not row[i].strip().endswith(':'):
                continue
            labels.setdefault(normalized(row[i]), []).append(row[i + 1])
    expected = [('ativo', 'symbol', symbol), ('expert advisor (robo)', 'expert', expert),
                ('periodo', 'period', f'{timeframe} ({from_date.replace("-", ".")} - {to_date.replace("-", ".")})')]
    return all(labels.get(pt, labels.get(en, [])) == [value] for pt, en, value in expected)


def evaluate(config, run_name, terminal, tester, report, *, final_snapshot, quiescent,
             profile=HOMOLOGATION_001):
    """A report or launcher exit alone never proves a completed native run."""
    validate_request(config, checked_profile(profile).compiled_sha256, profile=profile)
    metrics = analyze_report(report)['metrics'] if report is not None else None
    result = {'status': 'inconclusive', 'reason': 'insufficient_evidence', 'metrics': metrics}
    if not quiescent or final_snapshot.get('busy') is not False:
        return dict(result, reason='process_state_unknown_or_running')
    if (final_snapshot.get('origin_matches') is not True or
            final_snapshot.get('demo_verified') is not True or
            final_snapshot.get('startup_safe') is not True or
            final_snapshot.get('installation') != str(INSTALLATION) or
            final_snapshot.get('data') != str(DATA)):
        return dict(result, reason='final_identity_not_verified')
    if (final_snapshot.get('build') != BUILD or final_snapshot.get('exe_sha256') != EXE_SHA256):
        return dict(result, reason='unexpected_build_change')
    if (final_snapshot.get('ea_sha256') != profile.compiled_sha256 or
            final_snapshot.get('source_sha256') != profile.source_sha256):
        return dict(result, reason='ea_changed_during_run')
    if (str(DATA) not in terminal or f'{run_name}\\tester.ini' not in terminal or
            f'build {BUILD} started' not in terminal):
        return dict(result, reason='run_identity_not_proven')
    if any(token in tester.lower() for token in ('tester not started', 'test failed', 'initialization failed')):
        return dict(result, status='failed', reason='tester_failure')
    if report is None:
        return dict(result, reason='report_missing')
    start = (f'{config.symbol},{config.timeframe}: testing of Experts\\'
             f'{profile.expert.relative_to(DATA / "MQL5/Experts")} from '
             f'{config.from_date.replace("-", ".")} 00:00 to '
             f'{config.to_date.replace("-", ".")} 00:00 started')
    if (start not in tester or tester.count('automatic testing finished') != 1 or
            tester.count('Test passed') != 1 or
            tester.count('automatic testing started') > 1):
        return dict(result, reason='journal_incomplete_or_multiple_tests')
    model_marker = {'m1 ohlc': '1 minutes OHLC ticks generating',
                    'every tick': 'every tick generating',
                    'open prices': 'open prices', 'real ticks': 'real ticks'}[config.model]
    if model_marker.lower() not in tester.lower():
        return dict(result, reason='tick_model_not_proven')
    if 'cloud network mode is off' not in tester.lower():
        return dict(result, reason='cloud_disabled_not_proven')
    if not report_context_matches(report, expert=profile.expert.stem, symbol=config.symbol,
                                  timeframe=config.timeframe, from_date=config.from_date,
                                  to_date=config.to_date):
        return dict(result, reason='report_scenario_mismatch')
    if metrics['trades'] is None or metrics['deals'] is None:
        return dict(result, reason='trade_counts_unavailable')
    if profile.positive_operations:
        from .homologation_002 import assess_evidence
        assessment = assess_evidence(report, tester, run_id=run_name, config=config)
        if assessment['issues']:
            failed = bool({'ea_halted', 'order_rejection_or_error', 'order_not_fully_confirmed'} & set(assessment['issues']))
            return dict(result, status='failed' if failed else 'inconclusive',
                        reason='sf_o08_acceptance_not_met', assessment=assessment)
        return dict(result, status='completed', reason='dedicated_tester_and_positive_operations_proven',
                    assessment=assessment)
    if metrics['trades'] != 0 or metrics['deals'] != 0:
        return dict(result, status='failed', reason='unexpected_trading_activity')
    return dict(result, status='completed', reason='dedicated_tester_and_zero_trades_proven')


class LocalTesterExecutor:
    """One launch, no retries, no process termination. Locks span all state roots.

    The native backend owns its fixed lock namespace. Simulations must provide a
    temporary lock path. Real use requires a separate explicit authorization.
    """
    def __init__(self, backend):
        self.backend = backend

    def run(self, config, *, state_root, expected_sha256=None,
            simulate=True, authorized=False, timeout=120):
        profile = checked_profile(getattr(self.backend, 'profile', HOMOLOGATION_001))
        validate_request(config, profile.compiled_sha256 if expected_sha256 is None else expected_sha256,
                         profile=profile)
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= 600:
            raise ValueError('invalid_timeout')
        if self.backend.simulated is not simulate or (not simulate and authorized is not True):
            raise PermissionError('native_execution_requires_separate_human_authorization')
        root = regular_path(state_root)
        if not simulate and root != Path('C:/estrategia/runs').absolute():
            raise ValueError('native_state_root_not_allowed')
        root.mkdir(parents=True, exist_ok=True)
        name = 'local_' + uuid.uuid4().hex
        directory = root / name; directory.mkdir()
        ini = render_ini(config, name + '.htm', profile=profile)
        (directory / 'tester.ini').write_text(ini, encoding='ascii')
        write_artifact(directory / 'request.json', asdict(config))
        write_artifact(directory / 'profile.json', profile_record(profile))
        if profile.positive_operations:
            (directory / ('sf_o08_' + name[6:] + '.set')).write_text('InpRunId=' + name + '\n', encoding='ascii', newline='\n')
        lock = InstallationLock(self.backend.lock_path)
        result = {'status': 'blocked', 'reason': 'installation_locked', 'simulation': simulate,
                  'sf_mcp_restrict': 'blocked', 'launches': 0, 'run_id': name}
        acquired = False; launched = False; release = True; finalize = False
        try:
            acquired = lock.acquire(directory)
            if acquired:
                result['lock_sha256'] = lock.digest
                before = self.backend.inspect()
                result['observed_before'] = {key: before.get(key) for key in (
                    'build', 'exe_sha256', 'ea_sha256', 'source_sha256')}
                reason = preflight(before, profile=profile)
                if reason:
                    result['reason'] = reason
                else:
                    write_artifact(directory / 'attempt.json', {'launch_limit': 1, 'consumed': True})
                    launched = True; release = False; result['launches'] = 1
                    self.backend.launch(directory, timeout=timeout)
                    captured = self.backend.collect(directory)
                    terminal, tester, report = (captured[k] for k in ('terminal', 'tester', 'report'))
                    self._capture(directory, captured)
                    final = self.backend.inspect()
                    result['observed_after'] = {key: final.get(key) for key in (
                        'build', 'exe_sha256', 'ea_sha256', 'source_sha256')}
                    outcome = evaluate(config, name, terminal, tester, report,
                                       final_snapshot=final, quiescent=captured['quiescent'], profile=profile)
                    result.update(outcome)
                    release = captured['quiescent'] and outcome['status'] in ('completed', 'failed')
                    summary_report = {'statistics': outcome['metrics']} if outcome['metrics'] else None
                    write_artifact(directory / 'run_summary.json', summarize_run(
                        summary_report, parameters=asdict(config), local_run_id=name,
                        execution={'status': outcome['status']}, synthetic=simulate))
            finalize = True
        except Exception as error:
            # Do not persist exception messages from OS/config/account backends.
            result.update(status='inconclusive' if launched else 'blocked', reason='backend_error',
                          error_type=type(error).__name__)
            release = not launched
            if launched and not (directory / 'source_hashes.json').exists():
                try:
                    self._capture(directory, self.backend.collect(directory))
                except Exception:
                    result['capture_incomplete'] = True
            finalize = True
        finally:
            try:
                if finalize:
                    if acquired and release:
                        try:
                            if sha(regular_path(lock.path).read_bytes()) != lock.digest:
                                raise ValueError('lock_identity_changed')
                        except (OSError, ValueError):
                            release = False
                            result.update(status='inconclusive' if launched else 'blocked',
                                          reason='lock_identity_changed')
                    result['lock_retained'] = (not release) if acquired else lock.path.exists()
                    # Keep the OS guard and reservation until result, manifest and
                    # independent receipt are all written. Disk errors retain it.
                    self._finish(directory, config, result)
                    if acquired and release:
                        lock.release()
            finally:
                lock.close()
        return directory

    @staticmethod
    def _capture(directory, captured):
        terminal, tester, report = (captured[k] for k in ('terminal', 'tester', 'report'))
        for label, value in (('terminal', terminal), ('tester', tester)):
            (directory / (label + '.journal.txt')).write_text(sanitize_journal(value), encoding='utf-8')
        write_artifact(directory / 'source_hashes.json', {
            'raw_bytes': captured.get('raw_hashes'),
            'journal_ranges': captured.get('journal_ranges'),
            'decoded_text_utf8': {'terminal': sha(terminal.encode()), 'tester': sha(tester.encode()),
                                  'report': sha(report.encode()) if report is not None else None}})
        if report is not None:
            # The report parser exposes only numeric metrics and known labels.
            write_artifact(directory / 'report.json', analyze_report(report))

    @staticmethod
    def _finish(directory, config, result):
        result.setdefault('lock_retained', result.get('reason') == 'installation_locked')
        write_artifact(directory / 'result.json', result)
        write_artifact(directory / 'artifact_sha256.json', {
            p.name: sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()})
        receipts = regular_path(directory.parent / 'receipts')
        receipts.mkdir(exist_ok=True)
        write_artifact(receipts / (directory.name + '.json'), {
            'run_id': directory.name, 'simulation': result['simulation'],
            'status': result['status'], 'result_sha256': sha((directory / 'result.json').read_bytes()),
            'artifact_manifest_sha256': sha((directory / 'artifact_sha256.json').read_bytes())})
        return directory
