"""Versioned, unverified datasets, exposure registry and stale-evidence checks."""
from copy import deepcopy
from datetime import date,datetime,timezone
import hashlib
from pathlib import Path

from .analysis import compare_runs
from .batch_manifest import fingerprint,exact,identifier,timestamp,sha
from .period_planning import validate_candidate_periods

CONDITIONS=('commission','spread','slippage','swap','required_margin','short_restrictions')


def empty_broker_conditions():
    """Association contract only, never a financial estimator."""
    return dict(schema_version='3.3E-conditions-1',environment='demo',conditions_version=None,
        observed_at=None,effective_from=None,effective_to=None,source_sha256=None,
        **{key:None for key in CONDITIONS})


def validate_conditions(document):
    exact(document,{'schema_version','environment','conditions_version','observed_at','effective_from','effective_to','source_sha256',*CONDITIONS},'dataset broker conditions')
    if document['schema_version']!='3.3E-conditions-1' or document['environment'] not in ('demo','real'):
        raise ValueError('explicit environment and conditions schema required')
    for key in ('observed_at','effective_from','effective_to'):
        if document[key] is not None:timestamp(document[key])
    sha(document['source_sha256'])
    if document['conditions_version'] is not None and (not isinstance(document['conditions_version'],str) or not document['conditions_version']):
        raise ValueError('conditions version must be explicit or unknown')
    if any(document[k] is not None for k in CONDITIONS):
        if not isinstance(document['conditions_version'],str) or not document['conditions_version'] or any(document[k] is None for k in ('source_sha256','observed_at','effective_from','effective_to')):
            raise ValueError('observed condition values require version, source and dated effective scope')
        if timestamp(document['effective_from'])>=timestamp(document['effective_to']):raise ValueError('invalid conditions effective interval')
    fingerprint(document)  # Non-finite values cannot become evidence.
    return deepcopy(document)


def _validate_exposures(exposures):
    if not isinstance(exposures,list):raise ValueError('explicit exposure registry required')
    seen=set()
    for e in exposures:
        exact(e,{'exposure_id','kind','from_date','to_date','strategy_ids','source_sha256','known_at'},'exposure')
        identifier(e['exposure_id']);sha(e['source_sha256'])
        if e['exposure_id'] in seen or e['source_sha256'] is None or e['kind'] not in ('data_access','warmup_access','strategy_results') or not isinstance(e['strategy_ids'],list):raise ValueError('invalid exposure provenance')
        seen.add(e['exposure_id'])
        for strategy_id in e['strategy_ids']:identifier(strategy_id)
        if e['kind']=='strategy_results' and not e['strategy_ids']:raise ValueError('result exposure must identify strategies')
        if date.fromisoformat(e['from_date'])>=date.fromisoformat(e['to_date']):raise ValueError('invalid exposure interval')
        if e['known_at'] is not None:timestamp(e['known_at'])


def build_dataset_manifest(collection,*,exposures,conditions=None,reviewed_at,valid_until=None,previous_dataset_version=None):
    timestamp(reviewed_at)
    if valid_until is not None and timestamp(valid_until)<=timestamp(reviewed_at):raise ValueError('invalid review validity window')
    if collection.get('schema_version')!='3.3E-collection-1' or collection.get('coverage_certified') is not False:
        raise PermissionError('only observed, non-certified collections can be registered')
    _validate_exposures(exposures)
    sha(previous_dataset_version)
    body=dict(schema_version='3.3E-dataset-1',collection_sha256=fingerprint(collection),
        sources=deepcopy(collection['sources']),exposures=deepcopy(exposures),
        exposure_registry_sha256=fingerprint(exposures),broker_conditions=validate_conditions(conditions or empty_broker_conditions()),
        reviewed_at=reviewed_at,valid_until=valid_until,coverage_certified=False,live_execution_enabled=False,
        certification_status='unverified',classification=collection['classification'],previous_dataset_version=previous_dataset_version)
    return dict(body,dataset_version=fingerprint(body))


def validate_dataset_manifest(manifest):
    required={'schema_version','collection_sha256','sources','exposures','exposure_registry_sha256',
              'broker_conditions','reviewed_at','valid_until','coverage_certified','live_execution_enabled',
              'certification_status','classification','dataset_version','previous_dataset_version'}
    exact(manifest,required,'dataset manifest')
    if manifest['schema_version']!='3.3E-dataset-1' or manifest['coverage_certified'] is not False or manifest['certification_status']!='unverified' or manifest['live_execution_enabled'] is not False:
        raise PermissionError('unverified data cannot be promoted or enable execution')
    if fingerprint({k:v for k,v in manifest.items() if k!='dataset_version'})!=manifest['dataset_version'] or fingerprint(manifest['exposures'])!=manifest['exposure_registry_sha256']:
        raise ValueError('dataset or exposure registry changed')
    validate_conditions(manifest['broker_conditions']);timestamp(manifest['reviewed_at']);_validate_exposures(manifest['exposures'])
    sha(manifest['previous_dataset_version'])
    if manifest['valid_until'] is not None and timestamp(manifest['valid_until'])<=timestamp(manifest['reviewed_at']):raise ValueError('invalid dataset validity window')
    if manifest['classification'] not in ('invalid','observed_partial') or not isinstance(manifest['sources'],list) or not manifest['sources']:
        raise ValueError('explicit unverified source collection required')
    return deepcopy(manifest)


def revise_dataset_manifest(previous,collection,*,exposures,conditions=None,reviewed_at,valid_until=None):
    """New immutable revision; previous exposure cannot be removed or rewritten."""
    previous=validate_dataset_manifest(previous);_validate_exposures(exposures)
    current={e['exposure_id']:e for e in exposures}
    if any(e['exposure_id'] not in current or fingerprint(e)!=fingerprint(current[e['exposure_id']]) for e in previous['exposures']):
        raise PermissionError('prior exposure history is append-only')
    return build_dataset_manifest(collection,exposures=exposures,
        conditions=conditions if conditions is not None else previous['broker_conditions'],
        reviewed_at=reviewed_at,valid_until=valid_until,previous_dataset_version=previous['dataset_version'])


def revalidate_dataset(manifest,source_paths,*,expected_version,expected_exposure_sha256,expected_conditions_version,now=None):
    manifest=validate_dataset_manifest(manifest);blockers=[];changed=[]
    if manifest['dataset_version']!=expected_version:blockers.append('dataset_version_changed')
    if manifest['exposure_registry_sha256']!=expected_exposure_sha256:blockers.append('exposure_registry_changed')
    if manifest['broker_conditions']['conditions_version']!=expected_conditions_version:blockers.append('broker_conditions_version_changed')
    for source in manifest['sources']:
        try:
            if source['file_sha256'] is None or hashlib.sha256(Path(source_paths[source['source_id']]).read_bytes()).hexdigest()!=source['file_sha256']:
                changed.append(source['source_id'])
        except (KeyError,OSError):changed.append(source['source_id'])
    if changed:blockers.append('source_changed_or_missing')
    if manifest['classification']=='invalid':blockers.append('history_integrity_invalid')
    if (now or datetime.now(timezone.utc))<timestamp(manifest['reviewed_at']):blockers.append('review_not_yet_valid')
    if manifest['valid_until'] is None:blockers.append('freshness_policy_not_approved')
    elif (now or datetime.now(timezone.utc))>=timestamp(manifest['valid_until']):blockers.append('review_expired')
    if any(s['capture_time'] is None for s in manifest['sources']):blockers.append('source_capture_time_unknown')
    return dict(classification='STALE_OR_INCOMPLETE' if blockers else 'CONSISTENT_UNVERIFIED',
                blockers=blockers,changed_sources=changed,coverage_certified=False,live_execution_enabled=False)


def assess_period_data(collection,manifest,periods,*,model,warmup_bars=53):
    manifest=validate_dataset_manifest(manifest);periods=validate_candidate_periods(periods)
    if model not in ('every tick','real ticks'):raise ValueError('model must explicitly distinguish generated and broker ticks')
    if type(warmup_bars) is not int or warmup_bars<53:raise ValueError('existing indicator guard requires at least 53 bars')
    if fingerprint(collection)!=manifest['collection_sha256']:raise ValueError('collection changed')
    stages={}
    for stage,period in periods.items():
        blockers=[]
        if period is None:
            stages[stage]=dict(classification='BLOCKED_MISSING_EVIDENCE',blockers=['period_missing'],warmup_bars=0,evaluation_bars=0)
            continue
        bars=[r for s in collection['series'] if s['timeframe']=='M5' for r in s['records']]
        if len({s['date_basis'] for s in collection['series'] if s['timeframe']=='M5'})>1:
            blockers.append('multiple_time_bases_require_explicit_selection');bars=[]
        warmup=sum(period['warmup_from']<=r['local_date']<period['from_date'] for r in bars)
        evaluated=sum(period['from_date']<=r['local_date']<period['to_date'] for r in bars)
        if warmup<warmup_bars:blockers.append('insufficient_observed_M5_warmup')
        if not evaluated:blockers.append('no_observed_M5_evaluation_bars')
        needed=[r for s in collection['series'] if (s['timeframe']=='M1' if model=='every tick' else s['kind']=='broker_ticks') for r in s['records'] if period['warmup_from']<=r['local_date']<period['to_date']]
        if not needed:blockers.append('M1_missing_for_generated_ticks' if model=='every tick' else 'broker_ticks_missing')
        else:blockers.append('model_input_session_completeness_unverified')
        if model=='real ticks' and not any(s['timeframe']=='M1' and any(period['warmup_from']<=r['local_date']<period['to_date'] for r in s['records']) for s in collection['series']):
            blockers.append('M1_missing_for_real_tick_consistency_and_fallback_detection')
        if any(s['timezone']=='unknown' for s in collection['series']):blockers.append('broker_timezone_unverified')
        if collection['classification']=='invalid':blockers.append('history_integrity_invalid')
        for exposure in manifest['exposures']:
            if period['warmup_from']<exposure['to_date'] and period['to_date']>exposure['from_date']:
                if stage=='final_test' and exposure['kind']=='strategy_results':blockers.append('known_results_in_final_period')
                else:blockers.append('prior_exposure_requires_review')
        blockers.extend(('session_calendar_unverified','data_origin_and_capture_unverified','sample_trade_count_not_established'))
        stages[stage]=dict(classification='BLOCKED_SAFETY' if 'history_integrity_invalid' in blockers or 'known_results_in_final_period' in blockers else 'BLOCKED_MISSING_EVIDENCE',
            warmup_bars=warmup,evaluation_bars=evaluated,model_input_records=len(needed),
            observed_evaluation_days=len({r['local_date'] for r in bars if period['from_date']<=r['local_date']<period['to_date']}),
            blockers=sorted(set(blockers)))
    return dict(schema_version='3.3E-period-review-1',model=model,stages=stages,
        dataset_version=manifest['dataset_version'],coverage_certified=False,ready_for_execution=False,live_execution_enabled=False)


def attach_history_review(summary,review):
    """Add retrospective review only; never claim a runtime dataset fingerprint."""
    if summary.get('schema_version')!='1.1':raise ValueError('summary 1.1 required')
    compare_runs([summary])
    exact(review,{'schema_version','run_id','parameters_sha256','dataset_version','classification','coverage_certified','live_execution_enabled','details'},'retrospective dataset review')
    if review['schema_version']!='3.3E-run-review-1' or review.get('run_id')!=summary.get('run_id') or review.get('live_execution_enabled') is not False or review['parameters_sha256']!=fingerprint(summary['parameters']):
        raise ValueError('review run scope mismatch')
    if review['coverage_certified'] is not False or review['classification'] not in ('BLOCKED_MISSING_EVIDENCE','BLOCKED_SAFETY','OBSERVED_UNVERIFIED'):
        raise PermissionError('dataset review cannot certify a historical run')
    sha(review['dataset_version'])
    if review['dataset_version'] is None or not isinstance(review['details'],dict):raise ValueError('versioned review details required')
    result=deepcopy(summary)
    result['dataset_review']=deepcopy(review)
    result['dataset_review']['provenance']='retrospective_declared_dataset_not_runtime_proof'
    result['dataset_review']['runtime_dataset_verified']=False
    return result
