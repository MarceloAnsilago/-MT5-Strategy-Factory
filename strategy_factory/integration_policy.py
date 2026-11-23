"""Non-executable individual fixture contracts and evidence-based acceptance."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import math

from .batch_manifest import exact, fingerprint, timestamp, identifier
from .batch_safety import validate_plan
from .batch_consolidation import consolidate


@dataclass(frozen=True)
class ResourcePolicy:
    max_local_agents: int = 1
    max_active_per_terminal: int = 1
    timeout_attempt_seconds: int = 180
    timeout_batch_seconds: int = 360
    reconciliation_seconds: int = 45
    max_consecutive_failures: int = 1
    max_memory_bytes: int = 536870912
    max_cpu_percent: int = 100

    def __post_init__(self):
        if any(type(v) is not int or v<1 for v in asdict(self).values()):
            raise ValueError('resource limits must be positive integers')
        if self.max_active_per_terminal!=1 or self.max_cpu_percent>100:
            raise ValueError('one active run per terminal; CPU budget at most 100 percent')


@dataclass(frozen=True)
class AcceptanceCriteria:
    # None means unspecified, never a default approval threshold.
    min_trades: int | None = None
    max_equity_drawdown_percent: float | None = None
    max_balance_drawdown_percent: float | None = None

    def __post_init__(self):
        if self.min_trades is not None and (type(self.min_trades) is not int or self.min_trades<1):
            raise ValueError('minimum trades must be explicitly positive')
        for v in (self.max_equity_drawdown_percent,self.max_balance_drawdown_percent):
            if v is not None and (type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=100):
                raise ValueError('invalid drawdown limit')


def controls_digest(resources, criteria):
    return fingerprint(dict(resources=asdict(resources),acceptance=asdict(criteria),live_execution_enabled=False))


def check_individual_fixture(plan,record,*,run_id,attempt,resources,criteria,now=None):
    """Validate only synthetic, non-executable individual permission fixtures.

    No issuer is provided. Old, batch or planning approvals cannot satisfy this
    scope. Real approvals will require a separate reviewed issuance contract.
    """
    plan=validate_plan(plan)
    if not isinstance(record,dict):
        raise PermissionError('individual synthetic authorization missing')
    exact(record,{'schema_version','fixture_kind','scope','authorization_id','plan_sha256',
                  'controls_sha256','scenario_sha256','run_id','attempt','issued_at','expires_at'},'individual fixture')
    scenario=next((s for s in plan['scenarios'] if s['run_id']==run_id),None)
    if scenario is None or type(attempt) is not int or not 1<=attempt<=plan['manifest']['budget']['max_attempts_per_test']:
        raise PermissionError('attempt outside scenario budget')
    identifier(record['authorization_id'])
    if (record['schema_version']!='3.3B-1' or record['fixture_kind']!='synthetic_non_executable' or
        record['scope']!='simulation_individual_attempt' or record['plan_sha256']!=fingerprint(plan) or
        record['controls_sha256']!=controls_digest(resources,criteria) or record['scenario_sha256']!=scenario['scenario_sha256'] or
        record['run_id']!=run_id or type(record['attempt']) is not int or record['attempt']!=attempt):
        raise PermissionError('individual synthetic authorization scope/hash mismatch')
    if not timestamp(record['issued_at'])<=(now or datetime.now(timezone.utc))<timestamp(record['expires_at']):
        raise PermissionError('individual synthetic authorization expired or not yet valid')
    return True


def assess_acceptance(summary,plan,run_id,criteria):
    """Readiness diagnosis, never strategy approval or a profitability ranking."""
    plan=validate_plan(plan)
    consolidate([summary])  # Reuse summary 1.1 and matching audit validation.
    run=next(r for r in plan['manifest']['runs'] if r['run_id']==run_id)
    audit=summary.get('execution_audit',{})
    reasons=[]
    checks={}
    trades=summary['metrics']['trades']['value']
    checks['trades']='unverifiable' if criteria.min_trades is None or trades is None else ('met' if trades>=criteria.min_trades else 'not_met')
    for metric,limit in (('equity_drawdown_relative',criteria.max_equity_drawdown_percent),
                         ('balance_drawdown_relative',criteria.max_balance_drawdown_percent)):
        value=summary['metrics'][metric]['value']
        checks[metric]='unverifiable' if limit is None or value is None else ('met' if value<=limit else 'not_met')
    checks['scenario']='met' if summary['parameters']==run['parameters'] and summary['strategy']['inputs']==run['inputs'] else 'not_met'
    checks['audit']='met' if audit.get('status')=='consistent' else ('not_met' if audit.get('status')=='inconsistent' else 'unverifiable')
    trace=summary['traceability']
    checks['effective_configuration']='met' if all(trace['readiness'][k] for k in ('parameters','inputs','tester_settings')) else 'unverifiable'
    checks['history']='met' if trace['readiness']['history_content'] else 'unverifiable'
    checks['costs']='met' if trace['readiness']['cost_configuration'] and audit.get('costs_complete') is True else 'unverifiable'
    checks['margin']='unverifiable'
    checks['independent_periods']='met' if all(plan['periods'][s] is not None for s in ('development','out_of_sample','final_test')) else 'unverifiable'
    checks['execution']='met' if summary['execution']['status']=='completed' else 'not_met'
    for name,status in checks.items():
        if status!='met':reasons.append(name+':'+status)
    return dict(classification='criteria_not_met' if 'not_met' in checks.values() else ('insufficient_evidence' if reasons else 'ready_for_review'),
                checks=checks,reasons=reasons,strategy_approved=False,profitability_assessed=False,
                costs_complete=audit.get('costs_complete') is True,effective_margin=None)
