"""Phase 3.3A contracts layered over manifest 1.0. No operational adapter."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import ntpath
from pathlib import Path

from .batch_manifest import validate_manifest, fingerprint, exact, sha, timestamp, identifier

STAGES = ('development', 'out_of_sample', 'final_test')
SETTINGS = dict(optimization=False, genetic=False, forward_mode=0, visual=False,
                use_local=True, use_remote=False, use_cloud=False, profit_in_pips=False)
CONTROLS = dict(execution_enabled=False, authorization_scope='planning_only',
                automatic_retries=False, local_agents_only=True,
                exclusive_terminal_required=True, reconciliation_required=True)


def scenario_payload(manifest, run, stage):
    strategy=next(s for s in manifest['strategies'] if s['strategy_id']==run['strategy_id'])
    return dict(strategy=strategy, parameters=run['parameters'], inputs=run['inputs'],
                stage=stage, tester_settings=SETTINGS, resources=manifest['budget'],
                attempt_policy=dict(max_attempts=manifest['budget']['max_attempts_per_test'],
                                    automatic_retries=False))


def validate_plan(document):
    """Strict envelope; no missing identities, guessed history or implicit dates.

    Hashes assert document integrity, never runtime identity or human consent.
    Intervals are half-open. Warmup and evaluation may not reuse a prior stage.
    """
    exact(document, {'schema_version','manifest','controls','periods','scenarios'}, 'safe batch plan')
    if document['schema_version']!='3.3A-1':
        raise ValueError('unsupported safe plan version')
    manifest=validate_manifest(document['manifest'])
    if document['controls']!=CONTROLS or any(type(document['controls'][k]) is not type(v) for k,v in CONTROLS.items()):
        raise ValueError('execution must remain disabled; planning scope only')
    binaries=set()
    for strategy in manifest['strategies']:
        ea=strategy['ea']
        if ea['source_sha256'] is None or ea['compiled_sha256'] is None:
            raise ValueError('source and EX5 hashes required, even for dry-run')
        identity=(ntpath.normcase(ntpath.normpath(ea['path'])), ea['compiled_sha256'])
        if identity in binaries:
            raise ValueError('duplicate EA under another strategy ID')
        binaries.add(identity)
    periods=document['periods']
    exact(periods,STAGES,'independent periods')
    previous=None
    for stage in STAGES:
        interval=periods[stage]
        if interval is None:
            continue  # Structure can be prepared without choosing final periods.
        exact(interval, {'from_date','to_date','warmup_from','history_status','selection_basis'}, 'period')
        start,end,warmup=(date.fromisoformat(interval[k]) for k in ('from_date','to_date','warmup_from'))
        if any(date.fromisoformat(interval[k]).isoformat()!=interval[k] for k in ('from_date','to_date','warmup_from')):
            raise ValueError('canonical ISO dates required')
        if not warmup<=start<end or (previous is not None and warmup<previous):
            raise ValueError('overlapping periods or warmup leakage')
        if interval['history_status'] not in ('unverified','verified') or interval['selection_basis']!='prospective_not_result_selected':
            raise ValueError('history status and prospective selection must be explicit')
        previous=end
    scenarios=document['scenarios']
    if not isinstance(scenarios,list) or len(scenarios)!=len(manifest['runs']):
        raise ValueError('exact scenario coverage required')
    covered,signatures=set(),set()
    runs={r['run_id']:r for r in manifest['runs']}
    for item in scenarios:
        exact(item, {'run_id','stage','scenario_sha256'}, 'scenario')
        run_id=item['run_id']
        if run_id not in runs or run_id in covered or item['stage'] not in STAGES:
            raise ValueError('duplicate or invalid scenario identity/stage')
        covered.add(run_id)
        interval=periods[item['stage']]
        params=runs[run_id]['parameters']
        if interval is None or any(params[k]!=interval[k] for k in ('from_date','to_date')):
            raise ValueError('scenario period must match its declared stage')
        expected=fingerprint(scenario_payload(manifest,runs[run_id],item['stage']))
        sha(item['scenario_sha256'])
        if item['scenario_sha256']!=expected or expected in signatures:
            raise ValueError('incorrect or duplicate scenario hash')
        signatures.add(expected)
    return deepcopy(document)


def verify_ea_files(document):
    """Opt-in local byte check; does not compile or access the terminal."""
    plan=validate_plan(document)
    for strategy in plan['manifest']['strategies']:
        binary=Path(strategy['ea']['path'])
        for path,key in ((binary,'compiled_sha256'),(binary.with_suffix('.mq5'),'source_sha256')):
            if hashlib.sha256(path.read_bytes()).hexdigest()!=strategy['ea'][key]:
                raise ValueError('EA file hash mismatch')
    return True


def check_planning_authorization(document, record, *, run_id, attempt, consumed=(), now=None):
    """Check a supplied planning record; never mint an executable authorization.

    No Phase 3.2/manifest-1.0 authorization can satisfy this contract. A future
    execution backend needs a separate reviewed contract and human approval.
    """
    plan=validate_plan(document)
    if not isinstance(record,dict):
        raise PermissionError('fresh planning authorization required')
    exact(record, {'schema_version','scope','authorization_id','plan_sha256','controls_sha256',
                  'scenario_sha256','run_id','attempt','issued_at','expires_at'}, 'planning authorization')
    scenario=next((s for s in plan['scenarios'] if s['run_id']==run_id),None)
    if scenario is None or type(attempt) is not int or not 1<=attempt<=plan['manifest']['budget']['max_attempts_per_test']:
        raise PermissionError('attempt outside scope')
    if (run_id,attempt) in consumed:
        raise PermissionError('attempt already consumed')
    identifier(record['authorization_id'])
    if record['schema_version']!='3.3A-1' or record['scope']!='planning_only' or record['plan_sha256']!=fingerprint(plan) or record['controls_sha256']!=fingerprint(CONTROLS) or record['scenario_sha256']!=scenario['scenario_sha256'] or record['run_id']!=run_id or type(record['attempt']) is not int or record['attempt']!=attempt:
        raise PermissionError('authorization does not match plan, controls, scenario and attempt')
    current=now or datetime.now(timezone.utc)
    if not timestamp(record['issued_at'])<=current<timestamp(record['expires_at']):
        raise PermissionError('planning authorization expired or not yet valid')
    return dict(valid_for_planning=True, live_execution_enabled=False)


def execution_gate(*args, **kwargs):
    """Unconditional fail-closed gate, including for otherwise valid records."""
    raise PermissionError('phase 3.3A has no executable authorization or real batch backend')
