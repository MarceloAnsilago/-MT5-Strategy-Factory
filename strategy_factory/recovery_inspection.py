"""Conservative read-only reconstruction of existing integration ledgers."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3

from .analysis import read_artifact
from .batch_manifest import fingerprint, identifier, sha
from .batch_safety import validate_plan
from .batch_control import RUN_TRANSITIONS, BATCH_TRANSITIONS, check_transition


def _decode(text):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result:raise ValueError('duplicate state key')
            result[key]=value
        return result
    result=json.loads(text,object_pairs_hook=unique)
    fingerprint(result)  # Reject NaN/infinity, including nested data.
    return result


def inspect_recovery(root,batch_id):
    """Never instantiate a controller, write, remove locks or start anything.

    A coherent ledger is not proof that a terminal is idle. Every outcome stays
    non-executable and requires fresh observations before any future proposal.
    """
    response=dict(schema_version='3.3C-1',artifact_type='recovery_inspection',
                  live_execution_enabled=False,automatic_restart=False,locks_released=False)
    try:
        identifier(batch_id)
        root=Path(root)
        database=root/'control.sqlite'
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as db:
            row=db.execute('SELECT manifest,digest,state FROM batches WHERE id=?',(batch_id,)).fetchone()
            if row is None:raise ValueError('missing batch')
            manifest,stored_hash,state=_decode(row[0]),row[1],_decode(row[2])
            plan=validate_plan(read_artifact(root/batch_id/'safe_plan.json'))
            safe=db.execute('SELECT digest FROM safe_plans WHERE id=?',(batch_id,)).fetchone()
            if (fingerprint(manifest)!=stored_hash or plan['manifest']!=manifest or not safe or safe[0]!=fingerprint(plan) or
                read_artifact(root/batch_id/'manifest.json')!=manifest):
                raise ValueError('manifest/safe plan mismatch')
            events=db.execute('SELECT seq,state FROM events WHERE batch=? ORDER BY seq',(batch_id,)).fetchall()
        if not events or _decode(events[-1][1])!=state:raise ValueError('last event differs from materialized state')
        expected={r['run_id'] for r in manifest['runs']}
        previous=None
        for _,encoded in events:
            current=_decode(encoded)
            if current.get('batch_id')!=batch_id or current.get('manifest_sha256')!=stored_hash or current.get('live_execution_enabled') is not False or set(current['runs'])!=expected:
                raise ValueError('incomplete event identity')
            check_transition(current['status'],current['status'],BATCH_TRANSITIONS)
            seen=set()
            for key,run in current['runs'].items():
                check_transition(run['status'],run['status'],RUN_TRANSITIONS)
                if not isinstance(run['attempts'],list) or len(run['attempts'])>manifest['budget']['max_attempts_per_test']:
                    raise ValueError('incomplete attempt list')
                for index,attempt in enumerate(run['attempts'],1):
                    request=attempt.get('request_sha256')
                    sha(request)
                    if (request is None or attempt.get('simulation_only') is not True or type(attempt.get('attempt')) is not int or
                        attempt['attempt']!=index or attempt.get('attempt_id',request)!=request or request in seen or
                        attempt.get('status') not in ('simulating','simulated','failed','interrupted')):
                        raise ValueError('incomplete, duplicate or unscoped attempt')
                    seen.add(request)
            if previous:
                check_transition(previous['status'],current['status'],BATCH_TRANSITIONS)
                for key,run in current['runs'].items():
                    old=previous['runs'][key]
                    check_transition(old['status'],run['status'],RUN_TRANSITIONS)
                    if len(run['attempts'])<len(old['attempts']):raise ValueError('attempt history removed')
                    for a,b in zip(old['attempts'],run['attempts']):
                        if a['request_sha256']!=b['request_sha256']:raise ValueError('attempt identity changed')
            previous=current
        ambiguous=(state.get('integration_blocked',False) or state['status'] in ('simulating','interrupted','cancel_requested') or
                   any(r.get('requires_reconciliation') or r['status']=='simulating' for r in state['runs'].values()))
        attempts=[dict(run_id=k,attempt=a['attempt'],attempt_id=a.get('attempt_id',a['request_sha256']),status=a['status'])
                  for k,r in state['runs'].items() for a in r['attempts']]
        return dict(response,classification='blocked_ambiguous' if ambiguous else 'requires_fresh_preflight',
                    batch_status=state['status'],state_sha256=fingerprint(state),plan_sha256=fingerprint(plan),
                    event_count=len(events),attempts=attempts,
                    manual_review_required=any(r.get('requires_reconciliation') and not r['attempts'] for r in state['runs'].values()))
    except Exception as exc:
        return dict(response,classification='blocked_incomplete',error_type=type(exc).__name__,manual_review_required=True)
