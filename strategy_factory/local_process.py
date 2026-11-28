"""Opt-in Windows backend for local_tester. Importing it performs no OS actions.

No process termination, MCP, account creation, installation changes or retries.
Existing dedicated terminals always block execution. Review this backend before
the second real homologation; offline tests never instantiate it against MT5.
"""
import configparser
from datetime import datetime
import os
from pathlib import Path
import re
import subprocess
import time

from .local_tester import DATA, EXPERT, INSTALLATION, regular_path, sha
from .local_profiles import HOMOLOGATION_001, checked_profile, profile_record


def read_text(path):
    if regular_path(path).stat().st_size > 32 * 1024 * 1024:
        raise ValueError('artifact_size_limit')
    data = regular_path(path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')


def require_fresh_report(*paths):
    for path in paths:
        if regular_path(path).exists():
            raise ValueError('report_already_exists')


class NativeLocalBackend:
    simulated = False
    lock_path = Path('C:/estrategia/runs/.sf_local_tester.lock')

    def __init__(self, *, authorized=False, profile=HOMOLOGATION_001):
        if authorized is not True:
            raise PermissionError('native_backend_requires_human_authorization')
        self._authorized = True
        self.profile = checked_profile(profile)
        if os.name != 'nt':
            raise RuntimeError('Windows_required')
        self.installation = regular_path(str(INSTALLATION))
        self.data = regular_path(str(DATA))
        self.executable = regular_path(self.installation / 'terminal64.exe')
        self._offsets = {}
        self._account = None

    def _powershell(self, command):
        result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive',
                                 '-Command', command], capture_output=True,
                                encoding='utf-8', timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('native_inventory_unavailable')
        return result.stdout.strip()

    def _busy(self):
        # Filter before output: no historical process paths or identifiers leave
        # the inventory command; no file of another installation is accessed.
        command = ("@(Get-CimInstance Win32_Process -Filter \"name = 'terminal64.exe'\" | "
                   "Where-Object { $_.ExecutablePath -eq "
                   "'C:\\estrategia\\infra\\mt5-factory\\terminal64.exe' "
                   "-or -not $_.ExecutablePath }).Count")
        return int(self._powershell(command)) != 0

    def _identity(self):
        c = configparser.ConfigParser(interpolation=None, strict=False)
        c.read_string(read_text(self.data / 'config/common.ini'))
        return (c.get('Common', 'Login', fallback=''), c.get('Common', 'Server', fallback=''))

    def _demo(self):
        identity = self._identity()
        login, server = identity
        if not login.isdigit() or login == '0' or server.casefold() != 'metaquotes-demo':
            return False
        if self._account is not None and identity != self._account:
            return False
        logs = sorted((self.data / 'logs').glob('20*.log'), key=lambda p: p.stat().st_mtime)
        if not logs or time.time() - logs[-1].stat().st_mtime > 900:
            return False
        lines = read_text(logs[-1]).splitlines()
        account_marker = "'" + login + "'"
        authorizations = [i for i, line in enumerate(lines)
                          if account_marker in line and 'authorized on MetaQuotes-Demo' in line]
        if not authorizations:
            return False
        try:
            fields = lines[authorizations[-1]].split('\t', 4)
            observed = datetime.strptime(logs[-1].stem + ' ' + fields[2],
                                         '%Y%m%d %H:%M:%S.%f').timestamp()
        except (ValueError, IndexError):
            return False
        if not 0 <= time.time() - observed <= 900:
            return False
        session = lines[authorizations[-1]:]
        # Graceful manual close is allowed; real/contest accounts are not.
        confirmed = any(account_marker in line and 'demo account' in line.lower() for line in session)
        if confirmed:
            self._account = identity  # memory only; never returned or serialized
        return confirmed

    def inspect(self):
        build = int(self._powershell(
            "(Get-Item -LiteralPath 'C:\\estrategia\\infra\\mt5-factory\\terminal64.exe').VersionInfo.FilePrivatePart"))
        expert = regular_path(str(self.profile.expert))
        source = regular_path(expert.with_suffix('.mq5'))
        services = regular_path(self.data / 'MQL5/Services')
        services_present = any(services.rglob('*.ex5')) if services.exists() else False
        return {'installation': str(INSTALLATION), 'data': str(DATA),
                'origin_matches': read_text(self.data / 'origin.txt').strip().casefold() == str(INSTALLATION).casefold(),
                'busy': self._busy(), 'demo_verified': self._demo(),
                'startup_safe': not services_present,
                'build': build, 'exe_sha256': sha(self.executable.read_bytes()),
                'ea_exists': expert.is_file(),
                'ea_sha256': sha(expert.read_bytes()) if expert.is_file() else None,
                'source_sha256': sha(source.read_bytes()) if source.is_file() else None}

    def _logs(self):
        roots = (self.data / 'logs', self.data / 'Tester',
                 Path('C:/Users/User/AppData/Roaming/MetaQuotes/Tester') / DATA.name)
        for root in roots:
            if root.exists():
                for path in root.rglob('*.log'):
                    yield regular_path(path)

    def launch(self, directory, *, timeout):
        if getattr(self, '_authorized', False) is not True:
            raise PermissionError('native_backend_not_authorized')
        from .local_tester import preflight, render_ini
        from .tester import BacktestConfig
        import json
        directory = regular_path(directory)
        if directory.parent != Path('C:/estrategia/runs').absolute():
            raise ValueError('native_output_directory_not_allowed')
        request = json.loads(read_text(directory / 'request.json'))
        profile = checked_profile(getattr(self, 'profile', HOMOLOGATION_001))
        if json.loads(read_text(directory / 'profile.json')) != profile_record(profile):
            raise ValueError('prepared_profile_changed')
        expected_ini = render_ini(BacktestConfig(**request), directory.name + '.htm', profile=profile)
        if read_text(directory / 'tester.ini') != expected_ini:
            raise ValueError('prepared_ini_changed')
        # Recheck immediately before launch under the executor's installation lock.
        if preflight(self.inspect(), profile=profile) is not None:
            raise PermissionError('prelaunch_identity_changed')
        report_name = directory.name + '.htm'
        require_fresh_report(self.data / report_name, self.installation / report_name)
        self._offsets = {p: p.stat().st_size for p in self._logs()}
        if self._identity() != self._account:
            raise PermissionError('demo_identity_changed')
        if profile.positive_operations:
            stage_inputs(directory, self.data)
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        self.process = subprocess.Popen([str(self.executable), '/config:' + str(directory / 'tester.ini')],
                                        cwd=self.installation, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        startupinfo=startup)
        # Native LiveUpdate can replace the initial launcher. Poll the dedicated
        # installation, not only Popen.wait(). Never kill a timeout or relaunch.
        deadline = time.monotonic() + timeout
        quiet_since = None
        while time.monotonic() < deadline:
            busy = self._busy()
            if not busy:
                quiet_since = quiet_since or time.monotonic()
                if time.monotonic() - quiet_since >= 3 and self.process.poll() is not None:
                    break
            else:
                quiet_since = None
            time.sleep(0.5)

    def collect(self, directory):
        terminal, tester = [], []
        raw_hashes = {}
        journal_ranges = []
        for path in self._logs():
            previous = self._offsets.get(path, 0)
            size = path.stat().st_size
            if size < previous:
                raise RuntimeError('journal_truncated')
            if size - previous > 32 * 1024 * 1024:
                raise ValueError('journal_size_limit')
            with path.open('rb') as stream:
                stream.seek(previous)
                delta = stream.read()
            if not delta:
                continue
            key = (str(path.relative_to(self.data)) if path.is_relative_to(self.data) else
                   'agent/' + str(path.relative_to(Path('C:/Users/User/AppData/Roaming/MetaQuotes/Tester') / DATA.name)))
            raw_hashes[key] = sha(delta)
            journal_ranges.append({'source': key, 'offset': previous,
                                   'length': len(delta), 'sha256': sha(delta)})
            text = delta.decode('utf-16' if delta.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-16le')
            if path.parent == self.data / 'logs' and re.fullmatch(r'20[0-9]{6}\.log', path.name):
                terminal.append(text)
            elif path.parent == self.data / 'Tester/logs':
                tester.append(text)
        report = regular_path(self.data / (directory.name + '.htm'))
        if report.exists():
            if report.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('report_size_limit')
            raw_hashes['report'] = sha(report.read_bytes())
        # Common/main mode report location is fixed by the approved POC. No scan
        # of other installations, Common or arbitrary report paths.
        return {'terminal': '\n'.join(terminal), 'tester': '\n'.join(tester),
                'report': read_text(report) if report.exists() else None,
                'raw_hashes': raw_hashes,
                'journal_ranges': journal_ranges,
                'quiescent': not self._busy() and self._identity() == self._account}


def stage_inputs(directory, data):
    """One fresh run-bound SET, only after native preflight under installation lock."""
    if regular_path(data) != regular_path(str(DATA)):
        raise ValueError('inputs_data_directory_not_allowed')
    if not re.fullmatch(r'local_[0-9a-f]{32}', directory.name):
        raise ValueError('invalid_run_id')
    name = 'sf_o08_' + directory.name[6:] + '.set'
    content = regular_path(directory / name).read_bytes()
    if content != ('InpRunId=' + directory.name + '\n').encode('ascii'):
        raise ValueError('prepared_inputs_changed')
    target = regular_path(data / 'MQL5/Profiles/Tester' / name)
    # No overwrite, directory creation or cleanup of an earlier execution.
    with target.open('xb') as stream:
        stream.write(content)
