"""Offline Python history laboratory. No MetaTrader5 import or live dispatcher.

Only finite recorded fixtures can be consumed. A new approved plan AND a separately
reviewed real bridge are necessary for live use; a JSON flag can never enable it.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path, PureWindowsPath
import shutil
import time
from typing import Protocol

from .batch_manifest import fingerprint
from .history_audit import audit_snapshot, audit_collection

SCHEMA = 'python-history-proposal-1'
INSTALLATION = r'C:\Program Files\Rico - MetaTrader 5'
MQL5_SHA256 = 'c9c24fd63fce9cebca6adc7228f2e166ae7e900a575c9e9d4b46c37ecc4b4d65'
LAB_ROOT = Path(__file__).resolve().parents[1]/'runs'/'python_history_lab'
OPERATION_COST = 14  # pre/post metadata (3 each) + rates, each paired with last_error
FIELDS = ('time','open','high','low','close','tick_volume','spread','real_volume')


class PythonHistoryPort(Protocol):
    """Design boundary only; no implementation is connected by this module."""
    def terminal_info(self): ...
    def account_info(self): ...
    def symbol_info(self, symbol): ...
    def copy_rates_range(self, symbol, timeframe, date_from, date_to): ...
    def last_error(self): ...


class DisabledPythonHistoryAdapter:
    acquisition_enabled = False
    live_execution_enabled = False

    def acquire(self, *args, **kwargs):
        raise PermissionError('PYTHON_BACKEND_DISABLED: new approval and reviewed real bridge required')

    initialize = acquire


def utc(value):
    if not isinstance(value, str): raise ValueError('explicit UTC timestamp required')
    stamp = datetime.fromisoformat(value.replace('Z','+00:00'))
    if stamp.tzinfo is None or stamp.utcoffset()!=timedelta(0) or stamp.microsecond:
        raise ValueError('UTC whole seconds required; no implicit relabeling')
    return stamp


def api_interval(request):
    start, end = utc(request['from_utc']), utc(request['to_utc'])
    if start >= end or end-start > timedelta(days=1): raise ValueError('invalid page interval')
    step = 60 if request['timeframe']=='M1' else 300 if request['timeframe']=='M5' else 0
    if not step or int(start.timestamp())%step or int(end.timestamp())%step:
        raise ValueError('unsupported or misaligned bar interval')
    return start, end-timedelta(seconds=1)


def logical_key(request):
    """Backend-independent exact UTC window identity, independent of plan/version."""
    api_interval(request)
    return fingerprint(dict(symbol='PETR4',timeframe=request['timeframe'],
        start=int(utc(request['from_utc']).timestamp()),end=int(utc(request['to_utc']).timestamp())))


def proposal():
    pages=[]
    for start,end in [('2026-11-03T13:00:00+00:00','2026-11-03T13:05:00+00:00'),
                      ('2026-11-03T13:05:00+00:00','2026-11-03T13:10:00+00:00')]:
        for tf in ('M1','M5'): pages.append(dict(timeframe=tf,from_utc=start,to_utc=end))
    return dict(schema_version=SCHEMA,backend='python_mt5',status='PROPOSED_NOT_APPROVED',
        acquisition_enabled=False,live_execution_enabled=False,automatic_retries=False,
        max_concurrency=1,symbol='PETR4',installation=INSTALLATION,exe='terminal64.exe',
        mql5_path_sha256=MQL5_SHA256,terminal_name='Rico - MetaTrader 5',build=6230,
        server='Rico-DEMO',account_binding=None,python_version='3.11',package_version='5.0.5430',
        utc_semantics='UTC_windows_not_unverified_broker_dates',pages=pages,
        valid_from=None,valid_to=None,calendar_evidence=None,prior_attempt_review=None,
        limits=dict(max_pages=4,max_operations=80,max_records=8000,records_per_page=2000,
            raw_page_bytes=2097152,storage_bytes=33554432,min_free_bytes=4294967296,
            elapsed_seconds=600,identity_age_seconds=60),
        allowed_future_functions=['initialize','terminal_info','account_info','symbol_info',
                                 'copy_rates_range','last_error','shutdown'])


def validate_plan(plan):
    # This implementation accepts only the reviewed, non-executable proposal shape.
    if plan != proposal(): raise PermissionError('unsupported or altered offline proposal')
    for page in plan['pages']: api_interval(page)
    return deepcopy(plan)


def _encode(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')


def _save(path, data):
    with path.open('xb') as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())


def _read(path):
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out: raise ValueError('duplicate artifact key')
            out[key]=value
        return out
    return json.loads(path.read_text(encoding='utf-8'),object_pairs_hook=unique)


def error_record(error):
    """Preserve code and hash of description without leaking credentials/account data."""
    if not isinstance(error,(list,tuple)) or len(error)!=2 or type(error[0]) is not int or not isinstance(error[1],str):
        raise ValueError('invalid last_error result')
    names={1:'success',-1:'generic_failure',-2:'invalid_parameters',-3:'no_memory',
           -4:'no_history',-5:'invalid_version',-6:'authentication_failed',
           -7:'unsupported',-8:'trading_disabled',-10000:'ipc_failure',
           -10001:'ipc_send_failed',-10002:'ipc_receive_failed',
           -10003:'ipc_initialization_or_connection_failed',-10005:'ipc_timeout'}
    return dict(code=error[0],category=names.get(error[0],'unknown'),
        description_sha256=hashlib.sha256(error[1].encode('utf-8')).hexdigest())


def verify_identity(observation, plan, account_binding, now):
    """Input is a synthetic recorded observation; never calls a terminal."""
    term,account,symbol = (observation[k] for k in ('terminal','account','symbol'))
    observed=utc(observation['observed_at'])
    if now.tzinfo is None or not timedelta(0)<=now-observed<=timedelta(seconds=plan['limits']['identity_age_seconds']):
        raise PermissionError('stale or future identity')
    mql5=str(PureWindowsPath(term['data_path'])/'MQL5')
    if (PureWindowsPath(term['path'])!=PureWindowsPath(plan['installation']) or
        hashlib.sha256(mql5.casefold().encode()).hexdigest()!=plan['mql5_path_sha256'] or
        type(term['build']) is not int or term['build']!=plan['build'] or
        term['name']!=plan['terminal_name'] or term['connected'] is not True or
        account['server']!=plan['server'] or type(account['trade_mode']) is not int or account['trade_mode']!=0 or
        account['binding']!=account_binding or symbol['name']!='PETR4' or
        symbol['select'] is not True or symbol['custom'] is not False):
        raise PermissionError('terminal, demo account or symbol identity mismatch')
    if len(observation['metadata_errors'])!=3 or any(error_record(e)['code']!=1 for e in observation['metadata_errors']):
        raise PermissionError('identity metadata call failed')
    return dict(installation_sha256=plan['mql5_path_sha256'],build=term['build'],
        server=account['server'],demo=True,symbol='PETR4',observed_at=observation['observed_at'])


class RecordedPythonSource:
    """Finite synthetic records, not a callback or native library wrapper."""
    def __init__(self, pages):
        self._pages=deepcopy(pages)
        self.calls=[]

    def _take(self, key):
        self.calls.append(key)
        return deepcopy(self._pages[key])


def analyze_bars(bars, request, expected_times):
    """Detect gaps against independent fixture expectations; never certify a market calendar."""
    import numpy as np  # numerical data only; no terminal package imported
    if not isinstance(bars,np.ndarray) or bars.ndim!=1 or bars.dtype.hasobject or bars.dtype.names!=FIELDS:
        raise ValueError('unexpected array shape or dtype')
    for field in FIELDS:
        kinds='iu' if field in ('time','tick_volume','spread','real_volume') else 'f'
        if bars.dtype[field].kind not in kinds: raise ValueError('unexpected column type')
    start,end=utc(request['from_utc']),utc(request['to_utc'])
    times=[int(t) for t in bars['time']]
    if any(not int(start.timestamp())<=t<int(end.timestamp()) for t in times):
        raise ValueError('bar outside authorized half-open interval')
    if times!=sorted(set(times)): raise ValueError('duplicate or reversed bars')
    rows=[dict(time=datetime.fromtimestamp(int(r['time']),timezone.utc).isoformat(),
        **{f:float(r[f]) for f in ('open','high','low','close')},
        tick_volume=int(r['tick_volume']),spread=int(r['spread']),volume=int(r['real_volume'])) for r in bars]
    snapshot=dict(symbol='PETR4',period=request['timeframe'],ok=True,history=rows)
    audit=audit_snapshot(snapshot,source_id='synthetic-python-page',timezone_label='UTC',origin='synthetic_numpy_fixture')
    if audit['errors'] or audit['duplicate_rows']: raise ValueError('invalid bars')
    missing=extra=None
    if expected_times is not None:
        if not isinstance(expected_times,list) or any(type(t) is not int for t in expected_times):
            raise ValueError('invalid independent expected grid')
        step=60 if request['timeframe']=='M1' else 300
        if (expected_times!=sorted(set(expected_times)) or
            any(not int(start.timestamp())<=t<int(end.timestamp()) or t%step for t in expected_times)):
            raise ValueError('expected grid outside page')
        missing=sorted(set(expected_times)-set(times));extra=sorted(set(times)-set(expected_times))
    return dict(audit=audit,missing_expected=missing,unexpected=extra,
        coverage_certified=False,fixture_complete=bool(times) and missing==[] and extra==[])


class OfflinePythonHistoryAdapter:
    """Append-only laboratory. No live adapter can be injected, even with approval.

    Cross-backend prior intents are conservative: naive timestamps/unknown timezone
    for the same symbol+period block overlap by date; they are never relabeled UTC.
    """
    acquisition_enabled=False
    live_execution_enabled=False

    def __init__(self, root, plan, consent, *, now, prior_intents=()):
        self.plan=validate_plan(plan);self.consent=deepcopy(consent)
        self.root=Path(root).resolve()
        if not self.root.is_relative_to(LAB_ROOT.resolve()) or self.root==LAB_ROOT.resolve():
            raise PermissionError('separate private Python laboratory directory required')
        if self.root.is_symlink(): raise PermissionError('symlink ledger forbidden')
        self.prior=deepcopy(list(prior_intents))
        self._check(now)
        self.manifest=dict(schema_version='python-history-lab-1',synthetic_only=True,
            plan_sha256=fingerprint(self.plan),consent_sha256=fingerprint(self.consent),
            prior_intents_sha256=fingerprint(self.prior),acquisition_enabled=False)
        if not self.root.exists():
            self.root.mkdir(parents=True,exist_ok=False)
            _save(self.root/'session.json',_encode(self.manifest))
        self.reload()

    def _check(self, now):
        validate_plan(self.plan)
        c=self.consent
        required={'purpose','plan_sha256','from_utc','to_utc','account_binding','expected_grids'}
        if (set(c)!=required or c['purpose']!='synthetic_offline_only' or
            c['plan_sha256']!=fingerprint(self.plan) or c['account_binding']!='synthetic-demo-account'):
            raise PermissionError('synthetic fixture consent required; real approvals are not accepted')
        a,b=utc(c['from_utc']),utc(c['to_utc'])
        if now.tzinfo is None or not a<=now<b or b-a>timedelta(hours=24):
            raise PermissionError('offline fixture window expired or invalid')
        keys={logical_key(p) for p in self.plan['pages']}
        if not isinstance(c['expected_grids'],dict) or not set(c['expected_grids'])<=keys:
            raise ValueError('unknown expected-grid page')

    def reload(self):
        validate_plan(self.plan)
        if (fingerprint(self.consent)!=self.manifest['consent_sha256'] or
            fingerprint(self.prior)!=self.manifest['prior_intents_sha256']):
            raise PermissionError('consent or prior-attempt index changed')
        if _read(self.root/'session.json')!=self.manifest: raise ValueError('session changed')
        self.calls=0;self.operations=0;self.records=0;self.storage=0;self.elapsed=0.0;self.blockers=[];self.done=set()
        previous=None
        for entry in self.root.iterdir():
            if entry.is_symlink() or entry.name!='session.json' and not entry.name.startswith('call-'):
                raise ValueError('unexpected session artifact')
        folders=sorted(self.root.glob('call-*'))
        for i,folder in enumerate(folders):
            if folder.name!=f'call-{i:06d}' or not folder.is_dir(): raise ValueError('noncontiguous ledger')
            intent=_read(folder/'intent.json')
            request=self.plan['pages'][i] if i<len(self.plan['pages']) else None
            if (intent['sequence']!=i or intent['request']!=request or
                intent['logical_key']!=logical_key(request) or
                intent['plan_sha256']!=fingerprint(self.plan) or intent['manifest_sha256']!=fingerprint(self.manifest)):
                raise ValueError('intent identity changed')
            if any(p.is_symlink() or not p.is_file() for p in folder.iterdir()): raise ValueError('unsafe page artifact')
            self.calls+=1;self.operations+=OPERATION_COST
            self.storage+=sum(p.stat().st_size for p in folder.iterdir())
            key=logical_key(intent['request'])
            if key in self.done: raise ValueError('duplicate durable request')
            self.done.add(key)
            receipt_path=folder/'receipt.json'
            if not receipt_path.exists(): self.blockers.append('unknown_outcome');continue
            r=_read(receipt_path);body={k:v for k,v in r.items() if k!='receipt_sha256'}
            if (fingerprint(body)!=r['receipt_sha256'] or r['previous']!=previous or
                r['intent_sha256']!=fingerprint(intent) or r['operation_cost']!=OPERATION_COST or
                type(r['records']) is not int or r['records']<0 or
                type(r['elapsed']) not in (int,float) or not math.isfinite(r['elapsed']) or r['elapsed']<0):
                raise ValueError('receipt integrity changed')
            if set(p.name for p in folder.iterdir())!=set(r['files'])|{'intent.json','receipt.json'}:
                raise ValueError('unexpected page file')
            for name,digest in r['files'].items():
                if name not in ('array.npy','result.json','audit.json','failure.json'):
                    raise ValueError('unsafe receipt path')
                if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest: raise ValueError('stored bytes changed')
            previous=r['receipt_sha256'];self.records+=r['records'];self.elapsed+=r['elapsed']
            if r['outcome']!='synthetic_observed': self.blockers.append('failed_or_ambiguous_response')
        self.previous=previous
        limits=self.plan['limits']
        if (self.calls>limits['max_pages'] or self.operations>limits['max_operations'] or
            self.records>limits['max_records'] or self.storage>limits['storage_bytes'] or
            self.elapsed>=limits['elapsed_seconds']):
            self.blockers.append('persistent_budget_exceeded')

    def status(self):
        self.reload()
        return dict(state='BLOCKED' if self.blockers else 'OFFLINE_PILOT_REVIEW_REQUIRED' if self.calls==len(self.plan['pages']) else 'OFFLINE_READY',
            pages=self.calls,operations_reserved=self.operations,records=self.records,
            storage_bytes=self.storage,elapsed_seconds=self.elapsed,blockers=self.blockers,
            acquisition_enabled=False,coverage_certified=False)

    def _prior_overlap(self, page):
        a,b=utc(page['from_utc']),utc(page['to_utc'])
        for intent in self.prior:
            r=intent.get('request',intent)
            if r.get('symbol','PETR4')!='PETR4' or r.get('period',r.get('timeframe'))!=page['timeframe']: continue
            start=r.get('datetime_from',r.get('from_utc'));end=r.get('datetime_to',r.get('to_utc'))
            try:
                x,y=datetime.fromisoformat(start),datetime.fromisoformat(end)
                overlap=(a<y and x<b) if x.tzinfo and y.tzinfo else a.date()<=y.date() and x.date()<=b.date()
            except (ValueError,TypeError): overlap=True
            if overlap: raise PermissionError('prior backend attempt requires separate human disposition')

    def acquire_next(self, source, *, now, free_bytes=None, clock=time.monotonic):
        # Concrete finite source only: no Protocol object, callback, module or subclass.
        if type(source) is not RecordedPythonSource: raise PermissionError('recorded synthetic source only')
        self._check(now());self.reload()
        if self.blockers: raise PermissionError('BLOCKED: no retries or recovery by resetting counters')
        if self.calls>=len(self.plan['pages']): raise PermissionError('pilot review required; no expansion implemented')
        request=self.plan['pages'][self.calls];key=logical_key(request);self._prior_overlap(request)
        lim=self.plan['limits'];available=free_bytes or (lambda:shutil.disk_usage(self.root).free)
        reserve=4*lim['raw_page_bytes']+65536
        if (self.operations+OPERATION_COST>lim['max_operations'] or
            self.records+lim['records_per_page']>lim['max_records'] or self.elapsed>=lim['elapsed_seconds']):
            raise PermissionError('budget exhausted')
        if self.storage+reserve>lim['storage_bytes'] or available()<lim['min_free_bytes']+reserve:
            raise OSError('insufficient storage reserve')
        started=clock();folder=self.root/f'call-{self.calls:06d}'
        intent=dict(sequence=self.calls,request=deepcopy(request),logical_key=key,
            plan_sha256=fingerprint(self.plan),manifest_sha256=fingerprint(self.manifest),
            observed_at=now().isoformat(),synthetic_only=True)
        folder.mkdir(exist_ok=False);_save(folder/'intent.json',_encode(intent))
        files={};count=0;outcome='failed';err=None;metadata_errors=[]
        def save(name, data):
            if sum((folder/n).stat().st_size for n in files)+len(data)>reserve-16384 or available()<lim['min_free_bytes']+len(data):
                raise OSError('page storage exceeded')
            _save(folder/name,data);files[name]=hashlib.sha256(data).hexdigest()
        try:
            self._check(now())
            reply=RecordedPythonSource._take(source,key)
            err=error_record(reply['last_error'])
            metadata_errors=[error_record(e) for side in ('before','after')
                for e in reply[side]['metadata_errors'][:3]]
            pre=verify_identity(reply['before'],self.plan,self.consent['account_binding'],now())
            bars=reply['bars']
            if bars is not None:
                import numpy as np
                if not isinstance(bars,np.ndarray) or bars.dtype.hasobject: raise ValueError('invalid array')
                buf=io.BytesIO();np.save(buf,bars,allow_pickle=False);raw=buf.getvalue()
                count=len(bars) if bars.ndim else 0
                save('result.json',_encode(dict(error=err,rows=count,bytes=len(raw),dtype=str(bars.dtype),
                    shape=list(bars.shape),array_sha256=hashlib.sha256(raw).hexdigest(),identity=pre)))
                if len(raw)>lim['raw_page_bytes']:
                    raise ValueError('oversized array; hash only retained, not a complete raw artifact')
                save('array.npy',raw)
            else: save('result.json',_encode(dict(error=err,rows=None,identity=pre)))
            if err['code']!=1: raise ValueError('provider_'+err['category'])
            if bars is None: raise ValueError('None result despite success code')
            if not count: raise ValueError('empty response')
            if count>lim['records_per_page']: raise ValueError('record limit exceeded')
            post=verify_identity(reply['after'],self.plan,self.consent['account_binding'],now())
            if {k:v for k,v in pre.items() if k!='observed_at'}!={k:v for k,v in post.items() if k!='observed_at'}:
                raise PermissionError('identity changed in flight')
            audit=analyze_bars(bars,request,self.consent['expected_grids'].get(key))
            audit['audit']['source_id']=f'synthetic-python-{self.calls:06d}'
            earlier=[_read(p/'audit.json')['audit'] for p in sorted(self.root.glob('call-*'))
                     if p!=folder and (p/'audit.json').exists()]
            collection=audit_collection([*earlier,audit['audit']])
            audit['M1_M5_comparison']=collection['M1_M5_comparison']
            save('audit.json',_encode(audit))
            if not audit['fixture_complete']: raise ValueError('incomplete_or_ambiguous_grid')
            if collection['classification']=='invalid': raise ValueError('M1_M5_conflict')
            self._check(now())
            if self.elapsed+clock()-started>=lim['elapsed_seconds']: raise TimeoutError('processing deadline')
            outcome='synthetic_observed'
        except BaseException as exc:
            # Exception text may contain private fixture inputs. Persist type only.
            save('failure.json',_encode(dict(error_type=type(exc).__name__,
                reason=str(exc) if str(exc) in ('empty response','incomplete_or_ambiguous_grid',
                    'record limit exceeded','M1_M5_conflict','processing deadline',
                    'None result despite success code') else 'synthetic_page_failed',
                last_error=err,metadata_errors=metadata_errors,
                exception_sha256=hashlib.sha256(str(exc).encode()).hexdigest())))
            raise
        finally:
            receipt=dict(intent_sha256=fingerprint(intent),previous=self.previous,files=files,
                records=count,elapsed=clock()-started,outcome=outcome,operation_cost=OPERATION_COST,
                coverage_certified=False,synthetic_only=True)
            receipt['receipt_sha256']=fingerprint(receipt)
            _save(folder/'receipt.json',_encode(receipt))
        self.reload()
        return deepcopy(receipt)
