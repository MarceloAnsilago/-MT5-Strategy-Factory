"""Bounded deterministic JSON-to-MQL5 generator. No compiler/tester calls."""
import argparse
from copy import deepcopy
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path,PureWindowsPath
import re
import sqlite3
from string import Template

from .analysis import read_artifact,write_artifact
from .batch_manifest import exact,sha
from .tester import BacktestConfig

VERSION='1.0.0'
MAX_CANDIDATES=32
MAX_RULES=5
MAX_HANDLES=16
TEMPLATE=Path(__file__).parent/'templates/candidate_v1.mq5.in'
RISK_KEYS={'volume_mode','sl_percent','tp_percent','max_spread_points','max_entries','max_holding_bars','deviation_points'}


class DuplicateCandidate(ValueError):
    pass


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def integer(value,low,high):
    if type(value) is not int or not low<=value<=high:
        raise ValueError('integer parameter outside limits')
    return value


def real(value,low,high):
    if type(value) not in (int,float):
        raise ValueError('numeric parameter required')
    number=Decimal(str(value))
    if not number.is_finite() or not low<=number<=high or number!=number.quantize(Decimal('0.000001')):
        raise ValueError('real parameter outside limits or more than six decimals')
    return float(number)


def validate_rule(rule):
    if not isinstance(rule,dict):
        raise ValueError('rule must be an object')
    kind=rule.get('kind')
    fields={
        'ma_cross':{'kind','fast','slow','method','direction'},
        'ma_trend':{'kind','fast','slow','method','direction'},
        'price_ma':{'kind','period','method','relation'},
        'rsi_level':{'kind','period','level','relation'},
        'rsi_cross':{'kind','period','level','relation'},
        'adx_strength':{'kind','period','minimum','maximum'},
        'adx_direction':{'kind','period','minimum','direction'}}
    if not isinstance(kind,str) or kind not in fields:
        raise ValueError('unknown indicator rule')
    exact(rule,fields[kind],'rule')
    rule=deepcopy(rule)
    if kind.startswith('ma_'):
        integer(rule['fast'],2,500);integer(rule['slow'],3,500)
        if rule['fast']>=rule['slow']:
            raise ValueError('fast MA must be below slow MA period')
        allowed=('above','below') if kind=='ma_cross' else ('up','down')
        if rule['direction'] not in allowed:
            raise ValueError('invalid MA direction')
    else:
        integer(rule['period'],2,500 if kind=='price_ma' else 100)
    if kind in ('ma_cross','ma_trend','price_ma') and rule['method'] not in ('EMA','SMA'):
        raise ValueError('unsupported MA method')
    if kind in ('price_ma','rsi_level','rsi_cross') and rule['relation'] not in ('above','below'):
        raise ValueError('invalid relation')
    if kind.startswith('rsi_'):
        rule['level']=real(rule['level'],1,99)
    if kind.startswith('adx_'):
        rule['minimum']=real(rule['minimum'],0,100)
        if kind=='adx_strength':
            rule['maximum']=real(rule['maximum'],0,100)
            if rule['minimum']>=rule['maximum']:
                raise ValueError('invalid ADX interval')
        elif rule['direction'] not in ('up','down'):
            raise ValueError('invalid ADX direction')
    return rule


def clause(rules):
    if not isinstance(rules,list) or len(rules)>MAX_RULES:
        raise ValueError('clause requires zero to five rules')
    result=sorted((validate_rule(r) for r in rules),key=canonical)
    if len({canonical(r) for r in result})!=len(result):
        raise ValueError('duplicate rule')
    directions={}
    intervals={}
    for rule in result:
        kind=rule['kind']
        if kind in ('ma_cross','ma_trend'):
            key=('ma',rule['fast'],rule['slow'],rule['method'])
            direction=rule['direction'] in ('above','up')
        elif kind=='price_ma':
            key=('price',rule['period'],rule['method']);direction=rule['relation']=='above'
        elif kind=='adx_direction':
            key=('adx',rule['period']);direction=rule['direction']=='up'
        else:
            key=None
        if key is not None:
            if key in directions and directions[key]!=direction:
                raise ValueError('contradictory directions in AND clause')
            directions[key]=direction
        constraints=[]
        if kind.startswith('rsi_'):
            above=rule['relation']=='above'
            constraints.append((('rsi',rule['period'],1),above,rule['level'],False))
            if kind=='rsi_cross':
                constraints.append((('rsi',rule['period'],0),not above,rule['level'],True))
        elif kind.startswith('adx_'):
            constraints.append((('adx',rule['period'],1),True,rule['minimum'],True))
            if kind=='adx_strength':
                constraints.append((('adx',rule['period'],1),False,rule['maximum'],True))
        for key,lower,level,inclusive in constraints:
            low,high,li,hi=intervals.get(key,(0,100,True,True))
            if lower:
                if level>low:low,li=level,inclusive
                elif level==low:li=li and inclusive
            else:
                if level<high:high,hi=level,inclusive
                elif level==high:hi=hi and inclusive
            if low>high or low==high and not (li and hi):
                raise ValueError('impossible indicator interval')
            intervals[key]=(low,high,li,hi)
    return result


def validate_spec(document):
    exact(document,{'schema_version','symbol','timeframe','entries','exits','risk'},'candidate specification')
    if document['schema_version']!='1.0':
        raise ValueError('unsupported candidate specification version')
    spec=deepcopy(document)
    try:
        BacktestConfig(expert=r'C:\SPEC\candidate.ex5',symbol=spec['symbol'],timeframe=spec['timeframe'],
                       from_date='2026-01-01',to_date='2026-01-02')
    except (TypeError,ValueError,OverflowError):
        raise ValueError('invalid candidate symbol or timeframe') from None
    for key in ('entries','exits'):
        exact(spec[key],{'long','short'},key)
        for side in ('long','short'):
            spec[key][side]=clause(spec[key][side])
    if not spec['entries']['long'] and not spec['entries']['short']:
        raise ValueError('at least one active entry side is required')
    if spec['entries']['long']==spec['entries']['short']:
        raise ValueError('identical long/short entries would always conflict')
    for side in ('long','short'):
        if not spec['entries'][side] and spec['exits'][side]:
            raise ValueError('exit rules for inactive side')
    exact(spec['risk'],RISK_KEYS,'risk')
    risk=spec['risk']
    if risk['volume_mode']!='minimum':
        raise ValueError('only minimum fixed symbol volume is supported')
    risk['sl_percent']=real(risk['sl_percent'],Decimal('0.000001'),20)
    risk['tp_percent']=real(risk['tp_percent'],Decimal('0.000001'),50)
    if risk['max_spread_points'] is not None:
        risk['max_spread_points']=real(risk['max_spread_points'],0,1000)
    integer(risk['max_entries'],1,1000)
    integer(risk['max_holding_bars'],1,1000)
    integer(risk['deviation_points'],0,100)
    if len(indicators(spec))>MAX_HANDLES:
        raise ValueError('indicator handle limit exceeded')
    return spec


def indicators(spec):
    keys=set()
    for group in ('entries','exits'):
        for rules in spec[group].values():
            for rule in rules:
                kind=rule['kind']
                if kind in ('ma_cross','ma_trend'):
                    keys.update(('ma',period,rule['method']) for period in (rule['fast'],rule['slow']))
                elif kind=='price_ma':keys.add(('ma',rule['period'],rule['method']))
                else:keys.add(('rsi' if kind.startswith('rsi_') else 'adx',rule['period'],''))
    return sorted(keys)


def literal(value):
    return format(value,'.6f').rstrip('0').rstrip('.')+'.0' if float(value).is_integer() else format(value,'.6f').rstrip('0')


def render(document):
    spec=validate_spec(document)
    spec_hash=digest(spec)
    candidate_id='g1_'+spec_hash[:16]
    keys=indicators(spec)
    handles={key:'h'+str(index) for index,key in enumerate(keys)}
    def variable(key,buffer=0,index=1):
        return handles[key]+'b'+str(buffer)+'['+str(index)+']'
    def expression(rule):
        kind=rule['kind']
        if kind in ('ma_cross','ma_trend'):
            fast=('ma',rule['fast'],rule['method']);slow=('ma',rule['slow'],rule['method'])
            up=rule['direction'] in ('above','up');op='>' if up else '<'
            newer=variable(fast)+op+variable(slow)
            if kind=='ma_cross':
                return '('+variable(fast,index=0)+('<=' if up else '>=')+variable(slow,index=0)+' && '+newer+')'
            return '('+newer+' && '+variable(slow)+op+variable(slow,index=0)+')'
        if kind=='price_ma':
            return '(close[1]'+('>' if rule['relation']=='above' else '<')+variable(('ma',rule['period'],rule['method']))+')'
        if kind.startswith('rsi_'):
            key=('rsi',rule['period'],'');up=rule['relation']=='above';level=literal(rule['level'])
            newer=variable(key)+('>' if up else '<')+level
            return '('+(variable(key,index=0)+('<=' if up else '>=')+level+' && ' if kind=='rsi_cross' else '')+newer+')'
        key=('adx',rule['period'],'')
        minimum=variable(key)+'>='+literal(rule['minimum'])
        if kind=='adx_strength':return '('+minimum+' && '+variable(key)+'<='+literal(rule['maximum'])+')'
        return '('+minimum+' && '+variable(key,1)+('>' if rule['direction']=='up' else '<')+variable(key,2)+')'
    values=dict(candidate_id=candidate_id,spec_sha256=spec_hash,generator_version=VERSION,
        symbol=spec['symbol'],timeframe=spec['timeframe'],magic=int(spec_hash[:12],16),
        sl_percent=literal(spec['risk']['sl_percent']),tp_percent=literal(spec['risk']['tp_percent']),
        max_spread_points=literal(spec['risk']['max_spread_points']) if spec['risk']['max_spread_points'] is not None else '-1.0',
        max_entries=spec['risk']['max_entries'],max_holding_bars=spec['risk']['max_holding_bars'],
        deviation_points=spec['risk']['deviation_points'],warmup=max(key[1]*(2 if key[0]=='adx' else 1) for key in keys),
        allow_long='true' if spec['entries']['long'] else 'false',allow_short='true' if spec['entries']['short'] else 'false')
    declarations=[];initializers=[];readers=[];releases=[]
    for key,handle in handles.items():
        kind,period,method=key
        declarations.append('int '+handle+'=INVALID_HANDLE;')
        call=(f'iMA(_Symbol,_Period,{period},0,MODE_{method},PRICE_CLOSE)' if kind=='ma' else
              f'iRSI(_Symbol,_Period,{period},PRICE_CLOSE)' if kind=='rsi' else f'iADX(_Symbol,_Period,{period})')
        initializers.extend([f'   {handle}={call};',f'   if({handle}==INVALID_HANDLE) return INIT_FAILED;'])
        for buffer in range(3 if kind=='adx' else 1):
            readers.extend([f'   double {handle}b{buffer}[2];',f'   if(!ClosedBuffer({handle},{buffer},{handle}b{buffer})) return;'])
        releases.append(f'   if({handle}!=INVALID_HANDLE) IndicatorRelease({handle});')
    values.update(handle_declarations='\n'.join(declarations),handle_initializers='\n'.join(initializers),
                  buffer_readers='\n'.join(readers),handle_releases='\n'.join(releases))
    for group,prefix in (('entries','enter'),('exits','exit')):
        for side in ('long','short'):
            values[prefix+'_'+side]=' && '.join(expression(r) for r in spec[group][side]) or 'false'
    template=TEMPLATE.read_text(encoding='utf-8')
    source=Template(template).substitute(values)
    filename='MT5SF_G_'+spec_hash[:16]+'.mq5'
    metadata=dict(schema_version='1.0',candidate_id=candidate_id,generator_version=VERSION,
        spec_sha256=spec_hash,source_sha256=hashlib.sha256(source.encode('utf-8')).hexdigest(),
        template_sha256=hashlib.sha256(template.encode('utf-8')).hexdigest(),source_file=filename,
        compiled_sha256=None,policy=dict(tester_only=True,optimization=False,live_execution_enabled=False),
        parameters_location='compiled_constants',manifest_inputs={},symbol=spec['symbol'],timeframe=spec['timeframe'])
    return spec,source,metadata


def verify_candidate(directory):
    root=Path(directory)
    spec,source,expected=render(read_artifact(root/'spec.json'))
    metadata=read_artifact(root/'candidate.json')
    if metadata!=expected or (root/expected['source_file']).read_bytes()!=source.encode('utf-8'):
        raise ValueError('candidate artifacts changed or generator/template version differs')
    return deepcopy(metadata)


def audit_candidate(directory):
    """Static checklist, not behavioral certification. Verify bytes before compile."""
    metadata=verify_candidate(directory)
    source=(Path(directory)/metadata['source_file']).read_text(encoding='utf-8')
    for forbidden in ('OrderSend(', 'OrderSendAsync(', 'WebRequest(', '#import', 'BuyLimit(', 'SellLimit(',
                      'BuyStop(', 'SellStop(', 'input '):
        if forbidden in source:
            raise ValueError('generated code violates fixed safety template')
    required=('MQLInfoInteger(MQL_TESTER)','!MQLInfoInteger(MQL_OPTIMIZATION)',
              'if(!TesterOnly()) return INIT_FAILED;', 'if(!TesterOnly() || g_halted',
              'if(!TesterOnly() || !PositionSelectByTicket(ticket)) return false;',
              'CopyBuffer(handle,buffer,1,2,values)', 'CopyClose(_Symbol,_Period,1,2,close)',
              'SYMBOL_VOLUME_MIN', 'PositionsTotal()!=0 || OrdersTotal()!=0')
    if not all(marker in source for marker in required):
        raise ValueError('missing generator safety guard')
    return dict(candidate_id=metadata['candidate_id'],source_sha256=metadata['source_sha256'],
                static_check_passed=True,behavioral_validation=False,backtest_authorized=False)


def generate_many(specifications,*,output_root,registry='runs/candidate_registry.sqlite',limit=16):
    integer(limit,1,MAX_CANDIDATES)
    specifications=list(specifications)
    if not specifications or len(specifications)>limit:
        raise ValueError('candidate generation count outside limit')
    rendered=[render(spec) for spec in specifications] # All validation before artifact writes.
    hashes=[metadata['spec_sha256'] for _,_,metadata in rendered]
    if len(set(hashes))!=len(hashes):
        raise DuplicateCandidate('duplicate specifications in request')
    registry=Path(registry);registry.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(registry,timeout=5)
    records=[]
    try:
        db.execute('CREATE TABLE IF NOT EXISTS candidates (digest TEXT PRIMARY KEY,id TEXT UNIQUE,status TEXT,metadata TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY,id TEXT,time TEXT,status TEXT)')
        db.execute('BEGIN IMMEDIATE')
        for _,_,metadata in rendered:
            if db.execute('SELECT 1 FROM candidates WHERE digest=?',(metadata['spec_sha256'],)).fetchone():
                raise DuplicateCandidate('specification already registered; no overwrite or automatic retry')
        for _,_,metadata in rendered:
            db.execute('INSERT INTO candidates VALUES(?,?,?,?)',(metadata['spec_sha256'],metadata['candidate_id'],'reserved',canonical(metadata)))
            db.execute('INSERT INTO events(id,time,status) VALUES(?,?,?)',(metadata['candidate_id'],datetime.now(timezone.utc).isoformat(),'reserved'))
        db.commit()
        for spec,source,metadata in rendered:
            root=Path(output_root)/metadata['candidate_id']
            try:
                root.mkdir(parents=True,exist_ok=False)
                write_artifact(root/'spec.json',spec)
                with (root/metadata['source_file']).open('xb') as stream:stream.write(source.encode('utf-8'))
                write_artifact(root/'candidate.json',metadata)
                verify_candidate(root)
            except Exception as exc:
                db.execute('UPDATE candidates SET status=? WHERE digest=?',('failed:'+type(exc).__name__,metadata['spec_sha256']))
                db.execute('INSERT INTO events(id,time,status) VALUES(?,?,?)',(metadata['candidate_id'],datetime.now(timezone.utc).isoformat(),'failed:'+type(exc).__name__))
                db.commit()
                raise
            db.execute('UPDATE candidates SET status=? WHERE digest=?',('generated',metadata['spec_sha256']))
            db.execute('INSERT INTO events(id,time,status) VALUES(?,?,?)',(metadata['candidate_id'],datetime.now(timezone.utc).isoformat(),'generated'))
            db.commit()
            records.append(metadata)
        return records
    finally:
        db.close()


def manifest_strategy(metadata,compiled_path,compiled_sha256=None):
    """Declared identity only; does not compile, verify a binary or grant permission."""
    sha(compiled_sha256)
    expected=PureWindowsPath(metadata['source_file']).with_suffix('.ex5').name
    if not PureWindowsPath(compiled_path).is_absolute() or PureWindowsPath(compiled_path).name!=expected:
        raise ValueError('compiled EA path must match candidate identity')
    return dict(strategy_id=metadata['candidate_id'],version=metadata['generator_version'],
        ea=dict(path=compiled_path,source_sha256=metadata['source_sha256'],compiled_sha256=compiled_sha256))


def attach_candidate(summary,metadata):
    if summary.get('artifact_type')!='run_summary' or summary.get('schema_version')!='1.1':
        raise ValueError('summary 1.1 required')
    if summary['strategy']['expert']!=PureWindowsPath(metadata['source_file']).with_suffix('.ex5').name:
        raise ValueError('summary does not identify this candidate')
    result=deepcopy(summary)
    result['candidate_context']={key:metadata[key] for key in ('candidate_id','generator_version','spec_sha256','source_sha256')}
    result['candidate_context']['provenance']='generated_artifacts_not_runtime_confirmation'
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    generate=commands.add_parser('generate')
    generate.add_argument('specifications',type=Path,help='JSON array of candidate specifications')
    generate.add_argument('--output-root',type=Path,default=Path('MQL5/Experts/MT5StrategyFactory/Generated'))
    generate.add_argument('--registry',type=Path,default=Path('runs/candidate_registry.sqlite'))
    generate.add_argument('--limit',type=int,default=16)
    verify=commands.add_parser('verify');verify.add_argument('directory',type=Path)
    args=parser.parse_args()
    if args.command=='verify':
        result=verify_candidate(args.directory)
    else:
        result=generate_many(read_artifact(args.specifications),output_root=args.output_root,registry=args.registry,limit=args.limit)
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
