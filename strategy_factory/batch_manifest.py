"""Strict versioned batch plans and authorization records; no execution."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import uuid

from .analysis import clean_inputs
from .tester import BacktestConfig

VERSION='1.0'
POLICY=dict(simulation_default=True,environment='strategy_tester',optimization=False,
            forward_mode=0,local_agents_only=True,allow_live_trading=False,automatic_retries=False)
BUDGET_KEYS={'max_strategies','max_backtests','timeout_per_test_seconds','timeout_batch_seconds',
             'max_attempts_per_test','max_concurrency','max_artifact_bytes','max_run_artifact_bytes','min_free_disk_bytes'}
PARAMETERS={'symbol','timeframe','from_date','to_date','deposit','currency','model','leverage','execution_delay'}


def fingerprint(value):
    raw=json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def exact(value,keys,label):
    if not isinstance(value,dict) or set(value)!=set(keys):
        raise ValueError('invalid fields: '+label)


def identifier(value):
    if not isinstance(value,str) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,63}',value):
        raise ValueError('invalid identifier')


def sha(value):
    if value is not None and (not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value)):
        raise ValueError('invalid SHA256')


def validate_manifest(document):
    """Validate before side effects. Unknown keys/credentials are not persisted."""
    exact(document,{'schema_version','batch_id','revision','policy','budget','strategies','runs'},'manifest')
    if document['schema_version']!=VERSION:
        raise ValueError('unsupported manifest version')
    identifier(document['batch_id'])
    if type(document['revision']) is not int or document['revision']<1:
        raise ValueError('invalid revision')
    if document['policy']!=POLICY or any(type(document['policy'].get(k)) is not type(v) for k,v in POLICY.items()):
        raise ValueError('only tester-only, local, non-optimization policy is supported')
    budget=document['budget']
    exact(budget,BUDGET_KEYS,'budget')
    for key,value in budget.items():
        if type(value) is not int or value<(0 if key=='min_free_disk_bytes' else 1):
            raise ValueError('invalid budget: '+key)
    if budget['max_concurrency']!=1:
        raise ValueError('only one worker per terminal is supported')
    if budget['max_run_artifact_bytes']>budget['max_artifact_bytes']:
        raise ValueError('per-run storage exceeds batch storage')
    strategies,runs=document['strategies'],document['runs']
    if not isinstance(strategies,list) or not strategies or len(strategies)>budget['max_strategies']:
        raise ValueError('strategy limit exceeded or empty strategies')
    if not isinstance(runs,list) or not runs or len(runs)*budget['max_attempts_per_test']>budget['max_backtests']:
        raise ValueError('backtest/attempt limit exceeded or empty runs')
    # Reserve the full worst-case attempt envelope; no optimistic runtime assumptions.
    if len(runs)*budget['max_attempts_per_test']*budget['timeout_per_test_seconds']>budget['timeout_batch_seconds']:
        raise ValueError('batch timeout cannot cover the declared attempt envelope')
    strategy_ids={}
    for item in strategies:
        exact(item,{'strategy_id','version','ea'},'strategy')
        identifier(item['strategy_id'])
        if item['strategy_id'] in strategy_ids:
            raise ValueError('duplicate strategy ID')
        if not isinstance(item['version'],str) or not re.fullmatch('[A-Za-z0-9_.-]{1,64}',item['version']):
            raise ValueError('invalid strategy version')
        exact(item['ea'],{'path','compiled_sha256','source_sha256'},'ea')
        sha(item['ea']['compiled_sha256'])
        sha(item['ea']['source_sha256'])
        strategy_ids[item['strategy_id']]=item
    run_ids,scenarios=set(),set()
    for item in runs:
        exact(item,{'run_id','strategy_id','parameters','inputs'},'run')
        identifier(item['run_id'])
        if item['run_id'] in run_ids or item['strategy_id'] not in strategy_ids:
            raise ValueError('duplicate run ID or unknown strategy')
        run_ids.add(item['run_id'])
        exact(item['parameters'],PARAMETERS,'parameters')
        clean_inputs(item['inputs'])
        if item['inputs'] is None:
            raise ValueError('explicit EA inputs required; use {} for no inputs')
        try:
            BacktestConfig(expert=strategy_ids[item['strategy_id']]['ea']['path'],**item['parameters'])
        except (TypeError,ValueError,OverflowError):
            raise ValueError('invalid EA or backtest parameters') from None
        signature=fingerprint({k:v for k,v in item.items() if k!='run_id'})
        if signature in scenarios:
            raise ValueError('duplicate strategy/scenario/inputs')
        scenarios.add(signature)
    return deepcopy(document)


def approval_phrase(manifest):
    document=validate_manifest(manifest)
    return 'AUTORIZO LOTE TESTER '+document['batch_id']+' SHA256 '+fingerprint(document)


def timestamp(value):
    if not isinstance(value,str):
        raise ValueError('timestamp must contain UTC offset')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:
        raise ValueError('timezone required')
    return result.astimezone(timezone.utc)


def make_authorization(manifest,*,approval,approved_by,expires_at,permitted_attempts=None,now=None):
    """Record explicit intent only. This does not enable a live batch backend."""
    document=validate_manifest(manifest)
    if approval!=approval_phrase(document):
        raise PermissionError('explicit approval must match batch ID and exact manifest SHA256')
    identifier(approved_by)
    now=now or datetime.now(timezone.utc)
    record=dict(schema_version=VERSION,authorization_id=uuid.uuid4().hex,batch_id=document['batch_id'],
        manifest_sha256=fingerprint(document),scope='strategy_tester_backtests_only',allow_live_trading=False,
        automatic_retries=False,approved_by=approved_by,issued_at=now.isoformat(),expires_at=expires_at,
        permitted_attempts=permitted_attempts if permitted_attempts is not None else {r['run_id']:[1] for r in document['runs']})
    validate_authorization(document,record,now=now)
    return record


def validate_authorization(manifest,record,*,now=None):
    document=validate_manifest(manifest)
    exact(record,{'schema_version','authorization_id','batch_id','manifest_sha256','scope','allow_live_trading',
        'automatic_retries','approved_by','issued_at','expires_at','permitted_attempts'},'authorization')
    if record['schema_version']!=VERSION or record['batch_id']!=document['batch_id'] or record['manifest_sha256']!=fingerprint(document):
        raise PermissionError('authorization does not match validated manifest')
    if record['scope']!='strategy_tester_backtests_only' or record['allow_live_trading'] is not False or record['automatic_retries'] is not False:
        raise PermissionError('authorization scope forbidden')
    identifier(record['authorization_id'])
    identifier(record['approved_by'])
    issued,expires=timestamp(record['issued_at']),timestamp(record['expires_at'])
    current=now or datetime.now(timezone.utc)
    if not issued<=current<expires:
        raise PermissionError('authorization not yet valid or expired')
    permits=record['permitted_attempts']
    if not isinstance(permits,dict) or not permits:
        raise ValueError('explicit attempt permits required')
    run_ids={r['run_id'] for r in document['runs']}
    for key,attempts in permits.items():
        if key not in run_ids or not isinstance(attempts,list) or not attempts:
            raise ValueError('invalid attempt scope')
        if any(type(n) is not int or not 1<=n<=document['budget']['max_attempts_per_test'] for n in attempts):
            raise ValueError('attempt outside budget')
        if len(set(attempts))!=len(attempts):
            raise ValueError('duplicate attempt permit')
    return True


def manifest_schema():
    """JSON Schema shape; arithmetic/domain checks remain in validate_manifest."""
    def obj(properties):
        return dict(type='object',properties=properties,required=list(properties),additionalProperties=False)
    text=dict(type='string',minLength=1)
    ident=dict(type='string',pattern='^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$')
    checksum=dict(type=['string','null'],pattern='^[0-9a-f]{64}$')
    budget={key:dict(type='integer',minimum=0 if key=='min_free_disk_bytes' else 1) for key in sorted(BUDGET_KEYS)}
    budget['max_concurrency']={'const':1}
    params={key:deepcopy(text) for key in sorted(PARAMETERS)}
    for key in ('deposit','leverage','execution_delay'):
        params[key]={'type':'number'}
    params['leverage']={'type':'integer','minimum':1}
    params['execution_delay']={'type':'integer','minimum':-1,'maximum':600000}
    params['deposit']={'type':'number','exclusiveMinimum':0}
    params['from_date']={'type':'string','pattern':'^\\d{4}-\\d{2}-\\d{2}$'}
    params['to_date']=deepcopy(params['from_date'])
    ea=obj(dict(path=dict(type='string',pattern='\\.[eE][xX]5$'),compiled_sha256=checksum,source_sha256=checksum))
    strategy=obj(dict(strategy_id=ident,version=dict(type='string',pattern='^[A-Za-z0-9_.-]{1,64}$'),ea=ea))
    run=obj(dict(run_id=ident,strategy_id=ident,parameters=obj(params),inputs=dict(type='object',additionalProperties=dict(type=['string','number','boolean']))))
    schema=obj(dict(schema_version={'const':VERSION},batch_id=ident,revision=dict(type='integer',minimum=1),
        policy={'const':POLICY},budget=obj(budget),strategies=dict(type='array',minItems=1,items=strategy),
        runs=dict(type='array',minItems=1,items=run)))
    schema['$schema']='https://json-schema.org/draft/2020-12/schema'
    schema['title']='MT5 Strategy Factory batch manifest 1.0'
    return deepcopy(schema)
