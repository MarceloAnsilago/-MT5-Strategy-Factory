"""Offline evidence ledger. Requested snapshots never prove effective settings."""
import configparser
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import PureWindowsPath
import re

PARAMETERS = ('expert','symbol','timeframe','from_date','to_date','deposit','currency',
              'leverage','model','execution_delay')
SETTINGS = ('optimization','forward_mode','visual','use_local','use_remote','use_cloud','terminal_build','agent_build','local_agent_observed')
COSTS = ('currency','spread_points','spread_model','commission_total','commission_model','swap_total',
         'swap_model','fees_total','fee_model','slippage_total','configuration_sha256')
HISTORY = ('origin','available_from','available_to','quality_percent','generated_bars',
           'generated_ticks','tick_source','coverage_complete','content_sha256',
           'synchronization_from','synchronization_to','synchronization_origin')
SENSITIVE = re.compile(r'token|password|secret|credential|authorization|dpapi|account|login',re.I)
MODELS = {0:'every tick',1:'m1 ohlc',2:'open prices',3:'math calculations',4:'real ticks'}
INI_KEYS = dict(Expert='expert',Symbol='symbol',Period='timeframe',FromDate='from_date',
               ToDate='to_date',Deposit='deposit',Currency='currency',Leverage='leverage',
               Model='model',ExecutionMode='execution_delay',Optimization='optimization',
               ForwardMode='forward_mode',Visual='visual',UseLocal='use_local',
               UseRemote='use_remote',UseCloud='use_cloud')


def digest(value):
    encoded = json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def scalar(value):
    return type(value) in (str,int,float,bool) and not (type(value) is float and not math.isfinite(value))


def equivalent(left,right):
    if type(left) is bool:
        return right is left or (isinstance(right,str) and right.lower()==str(left).lower())
    if type(right) is bool:
        return equivalent(right,left)
    if type(left) in (int,float) or type(right) in (int,float):
        try:
            a,b=Decimal(str(left)),Decimal(str(right))
            return a.is_finite() and b.is_finite() and abs(a-b)<=Decimal('0.0000000001')
        except InvalidOperation:
            return False
    return type(left) is type(right) and left==right


def normalize(key,value):
    if not scalar(value):
        return None
    if key=='expert':
        return PureWindowsPath(str(value)).name
    if key in ('from_date','to_date','available_from','available_to','synchronization_from','synchronization_to'):
        from datetime import date
        try:
            value=str(value)[:10].replace('.','-')
            return date.fromisoformat(value).isoformat()
        except ValueError:
            return None
    if key in ('deposit','leverage','execution_delay','spread_points','commission_total','swap_total',
               'fees_total','slippage_total','quality_percent','generated_bars','generated_ticks','forward_mode','terminal_build','agent_build'):
        try:
            if type(value) is bool:
                return None
            value=float(str(value).split(':')[-1])
            if not math.isfinite(value) or abs(value)>=1e100:
                return None
            if key in ('deposit','leverage') and value<=0:
                return None
            if key in ('generated_bars','generated_ticks','forward_mode') and (value<0 or not value.is_integer()):
                return None
            if key in ('leverage','execution_delay','terminal_build','agent_build') and not value.is_integer():
                return None
            if key in ('terminal_build','agent_build') and value<=0:
                return None
            if key=='execution_delay' and not -1<=value<=600000:
                return None
            if key=='spread_points' and value<0:
                return None
            if key=='quality_percent' and not 0<=value<=100:
                return None
            return int(value) if value.is_integer() else value
        except ValueError:
            return None
    if key in ('optimization','visual','use_local','use_remote','use_cloud','coverage_complete','local_agent_observed'):
        if type(value) is bool:
            return value
        if value in ('0','false') or type(value) is int and value==0:
            return False
        if value in ('1','true') or type(value) is int and value==1:
            return True
        return None
    if key=='model':
        if type(value) is int or isinstance(value,str) and value.isdigit():
            return MODELS.get(int(value))
        return value if value in MODELS.values() else None
    if key in ('configuration_sha256','content_sha256'):
        return value if isinstance(value,str) and re.fullmatch('[0-9a-f]{64}',value) else None
    return value if isinstance(value,str) and value and not any(c in value for c in '\r\n\x00') else None


def parse_set(text):
    """Only requested base values. Optimization ranges do not confirm execution."""
    result={}
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(';'):
            continue
        key,separator,value=line.partition('=')
        key=key.strip()
        if not separator or not re.fullmatch(r'[A-Za-z_]\w*',key) or SENSITIVE.search(key):
            raise ValueError('invalid or sensitive SET input')
        if key in result:
            raise ValueError('duplicate SET input')
        result[key]=value.split('||',1)[0].strip()
    return result


def parse_ini(text):
    parser=configparser.ConfigParser(interpolation=None,strict=True)
    parser.read_string(text)
    section=parser['Tester'] if parser.has_section('Tester') else {}
    return {target:normalize(target,section.get(source)) for source,target in INI_KEYS.items()
            if section.get(source) is not None}


def build_traceability(*,parameters,inputs=None,report=None,run_id=None,journal=None,
                       journal_run_id=None,tester_ini=None,inputs_set=None,
                       history_snapshot=None,symbol_snapshot=None):
    """A matched ID / bounded journal is caller-asserted provenance, not authentication.

    Optional report inputs/tester_settings/costs/history are an explicit export
    contract; arbitrary snapshots are recorded as observations, never promoted.
    """
    requested={key:normalize(key,parameters.get(key)) for key in PARAMETERS}
    requested_settings={key:None for key in SETTINGS}
    requested_inputs=dict(inputs or {})
    warnings=[]
    artifacts=[]
    candidates={group:{} for group in ('parameters','inputs','tester_settings','costs','history')}

    def artifact(source,value,scope):
        checksum=digest(value)
        artifacts.append({'source':source,'sha256':checksum,'hash_kind':'canonical_json','scope':scope})
        return checksum

    def add(group,key,value,source,locator,checksum):
        if group=='inputs':
            if not re.fullmatch(r'[A-Za-z_]\w*',key) or SENSITIVE.search(key):
                warnings.append('sensitive_or_invalid_input_omitted')
                return
            if not scalar(value):
                warnings.append('sensitive_or_invalid_input_omitted')
                return
        else:
            value=normalize(key,value)
        if value is not None:
            candidates[group].setdefault(key,[]).append({'value':value,'source':source,
                    'locator':locator,'artifact_sha256':checksum})

    for key,value in requested_inputs.items():
        if not isinstance(key,str) or SENSITIVE.search(key) or not scalar(value):
            raise ValueError('invalid or sensitive requested input')
    if tester_ini is not None:
        artifact('requested_ini',tester_ini,'requested_snapshot_not_effective')
        for key,value in parse_ini(tester_ini).items():
            if key in SETTINGS:
                requested_settings[key]=value
            elif key in requested:
                if requested[key] is not None and value is not None and not equivalent(requested[key],value):
                    warnings.append('requested_ini_disagreement:'+key)
                if requested[key] is None:
                    requested[key]=value
    if inputs_set is not None:
        artifact('requested_set',inputs_set,'requested_snapshot_not_effective')
        for key,value in parse_set(inputs_set).items():
            if key in requested_inputs and not equivalent(requested_inputs[key],value):
                warnings.append('requested_set_disagreement:'+key)
            requested_inputs.setdefault(key,value)
    report_bound=isinstance(report,dict) and run_id is not None and str(report.get('run_id'))==str(run_id)
    input_block_complete=False
    if isinstance(report,dict):
        checksum=artifact('report',report,'run_id_matched' if report_bound else 'unverified')
        if report_bound:
            for key in PARAMETERS:
                if key in report:
                    add('parameters',key,report[key],'report',key,checksum)
            if 'initial_deposit' in report:
                add('parameters','deposit',report['initial_deposit'],'report','initial_deposit',checksum)
            if 'initial_balance' in report:
                add('parameters','deposit',report['initial_balance'],'report','initial_balance',checksum)
            if isinstance(report.get('statistics'),dict) and 'initial_balance' in report['statistics']:
                add('parameters','deposit',report['statistics']['initial_balance'],'report','statistics.initial_balance',checksum)
            settings=report.get('tester_settings',{})
            if isinstance(settings,dict):
                for key in PARAMETERS+SETTINGS:
                    if key in settings:
                        add('parameters' if key in PARAMETERS else 'tester_settings',key,settings[key],
                            'report','tester_settings.'+key,checksum)
            if isinstance(report.get('inputs'),dict):
                input_block_complete=True
                for key,value in report['inputs'].items():
                    add('inputs',key,value,'report','inputs.'+key,checksum)
            for group,fields in (('costs',COSTS),('history',HISTORY)):
                values=report.get(group,{})
                if isinstance(values,dict):
                    for key in fields:
                        if key in values:
                            add(group,key,values[key],'report',group+'.'+key,checksum)
            for key in ('generated_bars','generated_ticks'):
                if key in report:
                    add('history',key,report[key],'report',key,checksum)
            if 'history_quality' in report:
                add('history','quality_percent',report['history_quality'],'report','history_quality',checksum)
            if isinstance(report.get('statistics'),dict) and 'history_quality' in report['statistics']:
                add('history','quality_percent',report['statistics']['history_quality'],'report','statistics.history_quality',checksum)
        else:
            warnings.append('report_identity_unverified')
            if report.get('run_id') is not None and run_id is not None:
                warnings.append('report_run_id_mismatch')
    messages=[]
    journal_bound=journal is not None and run_id is not None and str(journal_run_id)==str(run_id)
    if isinstance(journal,dict):
        records=journal.get('records',[])
        if not isinstance(records,list) or any(not isinstance(r,dict) or not isinstance(r.get('message',''),str) for r in records):
            raise ValueError('invalid journal records')
        messages=[r.get('message','') for r in records]
        if journal.get('truncated') or journal.get('records_count',len(records))!=len(records):
            journal_bound=False
            warnings.append('journal_incomplete')
    elif isinstance(journal,str):
        messages=journal.splitlines()
    starts=sum('started with inputs:' in message for message in messages)
    if starts>1:
        journal_bound=False
        warnings.append('multiple_input_blocks')
    if journal is not None:
        checksum=artifact('journal',journal,'caller_scoped_run' if journal_bound else 'unverified')
        if not journal_bound:
            warnings.append('journal_identity_or_completeness_unverified')
            if journal_run_id is not None and run_id is not None and str(journal_run_id)!=str(run_id):
                warnings.append('journal_run_id_mismatch')
        else:
            in_inputs=False
            input_names=set()
            for index,message in enumerate(messages):
                location='records['+str(index)+'].message'
                if 'started with inputs:' in message:
                    in_inputs=True
                    input_block_complete=True
                elif in_inputs:
                    match=re.fullmatch(r'\s+([A-Za-z_]\w*)=(.*)',message)
                    if match:
                        key,value=match.groups()
                        if key in input_names:
                            warnings.append('duplicate_effective_input:'+key)
                        input_names.add(key)
                        add('inputs',key,value.strip(),'journal',location,checksum)
                    else:
                        in_inputs=False
                match=re.search(r'^([^,\s]+),([A-Z0-9]+) \([^)]*\): testing of (.+?\.ex5) from (\d{4}\.\d{2}\.\d{2}) \d\d:\d\d to (\d{4}\.\d{2}\.\d{2}) \d\d:\d\d',message)
                if match:
                    for key,value in zip(('symbol','timeframe','expert','from_date','to_date'),match.groups()):
                        add('parameters',key,value,'journal',location,checksum)
                match=re.fullmatch(r'initial deposit ([\d.]+) ([A-Z]{3}), leverage 1:(\d+)',message)
                if match:
                    for key,value in zip(('deposit','currency','leverage'),match.groups()):
                        add('parameters',key,value,'journal',location,checksum)
                for text,model in (('every tick generating','every tick'),('1 minutes OHLC ticks generating','m1 ohlc'),
                                   ('open prices only','open prices'),('real ticks generating','real ticks')):
                    if re.fullmatch(r'[^,\s]+,[A-Z0-9]+(?: \([^)]*\))?: '+re.escape(text),message):
                        add('parameters','model',model,'journal',location,checksum)
                        add('history','tick_source','real' if model=='real ticks' else 'generated','journal',location,checksum)
                match=re.fullmatch(r'quality of analyzed history is ([\d.]+)%',message)
                if match:
                    add('history','quality_percent',match[1],'journal',location,checksum)
                if message=='cloud network mode is off':
                    add('tester_settings','use_cloud',False,'journal',location,checksum)
                if re.fullmatch(r'agent process started on 127\.0\.0\.1:\d+',message):
                    add('tester_settings','local_agent_observed',True,'journal',location,checksum)
                match=re.fullmatch(r'[^:]+: history synchronized from (\d{4}\.\d{2}\.\d{2}) to (\d{4}\.\d{2}\.\d{2})',message)
                if match:
                    add('history','synchronization_from',match[1],'journal',location,checksum)
                    add('history','synchronization_to',match[2],'journal',location,checksum)
                    add('history','synchronization_origin','terminal_to_tester_agent','journal',location,checksum)
                match=re.fullmatch(r'authorized \(agent build (\d+)\)',message)
                if match:
                    add('tester_settings','agent_build',match[1],'journal',location,checksum)
            if in_inputs:
                input_block_complete=False
                warnings.append('unterminated_input_block')
    def ledger(keys,group,requests):
        result={}
        for key in sorted(set(keys)|set(candidates[group])|set(requests)):
            evidence=candidates[group].get(key,[])
            wanted=requests.get(key)
            conflict=bool(evidence) and any(not equivalent(evidence[0]['value'],e['value']) for e in evidence[1:])
            conflict=conflict or 'duplicate_effective_input:'+key in warnings
            value=evidence[0]['value'] if evidence and not conflict else None
            match=equivalent(wanted,value) if wanted is not None and value is not None else None
            state='conflicting' if conflict else ('mismatch' if match is False else ('confirmed' if value is not None else 'unverifiable'))
            result[key]={'requested':wanted,'confirmed':value,'status':state,
                         'matches_requested':match,'evidence':evidence}
        return result
    result={group:ledger(fields,group,requests) for group,fields,requests in (
        ('parameters',PARAMETERS,requested),('inputs',(),requested_inputs),
        ('tester_settings',SETTINGS,requested_settings),('costs',COSTS,{}),('history',HISTORY,{}))}
    observations={}
    for source,snapshot in (('history_snapshot',history_snapshot),('symbol_snapshot',symbol_snapshot)):
        if snapshot is not None:
            checksum=artifact(source,snapshot,'snapshot_not_effective_execution_evidence')
            values={}
            if source=='history_snapshot' and isinstance(snapshot,dict):
                values={key:snapshot.get(key) for key in ('symbol','period','data_available_from','truncated') if scalar(snapshot.get(key))}
                bars=snapshot.get('history',[])
                values['returned_records']=len(bars) if isinstance(bars,list) else None
            if source=='symbol_snapshot' and isinstance(snapshot,dict):
                symbols=snapshot.get('symbols',[])
                if len(symbols)==1:
                    values={key:symbols[0].get(key) for key in ('symbol','volume_min','volume_step','spread_float','swap_long','swap_short','swap_mode') if scalar(symbols[0].get(key))}
            observations[source]={'status':'not_execution_confirmed','artifact_sha256':checksum,'values':values}
    divergent=any(v['status'] in ('mismatch','conflicting') for fields in result.values() for v in fields.values())
    divergent=divergent or any(w.startswith('requested_ini_disagreement:') or w.startswith('requested_set_disagreement:') for w in warnings)
    divergent=divergent or 'report_run_id_mismatch' in warnings or 'journal_run_id_mismatch' in warnings
    inputs_confirmed=input_block_complete and all(v['status']=='confirmed' for v in result['inputs'].values()) and not any(
        w=='sensitive_or_invalid_input_omitted' or w.startswith('duplicate_effective_input:') for w in warnings)
    scenario_confirmed=all(v['status']=='confirmed' for v in result['parameters'].values())
    costs_confirmed=all(result['costs'][key]['status']=='confirmed' for key in (
        'currency','spread_model','commission_model','swap_model','fee_model','configuration_sha256'))
    history_confirmed=all(result['history'][key]['status']=='confirmed' for key in (
        'origin','tick_source','content_sha256','available_from','available_to','coverage_complete')) and result['history']['coverage_complete']['confirmed'] is True
    settings_confirmed=all(result['tester_settings'][key]['status']=='confirmed' for key in (
        'optimization','forward_mode','visual','use_local','use_remote','use_cloud','terminal_build')) and all(
        result['tester_settings'][key]['confirmed']==value for key,value in (
        ('optimization',False),('forward_mode',0),('visual',False),('use_local',True),('use_remote',False),('use_cloud',False)))
    warnings+=['unverifiable:'+group+'.'+key for group,fields in result.items() for key,v in fields.items() if v['status']=='unverifiable']
    return {'schema_version':'1.0',**result,'input_block_complete':input_block_complete,
            'readiness':{'parameters':scenario_confirmed,'inputs':inputs_confirmed,
                         'cost_configuration':costs_confirmed,'history_content':history_confirmed,'tester_settings':settings_confirmed},
            'classification':'divergent' if divergent else ('confirmed' if all((scenario_confirmed,inputs_confirmed,costs_confirmed,history_confirmed,settings_confirmed)) else 'partial'),
            'artifacts':artifacts,'observations':observations,'warnings':sorted(set(warnings)),
            'limitations':['run_scope_and_export_authenticity_require_caller_audit',
                           'canonical_json_hash_is_not_a_full_history_or_cost_fingerprint']}
