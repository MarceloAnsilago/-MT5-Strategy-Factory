"""Prepared connection boundary. Native binding is intentionally absent.

Reuses the history port, identity/error contracts and persistence primitives.
The diagnostic laboratory cannot acquire history or accept a live port.
"""
from copy import deepcopy
from datetime import timedelta
import hashlib
from pathlib import Path, PureWindowsPath
import sqlite3
import shutil
from contextlib import closing
import time

from .batch_manifest import fingerprint, exact, sha
from .python_history_adapter import (PythonHistoryPort, INSTALLATION, MQL5_SHA256,
    proposal, utc, verify_identity, error_record, logical_key, reject_prior_overlap,
    _save, _read, _encode)

ROOT=Path(__file__).resolve().parents[1]/'runs'/'python_bridge_lab'
METHODS=('initialize','terminal_info','account_info','symbol_info','last_error','shutdown')


class PreparedPythonBridge(PythonHistoryPort):
    """No library reference, loader, callback, approval flag or native entrypoint."""
    acquisition_enabled=False
    live_execution_enabled=False

    def _disabled(self,*args,**kwargs):
        raise PermissionError('NATIVE_PYTHON_BRIDGE_DISABLED: separate human approval and implementation review required')

    initialize=_disabled
    terminal_info=_disabled
    account_info=_disabled
    symbol_info=_disabled
    copy_rates_range=_disabled
    last_error=_disabled
    shutdown=_disabled


def diagnostic_proposal():
    return dict(schema_version='python-connection-diagnostic-proposal-1',status='PROPOSED_NOT_APPROVED',
        acquisition_enabled=False,live_execution_enabled=False,backend='python_mt5',
        installation=INSTALLATION,exe='terminal64.exe',mql5_path_sha256=MQL5_SHA256,
        build=6230,server='Rico-DEMO',account_binding=None,valid_from=None,valid_to=None,
        allowed_functions=list(METHODS),history_queries_allowed=False,allow_terminal_launch=False,
        native_attach_only_guaranteed=False,require_existing_exclusive_process=True,
        executable_sha256=None,executable_file_id=None,process_binding=None,
        python_executable=None,package_version='5.0.5430',
        limits=dict(max_operations=16,initialize_timeout_ms=5000,shutdown_reserved_operations=2,
            metadata_timeout_seconds=5,shutdown_timeout_seconds=5,total_seconds=30,
            storage_bytes=1048576,min_free_bytes=4294967296,max_concurrency=1),
        automatic_retries=False,approval_required=True)


def validate_process_attestation(evidence):
    """Pure validation of submitted evidence, not process enumeration or file IO.

    A trusted future observer must resolve file identities/junctions and keep
    process exclusivity; submitted strings and hashes do not prove authenticity.
    """
    exact(evidence,{'exe','resolved_exe','exe_sha256','expected_exe_sha256','file_id','expected_file_id',
        'resolved_data_path','reparse_detected','processes','observed_at'},'process attestation')
    expected=PureWindowsPath(INSTALLATION)/'terminal64.exe'
    for key in ('exe','resolved_exe'):
        if PureWindowsPath(evidence[key])!=expected: raise PermissionError('incorrect terminal executable')
    for key in ('exe_sha256','expected_exe_sha256'):sha(evidence[key])
    if (not evidence['exe_sha256'] or evidence['exe_sha256']!=evidence['expected_exe_sha256'] or
        not isinstance(evidence['file_id'],str) or not evidence['file_id'] or evidence['file_id']!=evidence['expected_file_id'] or
        evidence['reparse_detected'] is not False): raise PermissionError('executable identity or junction unresolved')
    mql5=str(PureWindowsPath(evidence['resolved_data_path'])/'MQL5')
    if hashlib.sha256(mql5.casefold().encode()).hexdigest()!=MQL5_SHA256: raise PermissionError('wrong data directory')
    processes=evidence['processes']
    if not isinstance(processes,list) or len(processes)!=1: raise PermissionError('existing exclusive terminal required; no autostart')
    process=processes[0]
    exact(process,{'pid','exe','file_id','data_path','started_at'},'process identity')
    if (type(process['pid']) is not int or process['pid']<1 or PureWindowsPath(process['exe'])!=expected or
        process['file_id']!=evidence['file_id'] or PureWindowsPath(process['data_path'])!=PureWindowsPath(evidence['resolved_data_path'])):
        raise PermissionError('wrong or ambiguous process')
    if utc(process['started_at'])>utc(evidence['observed_at']):raise PermissionError('future process start time')
    return fingerprint(evidence)


class RecordedConnectionPort:
    """Finite synthetic return values, with no reference to the native package."""
    def __init__(self, sequence):self.sequence=deepcopy(sequence);self.calls=[];self.arguments=[]

    def _invoke(self,name,arguments=None):
        self.calls.append(name)
        self.arguments.append(deepcopy(arguments or {}))
        if not self.sequence: raise ValueError('synthetic sequence exhausted')
        expected,value=self.sequence.pop(0)
        if name!=expected:raise ValueError('last_error must immediately follow its operation')
        if isinstance(value,BaseException):raise value
        return deepcopy(value)


def _private_root(root):
    supplied=Path(root).absolute()
    for p in (supplied,*supplied.parents):
        try:info=p.lstat()
        except FileNotFoundError:continue
        if p.is_symlink() or getattr(info,'st_file_attributes',0)&0x400:raise PermissionError('unsafe laboratory path')
    resolved=supplied.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or resolved==ROOT.resolve():raise PermissionError('separate bridge laboratory required')
    return resolved


class ConnectionDiagnosticLab:
    """Single-use connection-contract simulator, not a second history controller.

    Each operation and immediate last_error consume durable budget. Shutdown
    has a separate reserve and is attempted after simulated initialization,
    even on identity failure. Cleanup never retries an earlier operation.
    """
    def __init__(self,root,consent,*,now):
        self.root=_private_root(root);self.consent=deepcopy(consent)
        self._consent(now)
        self.root.mkdir(parents=True,exist_ok=False)
        self.manifest=dict(synthetic_only=True,plan_sha256=fingerprint(diagnostic_proposal()),
            consent_sha256=fingerprint(consent),acquisition_enabled=False)
        _save(self.root/'session.json',_encode(self.manifest))

    def _consent(self,now):
        exact(self.consent,{'purpose','plan_sha256','from_utc','to_utc','account_binding'},'connection fixture consent')
        c=self.consent
        if (c['purpose']!='synthetic_connection_only' or c['plan_sha256']!=fingerprint(diagnostic_proposal()) or
            c['account_binding']!='synthetic-demo-account' or not utc(c['from_utc'])<=now<utc(c['to_utc']) or
            utc(c['to_utc'])-utc(c['from_utc'])>timedelta(hours=1)):
            raise PermissionError('separate synthetic consent required; old MCP approvals forbidden')

    def run(self,port,evidence,*,now,clock=time.monotonic,stop=lambda:False,free_bytes=None):
        if type(port) is not RecordedConnectionPort:raise PermissionError('finite synthetic connection port only')
        self._consent(now())
        if _read(self.root/'session.json')!=self.manifest or fingerprint(self.consent)!=self.manifest['consent_sha256']:
            raise PermissionError('diagnostic consent or session changed')
        digest=validate_process_attestation(evidence)
        age=now()-utc(evidence['observed_at'])
        if not timedelta(0)<=age<=timedelta(seconds=5):raise PermissionError('stale process evidence')
        if any(p.name!='session.json' for p in self.root.iterdir()):raise PermissionError('single-use diagnostic; no repetition or unknown-outcome recovery')
        if stop():raise PermissionError('interrupted before initialization')
        limits=diagnostic_proposal()['limits'];started=clock();used=0;events=[];primary=None;cleanup_error=None
        available=free_bytes or (lambda:shutil.disk_usage(self.root).free)
        started_initialize=False
        def invoke(name,cleanup=False):
            nonlocal used,started_initialize
            cap=limits['max_operations'] if cleanup else limits['max_operations']-limits['shutdown_reserved_operations']
            if used+2>cap:raise PermissionError('operation budget exhausted')
            if not cleanup:
                self._consent(now())
                if stop():raise PermissionError('cooperative interruption')
                if clock()-started>=limits['total_seconds']:raise TimeoutError('diagnostic total deadline')
            if available()<limits['min_free_bytes']+limits['storage_bytes']:raise OSError('storage reserve missing')
            folder=self.root/f'operation-{used:03d}';folder.mkdir(exist_ok=False)
            _save(folder/'intent.json',_encode(dict(operation=name,last_error_reserved=True,
                process_evidence_sha256=digest,synthetic_only=True)))
            used+=2  # Unknown outcomes still consume both reserved operations.
            before=clock();result=None;err=None;failure=None
            try:
                if name=='initialize':started_initialize=True
                arguments=dict(path=str(PureWindowsPath(INSTALLATION)/'terminal64.exe'),
                    timeout=limits['initialize_timeout_ms'],portable=False) if name=='initialize' else dict(symbol='PETR4') if name=='symbol_info' else {}
                result=RecordedConnectionPort._invoke(port,name,arguments)
                # No metadata or cleanup may intervene before this error capture.
                err=error_record(RecordedConnectionPort._invoke(port,'last_error'))
                if err['code']!=1:raise ValueError('library operation failed')
                bound=limits['shutdown_timeout_seconds'] if cleanup else limits['initialize_timeout_ms']/1000 if name=='initialize' else limits['metadata_timeout_seconds']
                if clock()-before>=bound:raise TimeoutError('operation deadline')
                if name=='initialize' and result is not True:raise PermissionError('initialization refused')
                if name not in ('initialize','shutdown') and result is None:raise ValueError('empty metadata response')
                if not cleanup and clock()-started>=limits['total_seconds']:raise TimeoutError('diagnostic total deadline')
                return result
            except BaseException as exc:
                failure=type(exc).__name__;raise
            finally:
                event=dict(operation=name,last_error=err,failure_type=failure,synthetic_only=True)
                events.append(event)
                _save(folder/'receipt.json',_encode(dict(event,event_sha256=fingerprint(event))))
        try:
            invoke('initialize')
            observation=dict(terminal=invoke('terminal_info'),account=invoke('account_info'),
                symbol=invoke('symbol_info'),observed_at=now().isoformat(),metadata_errors=[(1,'synthetic_success')]*3)
            verify_identity(observation,proposal(),self.consent['account_binding'],now())
            if stop():raise PermissionError('cooperative interruption')
            self._consent(now())
        except BaseException as exc:
            primary=type(exc).__name__
        finally:
            if started_initialize:
                try:invoke('shutdown',cleanup=True)
                except BaseException as exc:cleanup_error=type(exc).__name__
            report=dict(state='SYNTHETIC_DIAGNOSTIC_CHECKED' if primary is None and cleanup_error is None else 'BLOCKED',
                primary_error_type=primary,cleanup_error_type=cleanup_error,operations_reserved=used,events=events,
                process_evidence_sha256=digest,acquisition_enabled=False,live_execution_enabled=False,
                initialization_arguments_policy=dict(explicit_path=True,allow_launch=False,
                    real_initialize_allowed=False),elapsed_seconds=clock()-started)
            encoded=_encode(report)
            if sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file())+len(encoded)>limits['storage_bytes']:
                raise OSError('diagnostic storage cap exceeded')
            _save(self.root/'report.json',encoded)
        return report


class CrossBackendAttemptIndex:
    """Transactional shared index model, isolated to the synthetic bridge root.

    Imported original intents are read-only references rehashed before every
    transaction. Reservation is permanent: success/failure/unknown never makes
    a window new. No method can erase, approve or retry an older attempt.
    """
    def __init__(self,root,sources=()):
        self.root=_private_root(root);self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'attempts.sqlite'
        if self.path.is_symlink() or self.path.exists() and getattr(self.path.lstat(),'st_file_attributes',0)&0x400:
            raise PermissionError('unsafe attempt database path')
        self.sources=[Path(p).resolve() for p in sources]
        workspace=ROOT.parents[1]
        if any(not p.is_relative_to(workspace/'runs') for p in self.sources):raise PermissionError('read-only intent sources must remain in project runs')
        self.manifest=dict(synthetic_only=True,sources={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in self.sources})
        marker=self.root/'index.json'
        exists=marker.exists()
        if marker.exists():
            if _read(marker)!=self.manifest:raise PermissionError('attempt catalog changed')
            if not self.path.is_file():raise PermissionError('attempt database missing; never reset counters')
        else:_save(marker,_encode(self.manifest))
        with closing(sqlite3.connect(self.path)) as db:
            if exists:
                if db.execute('SELECT digest FROM metadata').fetchall()!=[(fingerprint(self.manifest),)]:
                    raise PermissionError('attempt database identity changed')
                db.execute('SELECT key FROM attempts LIMIT 1').fetchall()
            else:
                db.execute('CREATE TABLE attempts (key TEXT PRIMARY KEY, backend TEXT, request TEXT, context TEXT)')
                db.execute('CREATE TABLE metadata (digest TEXT NOT NULL)')
                db.execute('INSERT INTO metadata VALUES (?)',(fingerprint(self.manifest),));db.commit()

    def reserve_synthetic(self,page,*,backend,context_sha256):
        if backend not in ('mcp','python_mt5'):raise ValueError('known backend required')
        sha(context_sha256)
        if context_sha256 is None:raise ValueError('explicit synthetic context required')
        if {str(p) for p in self.sources}!=set(self.manifest['sources']) or self.path!=self.root/'attempts.sqlite':
            raise PermissionError('attempt source catalog detached or database path changed')
        prior=[]
        for p in self.sources:
            if hashlib.sha256(p.read_bytes()).hexdigest()!=self.manifest['sources'][str(p)]:raise PermissionError('source attempt changed')
            record=_read(p);request=record.get('request',record)
            if (request.get('symbol','PETR4')!='PETR4' or request.get('period',request.get('timeframe')) not in ('M1','M5') or
                not isinstance(request.get('datetime_from',request.get('from_utc')),str) or
                not isinstance(request.get('datetime_to',request.get('to_utc')),str)):
                raise PermissionError('uninterpretable source attempt; catalog review required')
            prior.append(record)
        if _read(self.root/'index.json')!=self.manifest:raise PermissionError('index source manifest changed')
        key=logical_key(page)
        with closing(sqlite3.connect(self.path,timeout=1)) as db:
            db.execute('BEGIN IMMEDIATE')
            prior.extend(_read_request(row[0]) for row in db.execute('SELECT request FROM attempts'))
            reject_prior_overlap(page,prior)
            db.execute('INSERT INTO attempts VALUES (?,?,?,?)',(key,backend,_encode(page).decode(),context_sha256))
            db.commit()
        return key


def _read_request(text):
    from .analysis import decode_artifact
    return decode_artifact(text)
