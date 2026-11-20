"""Offline run summaries and comparison collections. No MCP or execution APIs."""
import argparse
from collections import Counter
from copy import deepcopy
from datetime import date
import json
import math
from pathlib import Path, PureWindowsPath
import re

from .financial import validate_financial
from .reports import ALIASES, COUNT_METRICS
from .traceability import build_traceability, parse_set, equivalent
from .traceability import PARAMETERS as TRACE_PARAMETERS, SETTINGS as TRACE_SETTINGS, COSTS, HISTORY, scalar

SCHEMA_VERSION = '1.1'
SCENARIO_FIELDS = ('symbol', 'timeframe', 'from_date', 'to_date', 'model',
                   'deposit', 'currency', 'leverage', 'execution_delay')
CONTEXT_FIELDS = ('terminal_build', 'history_fingerprint', 'costs_fingerprint', 'agents')
CORE_METRICS = tuple(key for key in ALIASES if key not in ('orders', 'positions'))
SENSITIVE = re.compile(r'token|password|secret|credential|authorization|dpapi|account|login', re.I)


def write_artifact(path, value):
    """Exclusive creation; serialization failure leaves no partial artifact."""
    encoded = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(encoded)


def read_artifact(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid_constant(value):
        raise ValueError('non-finite JSON constant')
    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError('non-finite JSON number')
        return result
    text = read_text_artifact(path)
    value = json.loads(text, object_pairs_hook=unique, parse_constant=invalid_constant, parse_float=finite_float)
    if isinstance(value, dict) and value.get('isError'):
        raise ValueError('MCP error envelope is not evidence')
    if isinstance(value, dict) and 'structuredContent' in value:
        value = value['structuredContent']
    elif isinstance(value, dict) and len(value.get('content', [])) == 1:
        block = value['content'][0]
        if block.get('type') == 'text':
            value = json.loads(block['text'], object_pairs_hook=unique, parse_constant=invalid_constant, parse_float=finite_float)
    return value


def read_text_artifact(path):
    data=Path(path).read_bytes()
    return data.decode('utf-16' if data.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')


def clean_inputs(inputs):
    if inputs is None:
        return None
    if not isinstance(inputs, dict):
        raise ValueError('strategy inputs must be an object')
    result = {}
    for key, value in inputs.items():
        if not isinstance(key, str) or SENSITIVE.search(key):
            raise ValueError('sensitive or invalid strategy input key')
        if not isinstance(value, (str, int, float, bool)) or (
                isinstance(value, float) and not math.isfinite(value)):
            raise ValueError('strategy inputs must contain finite scalar values')
        result[key] = value
    return result


def clean_parameters(parameters):
    if not isinstance(parameters, dict):
        raise ValueError('parameters must be an object')
    result, warnings = {}, []
    for key in SCENARIO_FIELDS:
        value = parameters.get(key)
        valid = value is not None
        if key in ('deposit', 'leverage', 'execution_delay'):
            valid = type(value) in (int, float) and math.isfinite(value)
            if valid and key != 'execution_delay':
                valid = value > 0
            if valid and key == 'execution_delay':
                valid = -1 <= value <= 600000
        else:
            valid = isinstance(value, str) and bool(value.strip()) and not any(c in value for c in '\r\n\x00')
        if valid and key in ('from_date', 'to_date'):
            try:
                valid = bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value))
                date.fromisoformat(value)
            except ValueError:
                valid = False
        result[key] = value if valid else None
        if not valid:
            warnings.append('parameter_missing_or_invalid:' + key)
    if result['from_date'] and result['to_date'] and result['from_date'] >= result['to_date']:
        result['from_date'] = result['to_date'] = None
        warnings.append('invalid_date_range')
    return result, warnings


def clean_context(data_context):
    if data_context is not None and not isinstance(data_context,dict):
        raise ValueError('data context must be an object')
    context,warnings = {},[]
    for key in CONTEXT_FIELDS:
        value = (data_context or {}).get(key)
        if key == 'terminal_build':
            valid = type(value) is int and value > 0
        elif key == 'agents':
            valid = value == 'local_only'
        else:
            valid = isinstance(value,str) and bool(re.fullmatch('[0-9a-f]{64}',value))
        context[key] = value if valid else None
        if not valid:
            warnings.append('context_unavailable:' + key)
    return context,warnings


def summarize_run(report, *, parameters, run_id=None, local_run_id=None, inputs=None,
                  execution=None, journal=None, journal_run_id=None,
                  native_reference=None, reference_run_id=None, data_context=None,
                  synthetic=False, tester_ini=None, inputs_set=None,
                  history_snapshot=None, symbol_snapshot=None):
    """Keep all source candidates. Conflicting values are never silently selected.

    Parameters describe the requested scenario, not verified remote INI contents.
    Journal/reference IDs assert a caller-audited scope; they do not prove identity.
    """
    if run_id is None and isinstance(report, dict):
        run_id = report.get('run_id')
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
        raise ValueError('run_id must be a nonempty string')
    if not run_id and not local_run_id:
        raise ValueError('a remote or local run identifier is required')
    if local_run_id is not None and (not isinstance(local_run_id, str) or not local_run_id.strip()):
        raise ValueError('invalid local run identifier')
    scenario, warnings = clean_parameters(parameters)
    strategy_inputs = clean_inputs(inputs if inputs is not None else (parse_set(inputs_set) if inputs_set is not None else None))
    if strategy_inputs is None:
        warnings.append('strategy_inputs_unavailable')
    expert = parameters.get('expert')
    expert = PureWindowsPath(expert).name if isinstance(expert, str) and expert else None
    if expert is None:
        warnings.append('expert_unavailable')
    execution = execution or {}
    status = execution.get('status', 'unknown')
    if status not in ('completed', 'failed', 'simulated', 'unknown'):
        status = 'unknown'
    timings = {}
    for key in ('elapsed_seconds', 'tester_observation_seconds', 'timeout_seconds'):
        value = execution.get(key)
        timings[key] = value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
    context,context_warnings = clean_context(data_context)
    warnings.extend(context_warnings)
    validation = validate_financial(report, journal=journal, run_id=run_id,
                       journal_run_id=journal_run_id, native_reference=native_reference,
                       reference_run_id=reference_run_id)
    traceability=build_traceability(parameters=parameters,inputs=strategy_inputs,report=report,
        run_id=run_id,journal=journal,journal_run_id=journal_run_id,tester_ini=tester_ini,
        inputs_set=inputs_set,history_snapshot=history_snapshot,symbol_snapshot=symbol_snapshot)
    warnings.extend('traceability:'+w for w in traceability['warnings'])
    checks = validation['checks']
    conflicts = {check['metric'] for check in checks if check['status'] == 'divergent'}
    provenance_invalid = any('run_id' in issue for issue in validation['issues'])
    if traceability['classification']=='divergent':
        provenance_invalid=True
        warnings.append('effective_configuration_divergent')
    if isinstance(report, dict) and report.get('symbol') and scenario['symbol'] and report['symbol'] != scenario['symbol']:
        provenance_invalid = True
        warnings.append('report_symbol_mismatch')
    initial_balance = validation['report']['metrics']['initial_balance']
    if initial_balance is not None and scenario['deposit'] is not None and abs(initial_balance-scenario['deposit']) > 0.01+1e-10:
        provenance_invalid = True
        warnings.append('requested_deposit_mismatch')
    metrics = {}
    for key in ALIASES:
        candidates = []
        for source, analysis in (('report', validation['report']), ('journal', validation['journal']),
                                  ('native_reference', validation['native_reference'])):
            if analysis and analysis['metrics'][key] is not None:
                candidates.append({'source': source, 'value': analysis['metrics'][key]})
        derived = validation['report'].get('derived_metrics', {}).get(key)
        if derived:
            candidates.append({'source': 'native_calculation', 'value': derived['value'],
                               'formula': derived['formula'], 'operands': deepcopy(derived['operands'])})
        reported_state = validation['report']['availability'][key]
        tolerance = 0 if key in COUNT_METRICS else 0.01
        if candidates and any(abs(c['value']-candidates[0]['value']) > tolerance+1e-10 for c in candidates[1:]):
            conflicts.add(key)
        if provenance_invalid or key in conflicts:
            value, source, state = None, None, 'conflicting'
        elif reported_state in ('not_applicable', 'undefined', 'infinite'):
            value, source, state = None, None, reported_state
        elif candidates:
            value, source = candidates[0]['value'], candidates[0]['source']
            state = 'derived' if source == 'native_calculation' else 'available'
        else:
            value, source, state = None, None, reported_state
        metrics[key] = {'value': value, 'source': source, 'availability': state,
                        'report_availability': reported_state, 'candidates': candidates}
        if value is None:
            warnings.append('metric_' + state + ':' + key)
    periods = deepcopy(validation['report']['period_results'])
    if periods is None:
        warnings.append('period_results_unavailable')
    warnings.extend(validation['issues'])
    warnings.extend('report:' + issue for issue in validation['report']['issues'])
    has_external = journal is not None or native_reference is not None
    counts = dict(Counter(c['status'] for c in checks))
    if validation['status'] == 'divergent' or provenance_invalid or conflicts:
        integrity = 'divergent'
    elif not has_external:
        integrity = 'not_reconciled'
    else:
        integrity = 'verified' if validation['status'] == 'verified' else 'partial'
    usable = sum(item['value'] is not None for item in metrics.values())
    incomplete = any(metrics[k]['value'] is None and metrics[k]['availability'] not in (
                     'not_applicable', 'undefined', 'infinite') for k in CORE_METRICS)
    source_incomplete = isinstance(report, dict) and (report.get('complete') is False or report.get('ok') is False)
    truncated = isinstance(journal, dict) and journal.get('truncated') is True
    if integrity == 'divergent' or provenance_invalid:
        quality = 'invalid'
    elif not usable:
        quality = 'unavailable'
    elif incomplete or source_incomplete or truncated or any(v is None for v in scenario.values()) or strategy_inputs is None or status != 'completed' or any(
            item['report_availability']=='inconclusive' for item in metrics.values()):
        quality = 'partial'
    else:
        quality = 'complete'
    if status != 'completed':
        warnings.append('execution_not_completed:' + status)
    warnings.append('history_quality_is_reported_not_independent_verification')
    declared_synthetic = isinstance(report,dict) and (
        str(report.get('fixture_kind','')).upper().startswith('SYNTHETIC') or report.get('evidence_kind')=='synthetic')
    return {'schema_version': SCHEMA_VERSION, 'artifact_type': 'run_summary',
            'evidence_kind': 'synthetic' if synthetic or declared_synthetic else ('simulation' if status == 'simulated' else 'observed'),
            'run_id': run_id, 'local_run_id': local_run_id,
            'execution': {'status': status, **timings},
            'strategy': {'expert': expert, 'inputs': strategy_inputs},
            'parameters': scenario, 'parameter_provenance': 'field_level_traceability',
            'traceability':traceability,
            'data_context': context, 'metrics': metrics, 'period_results': periods,
            'data_quality': {'classification': quality, 'available_metrics': usable,
                             'total_metrics': len(metrics), 'profitability_assessed': False},
            'reconciliation': {'classification': integrity, 'validation_status': validation['status'],
                               'check_counts': counts, 'checks': deepcopy(checks),
                               'external_scope_asserted_by_caller': has_external},
            'warnings': sorted(set(warnings))}


def summarize_directory(directory, *, journal=None, journal_run_id=None, inputs=None, data_context=None,
                        tester_ini=None,inputs_set=None,history_snapshot=None,symbol_snapshot=None):
    """Read known artifacts only. Do not scan logs or follow remote inputs_path."""
    root = Path(directory)
    if not root.is_dir():
        raise ValueError('run directory does not exist')
    def optional(name, default):
        path = root / name
        return read_artifact(path) if path.exists() else default
    remote = optional('remote_run.json', {})
    return summarize_run(optional('report.json', None), parameters=optional('request.json', {}),
            run_id=remote.get('run_id'), local_run_id=root.name,
            execution=optional('result.json', {'status': 'failed' if (root/'failure.json').exists() else 'unknown'}),
            journal=journal, journal_run_id=journal_run_id, inputs=inputs, data_context=data_context,
            tester_ini=tester_ini,inputs_set=inputs_set,history_snapshot=history_snapshot,symbol_snapshot=symbol_snapshot)


def compare_runs(summaries):
    """Build a comparison collection, never rank, schedule or execute tests."""
    summaries = list(summaries)
    seen = set()
    for item in summaries:
        if not isinstance(item,dict):
            raise ValueError('summary must be an object')
        if item.get('schema_version') not in ('1.0',SCHEMA_VERSION) or item.get('artifact_type') != 'run_summary':
            raise ValueError('unsupported summary schema')
        required = ('parameters','data_context','execution','data_quality','reconciliation','strategy','metrics')
        if any(not isinstance(item.get(key),dict) for key in required):
            raise ValueError('incomplete summary schema')
        if item.get('evidence_kind') not in ('observed','simulation','synthetic') or item['execution'].get('status') not in (
                'completed','failed','simulated','unknown') or item['data_quality'].get('classification') not in (
                'complete','partial','unavailable','invalid') or item['reconciliation'].get('classification') not in (
                'verified','partial','not_reconciled','divergent'):
            raise ValueError('invalid summary classification')
        normalized_parameters,_ = clean_parameters(item['parameters'])
        if normalized_parameters != item['parameters']:
            raise ValueError('invalid comparison parameters')
        normalized_context,_ = clean_context(item['data_context'])
        if normalized_context != item['data_context']:
            raise ValueError('invalid comparison context')
        clean_inputs(item['strategy'].get('inputs'))
        if item.get('schema_version')==SCHEMA_VERSION:
            trace=item.get('traceability')
            if not isinstance(trace,dict) or trace.get('schema_version')!='1.0' or not all(
                    isinstance(trace.get(key),dict) for key in ('parameters','tester_settings','inputs','costs','history','readiness')):
                raise ValueError('missing or invalid field traceability')
            if trace.get('classification') not in ('confirmed','partial','divergent') or any(
                    type(trace['readiness'].get(key)) is not bool for key in (
                    'parameters','inputs','cost_configuration','history_content','tester_settings')):
                raise ValueError('invalid traceability readiness')
            for group,fields in (('parameters',TRACE_PARAMETERS),('tester_settings',TRACE_SETTINGS),
                                 ('costs',COSTS),('history',HISTORY),('inputs',tuple(trace['inputs']))):
                for key in fields:
                    cell=trace[group].get(key)
                    if not isinstance(cell,dict) or cell.get('status') not in (
                            'confirmed','mismatch','conflicting','unverifiable') or (
                            (cell.get('confirmed') is not None) != (cell.get('status') in ('confirmed','mismatch'))):
                        raise ValueError('inconsistent traceability field')
                    if cell.get('confirmed') is not None and not scalar(cell['confirmed']):
                        raise ValueError('invalid confirmed value')
        for key in ALIASES:
            metric = item['metrics'].get(key)
            if not isinstance(metric,dict) or 'value' not in metric:
                raise ValueError('incomplete summary metrics')
            value = metric['value']
            availability = metric.get('availability')
            if availability not in ('available','derived','conflicting','unavailable','inconclusive',
                                     'infinite','undefined','not_applicable') or (
                    (value is not None) != (availability in ('available','derived'))):
                raise ValueError('inconsistent metric availability')
            if value is not None and (type(value) not in (int,float) or not math.isfinite(value)):
                raise ValueError('comparison requires finite numeric metrics')
        identity = item.get('run_id') or item.get('local_run_id')
        if not identity or identity in seen:
            raise ValueError('missing or duplicate run identity')
        seen.add(identity)
    pairs = []
    for index, left in enumerate(summaries):
        for right in summaries[index + 1:]:
            missing = [key for key in SCENARIO_FIELDS if left['parameters'].get(key) is None or right['parameters'].get(key) is None]
            different = [key for key in SCENARIO_FIELDS if key not in missing and left['parameters'][key] != right['parameters'][key]]
            missing_context = [key for key in CONTEXT_FIELDS if left['data_context'].get(key) is None or right['data_context'].get(key) is None]
            different_context = [key for key in CONTEXT_FIELDS if key not in missing_context and left['data_context'][key] != right['data_context'][key]]
            reasons = ['missing_parameter:' + k for k in missing] + ['different_parameter:' + k for k in different]
            reasons += ['missing_context:' + k for k in missing_context] + ['different_context:' + k for k in different_context]
            trace_ready=False
            trace_comparison={}
            a,b=left.get('traceability'),right.get('traceability')
            if a is None or b is None:
                reasons.append('legacy_traceability_unavailable')
            else:
                for group in ('parameters','inputs','tester_settings','costs','history'):
                    rows={}
                    for key in sorted(set(a[group])|set(b[group])):
                        av,bv=a[group].get(key,{}).get('confirmed'),b[group].get(key,{}).get('confirmed')
                        rows[key]={'left_confirmed':av,'right_confirmed':bv,
                            'classification':'unverifiable' if av is None or bv is None else (
                                'same' if equivalent(av,bv) else 'different')}
                    trace_comparison[group]=rows
                trace_ready=all(trace['readiness'].get(key) is True for trace in (a,b) for key in (
                    'parameters','inputs','cost_configuration','history_content','tester_settings'))
                if not trace_ready:
                    reasons.append('effective_configuration_or_history_or_costs_unverified')
                for key in SCENARIO_FIELDS:
                    av,bv=a['parameters'][key]['confirmed'],b['parameters'][key]['confirmed']
                    if av is not None and bv is not None and not equivalent(av,bv):
                        reasons.append('different_effective_parameter:'+key)
                        different.append(key)
                for group,key in (('history','content_sha256'),('costs','configuration_sha256'),('costs','currency'),('tester_settings','terminal_build')):
                    av,bv=a[group][key]['confirmed'],b[group][key]['confirmed']
                    if av is None or bv is None:
                        trace_ready=False
                        reasons.append('unverified_effective_context:'+key)
                    elif not equivalent(av,bv):
                        different_context.append(key)
                        reasons.append('different_effective_context:'+key)
                for trace in (a,b):
                    if not (trace['tester_settings']['use_local']['confirmed'] is True and
                            trace['tester_settings']['use_remote']['confirmed'] is False and
                            trace['tester_settings']['use_cloud']['confirmed'] is False):
                        trace_ready=False
                        reasons.append('effective_agents_not_fully_confirmed')
            if left['evidence_kind'] != right['evidence_kind']:
                reasons.append('different_evidence_kind')
            if any(s['execution']['status'] != 'completed' or s['data_quality']['classification'] in ('invalid', 'unavailable') for s in (left, right)):
                classification = 'excluded'
                reasons.append('execution_or_evidence_not_usable')
            elif different or different_context or 'different_evidence_kind' in reasons:
                classification = 'not_comparable'
            elif missing:
                classification = 'insufficient_context'
            elif not trace_ready or missing_context or any(s['reconciliation']['classification'] != 'verified' or s['data_quality']['classification'] != 'complete' or s['strategy']['inputs'] is None for s in (left, right)):
                classification = 'conditional'
                reasons.append('partial_or_unreconciled_evidence')
            else:
                classification = 'comparable'
            deltas = {}
            for key in ALIASES:
                a, b = left['metrics'][key]['value'], right['metrics'][key]['value']
                deltas[key] = b-a if classification == 'comparable' and a is not None and b is not None else None
            pairs.append({'left': left['run_id'] or left['local_run_id'], 'right': right['run_id'] or right['local_run_id'],
                          'classification': classification, 'reasons': sorted(set(reasons)),
                          'traceability_comparison':trace_comparison,'delta_right_minus_left': deltas})
    return {'schema_version': SCHEMA_VERSION, 'artifact_type': 'run_comparison', 'runs': deepcopy(summaries),
            'pairs': pairs, 'ranking': None, 'execution_enabled': False,
            'warnings': ['quality_and_integrity_do_not_assess_profitability',
                         'requested_parameters_and_context_require_independent_audit']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    summarize = commands.add_parser('summarize')
    summarize.add_argument('directory', type=Path)
    summarize.add_argument('--journal', type=Path)
    summarize.add_argument('--journal-run-id')
    summarize.add_argument('--inputs', type=Path)
    summarize.add_argument('--context', type=Path)
    summarize.add_argument('--tester-ini',type=Path)
    summarize.add_argument('--inputs-set',type=Path)
    summarize.add_argument('--history-snapshot',type=Path)
    summarize.add_argument('--symbol-snapshot',type=Path)
    summarize.add_argument('--output', required=True, type=Path)
    compare = commands.add_parser('compare')
    compare.add_argument('summaries', nargs='+', type=Path)
    compare.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.command == 'summarize':
        result = summarize_directory(args.directory,
            journal=read_artifact(args.journal) if args.journal else None,
            journal_run_id=args.journal_run_id, inputs=read_artifact(args.inputs) if args.inputs else None,
            data_context=read_artifact(args.context) if args.context else None,
            tester_ini=read_text_artifact(args.tester_ini) if args.tester_ini else None,
            inputs_set=read_text_artifact(args.inputs_set) if args.inputs_set else None,
            history_snapshot=read_artifact(args.history_snapshot) if args.history_snapshot else None,
            symbol_snapshot=read_artifact(args.symbol_snapshot) if args.symbol_snapshot else None)
    else:
        result = compare_runs(read_artifact(path) for path in args.summaries)
    write_artifact(args.output, result)
    print(args.output)


if __name__ == '__main__':
    main()
