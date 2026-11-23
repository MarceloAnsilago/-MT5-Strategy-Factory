"""Acquisition-only MCP bridge with durable intents and human-approved scope.

No tester imports, strategy execution, token discovery, scheduler or retries.
The approval below records the scope supplied by the human in this conversation;
it is not a general-purpose authorization issuer or a human authenticator.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import time

from .analysis import decode_artifact, read_artifact
from .batch_manifest import fingerprint, exact, timestamp
from .history_acquisition import validate_proposal, page_requests, DESTINATION
from .history_audit import audit_snapshot, audit_collection

PLAN_SHA256 = 'ba41024e0dd5e66a4a6a9e3f3ae086e3afa57c413836ce994bfedce39d6e88ca'
VALID_FROM = '2026-11-24T08:00:00-03:00'
VALID_TO = '2026-11-24T18:00:00-03:00'
TOOL = 'get_chart_history'


def approval_scope():
    return dict(schema_version='3.3G-human-scope-1', source='explicit_user_conversation_33G',
        plan_sha256=PLAN_SHA256, valid_from=VALID_FROM, valid_to=VALID_TO,
        symbol='PETR4', timeframes=['M1','M5'], datetime_from='2024-01-01T00:00:00',
        datetime_to='2026-10-01T00:00:00', server='Rico-DEMO', tools=[TOOL],
        implicit_sync_allowed=True, live_execution_enabled=False)


def check_window(now):
    if not isinstance(now,datetime) or now.tzinfo is None: raise ValueError('aware trusted wall clock required')
    if now < timestamp(VALID_FROM): raise PermissionError('AWAITING_AUTHORIZATION_WINDOW')
    if now >= timestamp(VALID_TO): raise PermissionError('AUTHORIZATION_EXPIRED')


def verify_identity(plan, workspace, account, symbols, *, observed_at):
    """Sanitize identity; never persist names, login, balances or quote prices."""
    validate_proposal(plan)
    path=workspace.get('workspace',{}).get('mql5_folder')
    build=workspace.get('compiler',{}).get('compiler_mql5_build')
    info=account.get('terminal',{}); identity=account.get('account',{})
    checksum=hashlib.sha256(path.casefold().encode()).hexdigest() if isinstance(path,str) else None
    actual=dict(server=identity.get('server'),build=build,installation_sha256=checksum)
    if (actual != plan['connection'] or identity.get('type')!='demo' or
        info.get('build')!=build or info.get('server_connected') is not True or
        info.get('program_name')!='Rico - MetaTrader 5' or
        not any(s.get('symbol')=='PETR4' and s.get('selected') is True for s in symbols.get('symbols',[]))):
        raise PermissionError('installation, server, connection or exact symbol diverged')
    timestamp(observed_at)
    return dict(connection=actual,symbol='PETR4',observed_at=observed_at,
                source='MCP_workspace_account_marketwatch',live_execution_enabled=False)


def _bytes(document):
    return json.dumps(document,sort_keys=True,ensure_ascii=False,allow_nan=False).encode('utf-8')


def _save(path, data):
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        import os
        os.fsync(stream.fileno())


class AuthorizedHistoryTransport:
    """One durable directory per approval, sequential pilot then reviewed scale.

    RPC result text is retained as UTF-8, distinct from HTTP/JSON-RPC wire bytes,
    which connected MCP tools do not expose. A receipt is written last. Any
    dispatched request lacking a valid receipt blocks every subsequent request.
    Multiple instances contend on exclusive creation of the same next intent.
    """
    live_execution_enabled=False

    def __init__(self, plan, *, base_root=DESTINATION):
        self.plan=validate_proposal(plan)
        if fingerprint(plan)!=PLAN_SHA256: raise PermissionError('authorized original plan changed')
        self.scope=approval_scope()
        self.root=Path(base_root)/('33g-'+fingerprint(self.scope)[:24])
        self.requests=page_requests(plan)
        self.pilot=[r for r in self.requests if '2024-01-02T00:00:00'<=r['datetime_from']<'2024-01-04T00:00:00']
        self.manifest=dict(schema_version='3.3G-session-1',plan_sha256=PLAN_SHA256,
            approval=self.scope,approval_sha256=fingerprint(self.scope),live_execution_enabled=False)
        if not self.root.exists():
            self.root.mkdir(parents=True,exist_ok=False)
            _save(self.root/'session.json',_bytes(self.manifest))
        if read_artifact(self.root/'session.json')!=self.manifest: raise PermissionError('session identity changed')
        self.reload()

    def reload(self):
        validate_proposal(self.plan)
        if fingerprint(self.plan)!=PLAN_SHA256: raise PermissionError('authorized plan changed in memory')
        if read_artifact(self.root/'session.json')!=self.manifest: raise PermissionError('session metadata changed')
        self.receipts=[];self.calls=0;self.diagnostic_calls=0;self.records=0;self.storage=0;self.elapsed=0.0
        self.blockers=[];self.audits=[]
        allowed={'session.json','pilot_review.json','diagnostics'}
        if any(not p.name.startswith('call-') and p.name not in allowed for p in self.root.iterdir()):
            raise ValueError('unknown acquisition artifact')
        diagnostics=self.root/'diagnostics'
        if diagnostics.exists():
            for index,path in enumerate(sorted(diagnostics.iterdir())):
                record=read_artifact(path)
                if path.name!=f'{index:06d}.json' or record['plan_sha256']!=PLAN_SHA256:
                    raise ValueError('diagnostic accounting changed')
                self.diagnostic_calls+=1
        remaining=[r for r in self.requests if r not in self.pilot]
        for index,folder in enumerate(sorted(self.root.glob('call-*'))):
            if folder.name!=f'call-{index:06d}' or not folder.is_dir(): raise ValueError('noncontiguous call ledger')
            self.calls+=1
            intent=read_artifact(folder/'intent.json')
            expected_request=self.pilot[index] if index<4 else remaining[index-4] if index-4<len(remaining) else None
            if (intent['sequence']!=index or intent['plan_sha256']!=PLAN_SHA256 or intent['approval_sha256']!=fingerprint(self.scope) or
                intent['tool']!=TOOL or intent['request']!=expected_request):
                raise ValueError('intent identity changed')
            self.storage+=sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
            if not (folder/'receipt.json').exists():
                self.blockers.append('pending_or_unknown_call_outcome');continue
            receipt=read_artifact(folder/'receipt.json')
            body={k:v for k,v in receipt.items() if k!='receipt_sha256'}
            if fingerprint(body)!=receipt['receipt_sha256'] or receipt['intent_sha256']!=fingerprint(intent):
                raise ValueError('receipt or request hash changed')
            if (receipt['request']!=intent['request'] or type(receipt['record_count']) is not int or receipt['record_count']<0 or
                type(receipt['elapsed_seconds']) not in (int,float) or not math.isfinite(receipt['elapsed_seconds']) or receipt['elapsed_seconds']<0):
                raise ValueError('receipt scope or resource accounting invalid')
            expected=self.receipts[-1]['receipt_sha256'] if self.receipts else None
            if receipt['previous_receipt_sha256']!=expected: raise ValueError('receipt chain changed')
            for name,checksum in receipt['files'].items():
                if name not in ('response.txt','audit.json','failure.json'): raise ValueError('unexpected receipt path')
                if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=checksum: raise ValueError('stored bytes changed')
            self.receipts.append(receipt)
            self.elapsed+=receipt['elapsed_seconds'];self.records+=receipt['record_count']
            if receipt['outcome']!='observed_partial': self.blockers.append('failed_or_ambiguous_response')
            elif 'audit.json' in receipt['files']: self.audits.append(read_artifact(folder/'audit.json'))
        if self.calls+self.diagnostic_calls>self.plan['max_calls'] or self.records>self.plan['max_records'] or self.storage>self.plan['max_storage_bytes']:
            raise ValueError('persistent budget exceeded')

    def record_diagnostic(self, tool, *, observed_at):
        """Account metadata attempts too; caller records before any future query.

        Initial read-only inspections may be recorded retrospectively with their
        real timestamps. This records an attempt, not a successful observation.
        """
        if tool not in ('rico_metaeditor.get_workspace_info','rico_terminal.get_workspace_info',
                        'rico_terminal.get_trading_account_info','rico_terminal.get_marketwatch_symbols'):
            raise PermissionError('diagnostic tool outside acquisition inspection scope')
        if observed_at is not None: timestamp(observed_at)
        self.reload()
        if self.calls+self.diagnostic_calls>=self.plan['max_calls']: raise PermissionError('total MCP call budget exhausted')
        folder=self.root/'diagnostics';folder.mkdir(exist_ok=True)
        _save(folder/f'{self.diagnostic_calls:06d}.json',_bytes(dict(tool=tool,observed_at=observed_at,
            recorded_at=datetime.now(timezone.utc).isoformat(),plan_sha256=PLAN_SHA256)))

    def status(self, *, now=None):
        self.reload()
        moment=now or datetime.now(timezone.utc)
        if self.blockers: state='ACQUISITION_BLOCKED'
        elif moment<timestamp(VALID_FROM): state='AWAITING_AUTHORIZATION_WINDOW'
        elif moment>=timestamp(VALID_TO): state='AUTHORIZATION_EXPIRED'
        else:
            state='PILOT_PENDING' if len(self.receipts)<4 else 'PILOT_REVIEW_REQUIRED'
            if (self.root/'pilot_review.json').exists():
                state='SCALE_READY' if read_artifact(self.root/'pilot_review.json')==self.pilot_review_document() else 'ACQUISITION_BLOCKED'
            if len(self.receipts)==len(self.requests): state='DATASET_PARTIAL'
        return dict(state=state,history_calls=self.calls,record_count=self.records,storage_bytes=self.storage,
            diagnostic_calls=self.diagnostic_calls,total_mcp_calls=self.calls+self.diagnostic_calls,
            elapsed_seconds=self.elapsed,blockers=self.blockers,coverage_certified=False,live_execution_enabled=False)

    def _next(self):
        if self.calls<4: return self.pilot[self.calls]
        review_path=self.root/'pilot_review.json'
        if not review_path.exists(): raise PermissionError('PILOT_REVIEW_REQUIRED')
        review=read_artifact(review_path)
        if review!=self.pilot_review_document(): raise PermissionError('pilot review missing, ambiguous or changed')
        done={fingerprint(r['request']) for r in self.receipts}
        return next((r for r in self.requests if fingerprint(r) not in done),None)

    def pilot_review_document(self):
        if len(self.receipts)<4 or self.blockers: raise PermissionError('four satisfactory pilot pages required')
        pilot_audits=self.audits[:4]
        collection=audit_collection(pilot_audits)
        comparisons=collection['M1_M5_comparison']
        if (len(pilot_audits)!=4 or collection['classification']=='invalid' or
            any(not a['records'] or a['timezone']=='unknown' for a in pilot_audits) or
            not comparisons or any(c['classification']!='conditional_aggregate_match' for c in comparisons)):
            raise PermissionError('pilot availability, timezone or M1/M5 remains ambiguous')
        return dict(schema_version='3.3G-pilot-review-1',plan_sha256=PLAN_SHA256,
            pilot_receipts=[r['receipt_sha256'] for r in self.receipts[:4]],
            collection_sha256=fingerprint(collection),temporal_semantics='verified_from_response_metadata',
            coverage_certified=False,live_execution_enabled=False)

    def accept_pilot(self):
        """Explicit pilot inspection, never inferred merely from four RPC successes."""
        self.reload()
        _save(self.root/'pilot_review.json',_bytes(self.pilot_review_document()))

    def acquire_next(self, call_tool, identity, *, now=lambda:datetime.now(timezone.utc),
                     free_bytes=None, stop=lambda:False, clock=time.monotonic):
        """Dispatch exactly one MCP tool call; no loop, retry, sleep or scheduler.

        call_tool(name, arguments) is the connected Rico-terminal bridge. A caller
        must collect fresh read-only identity first. Response metadata must
        positively establish temporal semantics and completeness; unknown stops.
        """
        started=clock()
        self.reload();check_window(now())
        if self.blockers: raise PermissionError('ACQUISITION_BLOCKED: previous outcome unresolved')
        exact(identity,{'connection','symbol','observed_at','source','live_execution_enabled'},'identity observation')
        age=now()-timestamp(identity['observed_at'])
        if (identity['connection']!=self.plan['connection'] or identity['symbol']!='PETR4' or
            identity['source']!='MCP_workspace_account_marketwatch' or identity['live_execution_enabled'] is not False or
            not timedelta(0)<=age<=timedelta(seconds=60)):
            raise PermissionError('fresh matching terminal identity required')
        if stop(): raise PermissionError('cooperative interruption before dispatch')
        if self.calls+self.diagnostic_calls>=self.plan['max_calls'] or self.elapsed+clock()-started>=self.plan['max_elapsed_seconds']:
            raise PermissionError('call or processing budget exhausted')
        request=self._next()
        if request is None: return dict(state='DATASET_PARTIAL',reason='all_planned_requests_observed',live_execution_enabled=False)
        # Reserve a whole page envelope, including its normalized audit and metadata.
        reserve=4*self.plan['max_raw_page_bytes']
        disk_free=free_bytes or (lambda:shutil.disk_usage(self.root).free)
        available=disk_free()
        if available<self.plan['min_free_disk_bytes']+reserve or self.storage+reserve>self.plan['max_storage_bytes']:
            raise OSError('insufficient disk or remaining page storage budget')
        if self.records+request['limit']>self.plan['max_records']: raise PermissionError('record budget exhausted')
        check_window(now())
        intent=dict(sequence=self.calls,tool=TOOL,request=deepcopy(request),plan_sha256=PLAN_SHA256,
            approval_sha256=fingerprint(self.scope),identity=deepcopy(identity),
            dispatched_at=now().isoformat(),live_execution_enabled=False)
        folder=self.root/f'call-{self.calls:06d}'
        folder.mkdir(exist_ok=False)
        _save(folder/'intent.json',_bytes(intent))  # Durable unknown outcome before dispatch.
        files={};count=0;outcome='failed';error_type=None;captured=None
        def save(name,data):
            if disk_free()<self.plan['min_free_disk_bytes']+len(data): raise OSError('free space fell below reserve')
            _save(folder/name,data);files[name]=hashlib.sha256(data).hexdigest()
        try:
            # Check the actual wall clock again after persisting the intent.
            check_window(now())
            if stop(): raise PermissionError('interrupted after intent; no dispatch')
            result=call_tool(TOOL,deepcopy(request))
            captured=now().isoformat()
            if not isinstance(result,dict): raise ValueError('unknown MCP envelope')
            content=result.get('content')
            if not isinstance(content,list) or len(content)!=1 or content[0].get('type')!='text' or not isinstance(content[0].get('text'),str):
                raise ValueError('raw MCP text unavailable; cannot invent source bytes')
            raw=content[0]['text'].encode('utf-8')
            if len(raw)>self.plan['max_raw_page_bytes']:
                save('response.txt',raw[:self.plan['max_raw_page_bytes']])
                save('failure.json',_bytes(dict(reason='oversized_response',received_bytes=len(raw),
                    full_received_sha256=hashlib.sha256(raw).hexdigest(),stored_prefix_only=True)))
                raise ValueError('response exceeds 2 MiB')
            save('response.txt',raw)
            if result.get('isError') is True: raise ValueError('MCP error response')
            payload=decode_artifact(raw.decode('utf-8'))
            rows=payload.get('history')
            if not isinstance(rows,list): raise ValueError('missing history records')
            count=len(rows)
            if count>=request['limit']: raise ValueError('saturated limit or excessive records')
            if payload.get('symbol')!='PETR4' or payload.get('period')!=request['period']: raise ValueError('response scope differs')
            if any(not isinstance(r,dict) or not request['datetime_from']<=r.get('time','')<request['datetime_to'] for r in rows):
                raise ValueError('temporal range or timestamp representation incompatible')
            # These fields are requirements, NOT claims about the unprobed MCP.
            if payload.get('complete') is not True or payload.get('truncated') is True:
                raise ValueError('response completeness unconfirmed')
            if payload.get('timezone') not in ('UTC','explicit_offsets'):
                raise ValueError('temporal semantics/broker timezone remain unknown')
            if payload.get('datetime_from')!=request['datetime_from'] or payload.get('datetime_to')!=request['datetime_to']:
                raise ValueError('request datetime interpretation not echoed by provider')
            if payload.get('connection')!=self.plan['connection']: raise ValueError('response installation identity unconfirmed')
            audit=audit_snapshot(payload,source_id=f'call-{self.calls:06d}',timezone_label=payload['timezone'],
                capture_time=captured,file_sha256=hashlib.sha256(raw).hexdigest(),origin='Rico-DEMO_MCP_received_text')
            save('audit.json',_bytes(audit))
            if audit['errors'] or not rows: raise ValueError('invalid data or availability not established')
            related=[a for a in self.audits if any(request['datetime_from']<=r['time']<request['datetime_to'] for r in a['records'])]
            if audit_collection([*related,audit])['classification']=='invalid': raise ValueError('M1/M5 conflict')
            if clock()-started+self.elapsed>=self.plan['max_elapsed_seconds']: raise TimeoutError('processing deadline exceeded')
            check_window(now())
            if stop(): raise PermissionError('cooperative interruption after response')
            outcome='observed_partial'
        except BaseException as exc:
            error_type=type(exc).__name__
            if 'failure.json' not in files: save('failure.json',_bytes(dict(error_type=error_type,reason=str(exc)[:250])))
            raise
        finally:
            receipt=dict(schema_version='3.3G-receipt-1',request=request,intent_sha256=fingerprint(intent),
                previous_receipt_sha256=self.receipts[-1]['receipt_sha256'] if self.receipts else None,
                files=files,outcome=outcome,error_type=error_type,record_count=count,
                captured_at=captured,recorded_at=now().isoformat(),elapsed_seconds=clock()-started,
                raw_format='MCP_text_UTF8_not_HTTP_wire',broker_timezone_certified=False,
                coverage_certified=False,live_execution_enabled=False)
            receipt['receipt_sha256']=fingerprint(receipt)
            _save(folder/'receipt.json',_bytes(receipt))
        self.reload()
        return deepcopy(receipt)
