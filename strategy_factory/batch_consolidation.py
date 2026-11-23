"""Consolidate existing audited summaries without modifying or ranking them."""
from copy import deepcopy

from .analysis import compare_runs
from .batch_manifest import fingerprint


def consolidate(summaries, *, small_sample_threshold=30):
    if type(small_sample_threshold) is not int or small_sample_threshold<1:
        raise ValueError('positive sample threshold required')
    summaries=list(summaries)
    if not summaries or any(s.get('schema_version')!='1.1' or not isinstance(s.get('execution_audit'),dict) for s in summaries):
        raise ValueError('audited summary 1.1 required')
    comparison=compare_runs(summaries)
    rows=[]
    for summary in summaries:
        audit=summary['execution_audit']
        if audit.get('schema_version')!='1.0' or audit.get('artifact_type')!='execution_audit' or audit.get('run_id')!=summary.get('run_id') or audit.get('status') not in ('consistent','partial','inconsistent'):
            raise ValueError('invalid or unrelated execution audit')
        trace=summary['traceability']
        trades=summary['metrics']['trades']['value']
        rows.append(dict(identity=summary.get('run_id') or summary['local_run_id'],
            summary_sha256=fingerprint(summary), metrics=deepcopy(summary['metrics']),
            reported_mt5_net_profit=deepcopy(summary['metrics']['net_profit']),
            costs=deepcopy(trace['costs']), history=deepcopy(trace['history']),
            effective_period={k:deepcopy(trace['parameters'][k]) for k in ('from_date','to_date')},
            execution_audit=deepcopy(summary['execution_audit']),
            all_costs_net_profit=None, effective_margin=None,
            sample_status='unknown' if trades is None else ('small' if trades<small_sample_threshold else 'threshold_met_not_validation'),
            unverified_costs=[k for k,v in trace['costs'].items() if v['status']!='confirmed']))
    return dict(schema_version='1.1',artifact_type='audited_batch_consolidation',
                runs=deepcopy(summaries), rows=rows, pairs=comparison['pairs'],
                ranking=None, portfolio_total=None, execution_enabled=False,
                warnings=['commission_zero_does_not_prove_absence_of_costs',
                          'reported_net_is_not_net_after_all_real_costs',
                          'spread_and_slippage_must_not_be_deducted_twice',
                          'historical_results_do_not_guarantee_profitability',
                          'no_portfolio_or_definitive_ranking',
                          'sample_threshold_is_diagnostic_only'])
