"""Four-way readiness from scoped evidence, never invented costs or margin."""
from copy import deepcopy
from datetime import date

from .batch_manifest import exact, fingerprint, timestamp

FIELDS=('history_sufficiency','period_integrity','tick_availability','commission','swap',
        'spread','slippage','margin_required','short_permission','volume_constraints','symbol_configuration')
SCOPE={'environment','symbol','from_date','to_date','model'}


def _validate_scope(scope):
    exact(scope,SCOPE,'readiness scope')
    if scope['environment'] not in ('demo','real'):raise ValueError('explicit environment required')
    if scope['symbol'] is not None and (not isinstance(scope['symbol'],str) or not scope['symbol'].strip()):
        raise ValueError('invalid symbol scope')
    if scope['model'] is not None and scope['model'] not in ('every tick','m1 ohlc','open prices','real ticks'):
        raise ValueError('invalid tick model scope')
    for key in ('from_date','to_date'):
        value=scope[key]
        if value is not None and (not isinstance(value,str) or date.fromisoformat(value).isoformat()!=value):
            raise ValueError('invalid period scope')
    if scope['from_date'] is not None and scope['to_date'] is not None and scope['from_date']>=scope['to_date']:
        raise ValueError('inverted period scope')


def _located(payload,locator):
    if not isinstance(locator,list) or not locator:raise ValueError('source locator required')
    for token in locator:
        if isinstance(payload,dict) and isinstance(token,str):payload=payload[token]
        elif isinstance(payload,list) and type(token) is int and 0<=token<len(payload):payload=payload[token]
        else:raise ValueError('invalid source locator')
    return payload


def assess_readiness(sources,observations,*,scope):
    """Hashes/locators establish submitted integrity, not source authenticity.

    Complete effective observations must match an explicitly chosen period and
    environment. Metadata, synthetic evidence and zero cost/margin cannot prove
    readiness. No inference from demo conditions to a live account is allowed.
    """
    _validate_scope(scope)
    if not isinstance(sources,dict) or not isinstance(observations,dict) or set(observations)-set(FIELDS):
        raise ValueError('invalid readiness evidence')
    for source in sources.values():
        exact(source,{'payload','sha256','kind'},'readiness source')
        if source['kind'] not in ('observed','synthetic') or fingerprint(source['payload'])!=source['sha256']:
            raise ValueError('source integrity mismatch')
    rows={}
    for field in FIELDS:
        facts=observations.get(field,[])
        if not isinstance(facts,list):raise ValueError('observation list required')
        statuses=[];values=[]
        for fact in facts:
            exact(fact,{'source','locator','value','scope','observed_at','coverage','limitations','incompatible'},'readiness fact')
            _validate_scope(fact['scope'])
            timestamp(fact['observed_at'])
            if type(fact['incompatible']) is not bool or fact['coverage'] not in ('metadata','effective') or not isinstance(fact['limitations'],list):
                raise ValueError('invalid evidence qualification')
            source=sources[fact['source']]
            if fingerprint(_located(source['payload'],fact['locator']))!=fingerprint(fact['value']):
                raise ValueError('observation is not the referenced source value')
            value=fact['value'];values.append(value)
            if fact['incompatible'] or any(fact['scope'][key] is not None and scope[key] is not None and fact['scope'][key]!=scope[key] for key in SCOPE):
                status='incompatible'
            elif value is None:status='unknown'
            elif (source['kind']=='synthetic' or fact['coverage']!='effective' or fact['limitations'] or
                  any(scope[k] is None or fact['scope'][k] is None for k in SCOPE) or
                  (field in ('commission','swap','margin_required') and type(value) in (int,float) and value==0)):
                status='partially_confirmed'
            else:status='confirmed'
            statuses.append(status)
        if len({fingerprint(v) for v in values if v is not None})>1:statuses.append('incompatible')
        classification=next((s for s in ('incompatible','unknown','partially_confirmed','confirmed') if s in statuses),'unknown')
        rows[field]=dict(classification=classification,evidence=deepcopy(facts))
    return dict(schema_version='3.3C-1',artifact_type='readiness_report',scope=deepcopy(scope),checks=rows,
                ready_for_execution=False,live_execution_enabled=False,
                source_hashes={k:s['sha256'] for k,s in sources.items()},
                warnings=['demo_is_not_live','metadata_does_not_prove_historical_effective_conditions',
                          'zero_commission_swap_or_margin_does_not_prove_cost_or_margin_model',
                          'source_authenticity_and_adapter_semantics_require_review'])
