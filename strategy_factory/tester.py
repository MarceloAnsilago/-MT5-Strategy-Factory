"""MCP orchestration. No terminal launch, account configuration or trading APIs."""
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import json
import hashlib
import math
import ntpath
from pathlib import Path, PureWindowsPath
import re
import time
import tempfile
import uuid

from .reports import analyze_report


class TesterError(RuntimeError):
    pass


def write_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)


@dataclass(frozen=True)
class BacktestConfig:
    expert: str
    symbol: str
    timeframe: str
    from_date: str
    to_date: str
    deposit: float = 10000
    currency: str = 'BRL'
    model: str = 'every tick'
    execution_delay: int = 0
    leverage: int = 1
    spread: float | None = None

    def __post_init__(self):
        if not PureWindowsPath(self.expert).is_absolute() or not self.expert.lower().endswith('.ex5'):
            raise ValueError('expert must be an absolute compiled .ex5 path')
        for value in (self.expert, self.symbol, self.currency):
            if not value or any(c in value for c in '\r\n\x00'):
                raise ValueError('invalid text parameter')
        if not re.fullmatch(r'[A-Za-z0-9_.#@+!\-]{1,64}', self.symbol):
            raise ValueError('invalid symbol')
        if self.timeframe not in ('M1','M2','M3','M4','M5','M6','M10','M12','M15','M20','M30','H1','H2','H3','H4','H6','H8','H12','D1','W1','MN1'):
            raise ValueError('invalid timeframe')
        if date.fromisoformat(self.from_date) >= date.fromisoformat(self.to_date):
            raise ValueError('testing requires at least one calendar day')
        if isinstance(self.deposit, bool) or not math.isfinite(self.deposit) or self.deposit <= 0:
            raise ValueError('invalid deposit')
        if not re.fullmatch('[A-Z]{3}', self.currency):
            raise ValueError('invalid currency')
        if self.model not in ('every tick', 'm1 ohlc', 'open prices', 'real ticks'):
            raise ValueError('unsupported tick model')
        if type(self.execution_delay) is not int or not -1 <= self.execution_delay <= 600000:
            raise ValueError('invalid execution delay')
        if type(self.leverage) is not int or self.leverage <= 0:
            raise ValueError('invalid leverage')
        if self.spread is not None:
            raise ValueError('fixed spread is not exposed by Rico tester_prepare_config')

    def prepare_arguments(self, output_path):
        return dict(mql5_program_path=self.expert, output_path=output_path,
                    symbol=self.symbol, timeframe=self.timeframe,
                    from_date=self.from_date + 'T00:00:00', to_date=self.to_date + 'T00:00:00',
                    deposit=self.deposit, deposit_currency=self.currency, model=self.model,
                    execution_delay=self.execution_delay, leverage=self.leverage,
                    optimization=False, genetic=False, forward_mode=0, profit_in_pips=False)


def payload(response):
    if not isinstance(response, dict) or response.get('isError'):
        raise TesterError('MCP call failed; remote error content omitted for credential safety')
    if 'structuredContent' in response:
        return response['structuredContent']
    blocks = [b.get('text', '') for b in response.get('content', []) if b.get('type') == 'text']
    if len(blocks) == 1:
        try:
            return json.loads(blocks[0])
        except ValueError:
            pass
    raise TesterError('unrecognized MCP response envelope')


def within(path, roots):
    candidate = ntpath.normcase(ntpath.normpath(path))
    for root in roots:
        try:
            if ntpath.commonpath([candidate, ntpath.normcase(ntpath.normpath(root))]) == ntpath.normcase(ntpath.normpath(root)):
                return True
        except ValueError:
            pass
    return False


class TesterRunner:
    """call_tool(name, arguments) is an authenticated, bounded MCP transport.

    Use one shared state_root per terminal. Uncertain remote state leaves a lock
    behind deliberately, including crashes; never auto-remove stale locks.
    """
    __test__ = False

    def __init__(self, state_root, call_tool=None, *, clock=time.monotonic, sleep=time.sleep):
        self.root = Path(state_root)
        self.call_tool = call_tool
        self.clock, self.sleep = clock, sleep

    def run(self, config, *, simulate=True, authorized=False, timeout=300, poll_interval=1):
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(poll_interval) or poll_interval <= 0:
            raise ValueError('timeout and poll interval must be positive finite values')
        if not simulate and (not authorized or self.call_tool is None):
            raise PermissionError('real tester requires explicit authorization and MCP transport')
        self.root.mkdir(parents=True, exist_ok=True)
        run_dir = self.root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex)
        run_dir.mkdir(exist_ok=False)
        write_new(run_dir / 'request.json', asdict(config))
        if simulate:
            write_new(run_dir / 'plan.json', config.prepare_arguments('<MQL5>\\Profiles\\Tester\\factory_' + run_dir.name + '.ini'))
            write_new(run_dir / 'result.json', {'status': 'simulated', 'metrics': None})
            return run_dir
        lock = self.root / 'terminal.lock'
        # Atomic acquisition spans processes. Existing lock is never overwritten.
        with lock.open('x', encoding='utf-8') as stream:
            stream.write(run_dir.name)
        release = True
        terminal_lock = None
        run_id = None
        deadline = self.clock() + timeout

        def call(name, args):
            return payload(self.call_tool(name, args))

        def stopped(data):
            return isinstance(data, dict) and data.get('status') in ('stopped', 'completed', 'finished')

        try:
            workspace = call('get_workspace_info', {})
            if not workspace.get('capabilities', {}).get('can_run_backtest'):
                raise TesterError('backtest unavailable')
            mql5 = workspace['workspace']['mql5_folder']
            # Same terminal is serialized even when callers use different run roots.
            lock_root = Path(tempfile.gettempdir()) / 'mt5-strategy-factory-locks'
            lock_root.mkdir(exist_ok=True)
            identity = hashlib.sha256(ntpath.normcase(ntpath.normpath(mql5)).encode()).hexdigest()
            candidate_lock = lock_root / (identity + '.lock')
            with candidate_lock.open('x', encoding='utf-8') as stream:
                stream.write(str(run_dir.resolve()))
            terminal_lock = candidate_lock
            remote_config = str(PureWindowsPath(mql5) / 'Profiles' / 'Tester' / ('factory_' + run_dir.name + '.ini'))
            permissions = workspace['permissions']
            if not within(config.expert, permissions.get('read_roots', [])) or not within(remote_config, permissions.get('write_roots', [])):
                raise TesterError('path outside MCP permissions')
            args = config.prepare_arguments(remote_config)
            write_new(run_dir / 'prepare.json', args)
            call('tester_prepare_config', args)
            if self.clock() >= deadline:
                raise TimeoutError('timeout before start')
            # An ambiguous start error may still mean a running remote test.
            release = False
            started = call('tester_run_backtest', {'config_path': remote_config, 'wait': False})
            run_id = started.get('run_id')
            if not isinstance(run_id, str) or not run_id:
                raise TesterError('start returned no run_id; reconcile lock manually')
            write_new(run_dir / 'remote_run.json', {'run_id': run_id})
            index = 0
            while True:
                if self.clock() >= deadline:
                    raise TimeoutError('tester deadline exceeded')
                status = call('tester_get_status', {'run_id': run_id})
                write_new(run_dir / f'status_{index:06d}.json', status)
                index += 1
                if stopped(status):
                    release = True
                    if status.get('error') or status.get('success') is False:
                        raise TesterError('tester reported failure')
                    break
                if status.get('status') in ('failed', 'error', 'cancelled'):
                    raise TesterError('tester did not complete successfully')
                if status.get('status') not in ('started', 'running'):
                    raise TesterError('unknown tester status; refusing to infer completion')
                self.sleep(min(poll_interval, max(0, deadline - self.clock())))
            report = call('tester_get_report', {'run_id': run_id, 'file_format': 'json'})
            write_new(run_dir / 'report.json', report)
            analysis = analyze_report(report)
            write_new(run_dir / 'analysis.json', analysis)
            write_new(run_dir / 'result.json', {'status': 'completed', 'analysis_status': analysis['status']})
        except Exception as exc:
            if run_id and not release:
                try:
                    call('tester_stop', {'run_id': run_id})
                    release = stopped(call('tester_get_status', {'run_id': run_id}))
                except Exception:
                    release = False
            # Exception messages can contain headers or credentials from a transport.
            write_new(run_dir / 'failure.json', {'status': 'failed', 'error_type': type(exc).__name__,
                      'lock_retained': not release, 'run_id': run_id})
            raise TesterError(f'{type(exc).__name__}; diagnostics: {run_dir}') from None
        finally:
            if release:
                if terminal_lock is not None:
                    terminal_lock.unlink()
                lock.unlink()
        return run_dir
