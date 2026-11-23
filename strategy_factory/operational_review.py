"""Review-only checklist, scoped metadata and logical resource assessment."""
from copy import deepcopy
import math

from .batch_manifest import exact,fingerprint,timestamp,sha
from .batch_consolidation import consolidate
from .integration_policy import ResourcePolicy
from .period_planning import validate_candidate_periods
from .readiness import FIELDS

REVIEW_STATES=('READY_FOR_REVIEW','BLOCKED_MISSING_EVIDENCE','BLOCKED_SAFETY','REQUIRES_HUMAN_DECISION')
SAFETY_KEYS={'executor_disabled','tester_stopped','no_ambiguous_attempt','hashes_preserved','local_agents_only','single_active_limit'}
DECISIONS={'prospective_period_freeze','acceptance_thresholds','supervised_exclusive_window','logical_resource_risk'}
METADATA_FIELDS={'spread_model','commission_per_operation','slippage','required_margin','swap','short_rules',
                 'volume_minimum','volume_increment','tick_size','tick_value','currency','account_leverage','demo_restrictions'}
INTEGRATION_EVIDENCE={'human_consent_channel','real_transport_deadline','operational_recovery','runtime_binary_identity'}


def classify_metadata(symbol_document,account_document,*,observed_at):
    timestamp(observed_at)
    symbol=symbol_document['symbols'][0];account=account_document['account']
    if symbol.get('symbol')!='PETR4' or account.get('type')!='demo':raise ValueError('current PETR4 demo metadata required')
    hashes=dict(symbol=fingerprint(symbol_document),account=fingerprint(account_document))
    rows={}
    def row(name,value,status,note,source='symbol'):
        rows[name]=dict(value=deepcopy(value),classification=status,source=source,source_sha256=hashes[source],
            observed_at=observed_at,scope=dict(environment='demo',symbol='PETR4',effective_period=None),limitations=[note])
    row('spread_model',symbol.get('spread_float'),'partially_confirmed','Floating-spread metadata, not historical realized execution cost')
    for name in ('commission_per_operation','slippage','required_margin'):
        row(name,None,'unknown','No effective per-operation cost/margin evidence in allowed metadata')
    row('swap',{k:symbol.get(k) for k in ('swap_mode','swap_long','swap_short')},'partially_confirmed','Current declared rules do not prove complete historical cost model')
    row('short_rules',symbol.get('trade_mode_name'),'partially_confirmed','FULL or a simulated short does not establish borrowing/live eligibility')
    for name,key in (('volume_minimum','volume_min'),('volume_increment','volume_step'),('tick_size','tick_size'),('tick_value','tick_value')):
        value=symbol.get(key)
        valid=type(value) in (int,float) and math.isfinite(value) and value>0
        row(name,value,'confirmed' if valid else ('unknown' if value is None else 'incompatible'),'Confirmed only as current symbol metadata; future-period applicability unverified')
    row('currency',dict(profit=symbol.get('currency_profit'),margin=symbol.get('currency_margin'),account=account.get('currency')),
        'confirmed' if symbol.get('currency_profit')==symbol.get('currency_margin')==account.get('currency')=='BRL' else 'incompatible','Current demo currency only')
    row('account_leverage',account.get('leverage'),'unknown' if account.get('leverage') is None else 'partially_confirmed','Proposal leverage 1:1 is a tester setting, not proof of effective account margin',source='account')
    row('demo_restrictions',{k:account.get(k) for k in ('type','margin_mode','read_only')},'partially_confirmed','Account metadata does not enumerate all broker restrictions or authorize trading',source='account')
    return dict(schema_version='3.3D-1',checks=rows,live_execution_enabled=False,scope='current_metadata_not_effective_future_conditions')


def assess_resource_proposal(summaries,resources):
    if type(resources) is not ResourcePolicy:raise ValueError('typed resource policy required')
    collection=consolidate(summaries)
    elapsed=[s['execution'].get('elapsed_seconds') for s in collection['runs']]
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in elapsed):raise ValueError('observed elapsed time missing')
    envelope=len(elapsed)*(resources.timeout_attempt_seconds+resources.reconciliation_seconds)
    coherent=envelope<=resources.timeout_batch_seconds and all(v<=resources.timeout_attempt_seconds for v in elapsed)
    return dict(classification='partially_confirmed' if coherent else 'incompatible',logical_envelope_seconds=envelope,
        logical_envelope_fits_batch=envelope<=resources.timeout_batch_seconds,
        observed_elapsed_seconds=elapsed,observed_sum_seconds=sum(elapsed),observed_max_seconds=max(elapsed),
        observed_within_attempt_cap=all(v<=resources.timeout_attempt_seconds for v in elapsed),
        future_duration_forecast_validated=False,os_cpu_memory_limits_enforced=False,
        physical_watchdog_homologated=False,live_execution_enabled=False)


def review_checklist(readiness,period_proposal,*,metadata,integration_evidence,safety,decisions):
    """Every critical gap stays visible; human decisions cannot waive evidence."""
    exact(safety,SAFETY_KEYS,'safety observations');exact(decisions,DECISIONS,'review decisions')
    exact(readiness['checks'],FIELDS,'complete readiness checklist')
    exact(metadata['checks'],METADATA_FIELDS,'complete market metadata checklist')
    exact(integration_evidence,INTEGRATION_EVIDENCE,'complete operational integration evidence')
    rows=[]
    if any(d.get('live_execution_enabled') is not False for d in (readiness,period_proposal,metadata)):
        rows.append(dict(item='non_executable_artifacts',state='BLOCKED_SAFETY'))
    for key,value in safety.items():
        if value is not None and type(value) is not bool:raise ValueError('explicit boolean/unknown safety evidence required')
        rows.append(dict(item=key,state='READY_FOR_REVIEW' if value is True else ('BLOCKED_SAFETY' if value is False else 'BLOCKED_MISSING_EVIDENCE')))
    for key,cell in readiness['checks'].items():
        classification=cell.get('classification')
        if classification not in ('confirmed','partially_confirmed','unknown','incompatible'):raise ValueError('invalid readiness classification')
        evidence=cell.get('evidence',[])
        supported=bool(evidence) and all(f.get('source') in readiness.get('source_hashes',{}) for f in evidence)
        rows.append(dict(item=key,state='READY_FOR_REVIEW' if classification=='confirmed' and supported else ('BLOCKED_SAFETY' if classification=='incompatible' else 'BLOCKED_MISSING_EVIDENCE'),classification=classification))
    for key,cell in metadata['checks'].items():
        c=cell.get('classification')
        if c not in ('confirmed','partially_confirmed','unknown','incompatible'):raise ValueError('invalid metadata classification')
        sha(cell.get('source_sha256'))
        rows.append(dict(item='metadata_'+key,state='READY_FOR_REVIEW' if c=='confirmed' and cell.get('source_sha256') else ('BLOCKED_SAFETY' if c=='incompatible' else 'BLOCKED_MISSING_EVIDENCE')))
    for key,cell in integration_evidence.items():
        c=cell.get('classification')
        if c not in ('confirmed','partially_confirmed','unknown','incompatible'):raise ValueError('invalid integration classification')
        sha(cell.get('source_sha256'))
        rows.append(dict(item=key,state='READY_FOR_REVIEW' if c=='confirmed' and cell.get('source_sha256') else ('BLOCKED_SAFETY' if c=='incompatible' else 'BLOCKED_MISSING_EVIDENCE')))
    validate_candidate_periods(period_proposal['periods'])
    for stage,period in period_proposal['periods'].items():
        rows.append(dict(item='period_'+stage,state='BLOCKED_MISSING_EVIDENCE' if period is None or period.get('history_status')!='verified' else 'READY_FOR_REVIEW'))
    for key,value in decisions.items():
        if type(value) is not bool:raise ValueError('review decision status must be explicit')
        rows.append(dict(item=key,state='READY_FOR_REVIEW' if value else 'REQUIRES_HUMAN_DECISION'))
    priority=('BLOCKED_SAFETY','BLOCKED_MISSING_EVIDENCE','REQUIRES_HUMAN_DECISION','READY_FOR_REVIEW')
    overall=next(s for s in priority if any(r['state']==s for r in rows))
    return dict(schema_version='3.3D-1',classification=overall,checks=rows,
        readiness_sha256=fingerprint(readiness),periods_sha256=fingerprint(period_proposal),metadata_sha256=fingerprint(metadata),
        integration_evidence_sha256=fingerprint(integration_evidence),
        live_execution_enabled=False,authorization_granted=False,ready_for_review_is_not_execution_permission=True)
