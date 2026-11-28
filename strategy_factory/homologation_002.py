"""SF-O08 offline package, reference and conservative evidence checks.

No compiler, OS process, transport, account API or native execution entry point.
The separate execution profile pins the reviewed source/EX5. Reference
simulations are not MQL compilation or native parity.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal
import hashlib
import math
from pathlib import Path
import re
from string import Template
import uuid

from .analysis import write_artifact
from .financial import validate_financial
from .generator import canonical, digest
from .local_tester import DATA, regular_path, render_dedicated_ini, report_context_matches
from .reports import analyze_report
from .local_profiles import SF_O08
from .tester import BacktestConfig

STRATEGY_ID = 'SF-O08-H002-EMA5-20-v1'
TEMPLATE = Path(__file__).parent / 'templates/homologation_002_sfo08.mq5.in'
SOURCE = Path(__file__).resolve().parents[1] / 'src/mql5/Experts/SFO08/MT5SF_Homologacao_002.mq5'
TARGET = DATA / 'MQL5/Experts/MT5StrategyFactory/SFO08/Homologacao_002/MT5SF_Homologacao_002.ex5'


def specification():
    return dict(schema_version='1.0', phase='SF-O08', strategy_id=STRATEGY_ID,
                symbol='EURUSD', timeframe='M5', method='EMA', fast=5, slow=20,
                volume='0.01', closed_shifts=[2, 1], exit='opposite_cross_close_then_defer_one_bar',
                same_bar_reentry=False, tester_only=True, demo_only=True,
                optimization=False, forward=False)


SPEC_SHA256 = digest(specification())
MAGIC = int(SPEC_SHA256[:12], 16)


def render():
    template = TEMPLATE.read_text(encoding='utf-8')
    source = Template(template).substitute(strategy_id=STRATEGY_ID,
                                            spec_sha256=SPEC_SHA256, magic=MAGIC)
    metadata = dict(strategy_id=STRATEGY_ID, spec_sha256=SPEC_SHA256, magic=MAGIC,
                    source_sha256=hashlib.sha256(source.encode()).hexdigest(),
                    template_sha256=hashlib.sha256(template.encode()).hexdigest(),
                    compiled_sha256=SF_O08.compiled_sha256, status='compiled_native_homologation_pending',
                    live_execution_enabled=False)
    return source, metadata


def prepare_offline(output_root, *, config=None):
    """Create a new source/INI/SET package, never touching a terminal directory."""
    output = regular_path(output_root)
    project = SOURCE.parents[4]
    approved = (project / 'artifacts').resolve()
    if not output.is_relative_to(approved):
        raise ValueError('offline_package_must_be_under_project_artifacts')
    source, metadata = render()
    if SOURCE.read_bytes() != source.encode('utf-8'):
        raise ValueError('materialized_source_integrity_mismatch')
    if config is None:
        config = BacktestConfig(str(TARGET), 'EURUSD', 'M5', '2023-11-01', '2023-11-02',
                                currency='USD', model='m1 ohlc')
    from .local_profiles import SF_O08, profile_record
    from .local_tester import validate_request
    validate_request(config, SF_O08.compiled_sha256, profile=SF_O08)
    output.mkdir(parents=True, exist_ok=False)
    run_id = 'local_' + uuid.uuid4().hex
    inputs_name = 'sf_o08_' + run_id[6:] + '.set'
    (output / SOURCE.name).write_bytes(source.encode())
    (output / inputs_name).write_text('InpRunId=' + run_id + '\n', encoding='ascii', newline='\n')
    (output / 'tester.ini').write_text(render_dedicated_ini(
        config, run_id + '.htm', inputs_name=inputs_name), encoding='ascii')
    write_artifact(output / 'profile.json', profile_record(SF_O08))
    write_artifact(output / 'manifest.json', dict(metadata, specification=specification(),
                   run_id=run_id, config=asdict(config), inputs_file=inputs_name,
                   sf_mcp_restrict='blocked',
                   native_gate='blocked_until_explicit_human_authorization'))
    write_artifact(output / 'artifact_sha256.json', {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()})
    return output


def volume_allowed(minimum, maximum, step):
    try:
        lo, hi, inc = (Decimal(str(v)) for v in (minimum, maximum, step))
        lot = Decimal('0.01')
        return (all(v.is_finite() for v in (lo, hi, inc)) and lo > 0 and inc > 0 and
                lo <= lot <= hi and lot % inc == 0)
    except (ValueError, ArithmeticError):
        return False


def closed_cross(fast, slow):
    """Exactly two closed observations: older shift 2, then newer shift 1."""
    if len(fast) != 2 or len(slow) != 2 or any(
        type(x) not in (int, float) or not math.isfinite(x) or not 0 < x < 1e100
        for x in (*fast, *slow)
    ):
        raise ValueError('two_valid_closed_observations_required')
    if fast[0] <= slow[0] and fast[1] > slow[1]: return 'buy'
    if fast[0] >= slow[0] and fast[1] < slow[1]: return 'sell'
    return None


@dataclass(frozen=True)
class SimulatedPosition:
    side: str
    symbol: str = 'EURUSD'
    magic: int = MAGIC
    volume: float = 0.01


class ReferenceSession:
    """Deterministic control-flow reference, never an order transport or backtest.

    Comparisons, position changes and retcodes here are synthetic. Tests of this
    model plus source contracts cannot prove the native behavior or execution parity.
    """
    def __init__(self, *, tester=True, demo=True, optimization=False, forward=False,
                 symbol='EURUSD', timeframe='M5', minimum=.01, maximum=100, step=.01):
        if not tester or not demo or optimization or forward:
            raise ValueError('standalone_demo_tester_required')
        if symbol != 'EURUSD' or timeframe != 'M5' or not volume_allowed(minimum, maximum, step):
            raise ValueError('scenario_or_fixed_volume_invalid')
        self.last_bar = 0; self.position = None; self.halted = False
        self.deferred = None
        self.events = []; self.rejections = 0

    def tick(self, bar, fast, slow, *, pending=0, extra_positions=0,
             sent=True, retcode=10009, filled_volume=.01):
        if self.halted or bar <= 0 or bar <= self.last_bar: return None
        signal = closed_cross(fast, slow)
        self.last_bar = bar
        if pending or extra_positions:
            self.halted = True; return None
        if self.position is not None and (
            self.position.symbol != 'EURUSD' or self.position.magic != MAGIC or
            self.position.volume != .01 or self.position.side not in ('buy', 'sell')
        ):
            self.halted = True; return None
        if self.position:
            action = 'close' if signal and signal != self.position.side else None
        else:
            deferred, self.deferred = self.deferred, None
            still_valid = deferred == 'buy' and fast[1] > slow[1] or deferred == 'sell' and fast[1] < slow[1]
            action = deferred if still_valid else signal
        if action is None: return None
        self.events.append(dict(action=action, volume=.01, retcode=retcode, sent=sent))
        if not sent or retcode != 10009:
            self.rejections += 1; self.halted = True
        elif action != 'close' and filled_volume != .01:
            self.halted = True
        else:
            if action == 'close': self.deferred = signal
            self.position = None if action == 'close' else SimulatedPosition(action)
        return action


def assess_evidence(report, journal, *, run_id, config=None):
    """Offline assessment of run-bound telemetry; not native execution approval."""
    if not re.fullmatch(r'local_[0-9a-f]{32}', run_id):
        raise ValueError('invalid_run_id')
    parsed = analyze_report(report)
    from_date = config.from_date if config else '2023-11-01'
    to_date = config.to_date if config else '2023-11-02'
    stats, ending, orders, issues = {}, [], [], []
    if isinstance(report, dict):
        expected = dict(run_id=run_id, strategy_id=STRATEGY_ID, symbol='EURUSD', timeframe='M5',
                        from_date=from_date, to_date=to_date)
        if any(report.get(k) != value for k, value in expected.items()): issues.append('report_context_mismatch')
    elif isinstance(report, str):
        if (not report_context_matches(report, expert='MT5SF_Homologacao_002', symbol='EURUSD',
                                       timeframe='M5', from_date=from_date, to_date=to_date) or
                not re.search(r'InpRunId='+re.escape(run_id)+r'(?![a-zA-Z0-9_])', report)):
            issues.append('report_context_mismatch')
    else: issues.append('report_context_mismatch')
    init = f'SFO08 INIT strategy={STRATEGY_ID} run={run_id} spec={SPEC_SHA256} magic={MAGIC} symbol=EURUSD timeframe=M5'
    if journal.count(init) != 1: issues.append('one_bound_init_marker_required')
    prefix = f'SFO08 STAT strategy={STRATEGY_ID} run={run_id} name='
    for line in journal.splitlines():
        if 'SFO08 ' not in line: continue
        if f'strategy={STRATEGY_ID} run={run_id} ' not in line:
            issues.append('telemetry_identity_mismatch'); continue
        if prefix in line:
            part = line.split(prefix, 1)[1]
            match = re.fullmatch(r'([a-z_]+) value=(UNAVAILABLE|[+-]?[0-9]+(?:\.[0-9]+)?)', part)
            if not match: issues.append('invalid_stat_marker'); continue
            key, value = match.groups()
            if key in stats: issues.append('duplicate_stat_marker'); continue
            allowed = {'trades','deals','net_profit','orders','owned_market_deals','profit_factor',
                       'balance_drawdown_absolute','equity_drawdown_absolute',
                       'balance_drawdown_relative','equity_drawdown_relative'}
            if key not in allowed: issues.append('unknown_stat_marker'); continue
            parsed_value = None if value == 'UNAVAILABLE' else float(value)
            if parsed_value is not None and (not math.isfinite(parsed_value) or abs(parsed_value) >= 1e100 or
                (key in ('trades','deals','orders','owned_market_deals') and
                 (parsed_value < 0 or not parsed_value.is_integer()))):
                issues.append('invalid_stat_value'); parsed_value = None
            stats[key] = parsed_value
        if 'SFO08 END ' in line:
            ending.append(line.split('SFO08 END ', 1)[1])
        if 'SFO08 ORDER ' in line:
            match = re.fullmatch(re.escape(f'strategy={STRATEGY_ID} run={run_id} ') +
                r'action=(buy|sell|close) sent=([01]) retcode=(\d+) deal=(\d+) order=(\d+)',
                line.split('SFO08 ORDER ', 1)[1])
            if match: orders.append(match.groups())
            else: issues.append('invalid_order_marker')
        if 'SFO08 HALT ' in line: issues.append('ea_halted')
    end = None
    if len(ending) != 1:
        issues.append('one_end_marker_required')
    else:
        match = re.fullmatch(re.escape(f'strategy={STRATEGY_ID} run={run_id} ') +
                             r'requests=(\d+) rejected=(\d+) errors=(\d+) buys=(\d+) sells=(\d+) closes=(\d+) halted=([01])', ending[0])
        if match: end = dict(zip(('requests','rejected','errors','buys','sells','closes','halted'),map(int,match.groups())))
        else: issues.append('invalid_end_marker')
    if end:
        if end['rejected'] or end['errors'] or end['halted']: issues.append('order_rejection_or_error')
        if not end['buys'] or not end['sells'] or not end['closes']: issues.append('directional_coverage_incomplete')
        if end['requests'] != len(orders) or end['requests'] != end['buys']+end['sells']+end['closes']:
            issues.append('request_count_mismatch')
        if any(sent != '1' or code != '10009' or int(deal) <= 0 or int(order) <= 0
               for _, sent, code, deal, order in orders): issues.append('order_not_fully_confirmed')
        for action, counter in (('buy','buys'),('sell','sells'),('close','closes')):
            if sum(o[0] == action for o in orders) != end[counter]: issues.append('action_count_mismatch')
        for key in ('orders','owned_market_deals'):
            if stats.get(key) is None or stats[key] < end['requests']:
                issues.append(key+'_coverage_incomplete')
    if (parsed['metrics']['trades'] is None or parsed['metrics']['deals'] is None or
            parsed['metrics']['trades'] <= 0 or parsed['metrics']['deals'] <= 0):
        issues.append('positive_trade_counts_required')
    reference = {'statistics': {key: value for key, value in stats.items() if value is not None}}
    comparison = validate_financial(report, run_id=run_id, native_reference=reference, reference_run_id=run_id)
    if comparison['status'] == 'divergent': issues.append('financial_evidence_diverges')
    for key in ('trades','deals','net_profit','orders','balance_drawdown_relative','equity_drawdown_relative'):
        if stats.get(key) is None: issues.append(key + '_telemetry_unavailable')
        if key != 'orders' and parsed['metrics'].get(key) is None: issues.append(key + '_report_unavailable')
    if parsed['metrics']['gross_loss'] is not None and parsed['metrics']['gross_loss'] < 0:
        if parsed['metrics']['profit_factor'] is None or stats.get('profit_factor') is None:
            issues.append('calculable_profit_factor_unavailable')
    return dict(strategy_id=STRATEGY_ID, run_id=run_id,
                status='offline_evidence_consistent' if not issues else 'inconclusive',
                native_homologation_approved=False, metrics=parsed['metrics'],
                telemetry=stats, order_outcomes=end, issues=sorted(set(issues)),
                financial_validation=comparison['status'])
