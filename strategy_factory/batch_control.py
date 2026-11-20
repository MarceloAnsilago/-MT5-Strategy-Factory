"""Durable OFFLINE batch simulation. No MCP transport or live backend exists here."""
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import uuid

from .analysis import summarize_run,read_artifact
from .batch_manifest import validate_manifest,fingerprint,identifier,make_authorization,validate_authorization


class BatchBlocked(RuntimeError):
    pass


class BatchController:
    def __init__(self,root='runs/batches',*,free_bytes=None):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.free_bytes=free_bytes or (lambda:shutil.disk_usage(self.root).free)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, manifest TEXT NOT NULL, digest TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, batch TEXT, time TEXT, state TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS approvals (id TEXT PRIMARY KEY, batch TEXT, record TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS revocations (id TEXT PRIMARY KEY, reason TEXT NOT NULL)')

    @contextmanager
    def _db(self):
        db=sqlite3.connect(self.root/'control.sqlite',timeout=5)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _load(self,db,batch_id,*,verify_snapshot=True):
        identifier(batch_id)
        row=db.execute('SELECT manifest,digest,state FROM batches WHERE id=?',(batch_id,)).fetchone()
        if row is None:
            raise ValueError('unknown batch')
        manifest=validate_manifest(json.loads(row[0]))
        if fingerprint(manifest)!=row[1] or (verify_snapshot and fingerprint(validate_manifest(read_artifact(self.root/batch_id/'manifest.json')))!=row[1]):
            raise BatchBlocked('manifest snapshot changed; existing batch cannot be reused')
        return manifest,json.loads(row[2])

    def _save(self,db,batch_id,state):
        encoded=json.dumps(state,allow_nan=False,sort_keys=True)
        db.execute('UPDATE batches SET state=? WHERE id=?',(encoded,batch_id))
        db.execute('INSERT INTO events(batch,time,state) VALUES(?,?,?)',
                   (batch_id,datetime.now(timezone.utc).isoformat(),encoded))

    def _usage(self,batch_id):
        return sum(path.stat().st_size for path in (self.root/batch_id).rglob('*') if path.is_file())

    def _write(self,manifest,relative,value,run_directory=None):
        encoded=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        budget=manifest['budget']
        batch_id=manifest['batch_id']
        used=self._usage(batch_id)
        if used+len(encoded)>budget['max_artifact_bytes'] or self.free_bytes()-len(encoded)<budget['min_free_disk_bytes']:
            raise BatchBlocked('artifact or free-disk budget exceeded')
        if run_directory is not None:
            run_root=self.root/batch_id/run_directory
            current=sum(p.stat().st_size for p in run_root.rglob('*') if p.is_file()) if run_root.exists() else 0
            if current+len(encoded)>budget['max_run_artifact_bytes']:
                raise BatchBlocked('per-attempt artifact budget exceeded')
        target=self.root/batch_id/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        # Binary exclusive write makes accounting exact on Windows (no CRLF expansion).
        with target.open('xb') as stream:
            stream.write(encoded)

    def plan(self,document):
        manifest=validate_manifest(document)
        with self._worker(manifest['batch_id']):
            return self._plan(manifest)

    def _plan(self,document):
        manifest=validate_manifest(document)
        batch_id=manifest['batch_id']
        checksum=fingerprint(manifest)
        with self._db() as db:
            existing=db.execute('SELECT digest FROM batches WHERE id=?',(batch_id,)).fetchone()
            if existing:
                if existing[0]!=checksum:
                    raise BatchBlocked('batch ID already belongs to another manifest')
                return deepcopy(self._load(db,batch_id)[1])
            directory=self.root/batch_id
            directory.mkdir(exist_ok=False)
            # Failed preparation leaves its directory intact; never replace it.
            self._write(manifest,Path('manifest.json'),manifest)
            state=dict(batch_id=batch_id,manifest_sha256=checksum,status='planned',cancel_requested=False,
                simulation_seconds_used=0,live_execution_enabled=False,
                warnings=['live_batch_execution_disabled','manifest_hash_does_not_verify_runtime_ea_history_or_costs',
                          'artifact_quota_excludes_control_database_and_mt5_cache']+
                         ['declared_compiled_hash_unavailable:'+s['strategy_id'] for s in manifest['strategies'] if s['ea']['compiled_sha256'] is None],
                runs={r['run_id']:{'status':'pending','attempts':[]} for r in manifest['runs']})
            db.execute('INSERT INTO batches VALUES(?,?,?,?)',
                       (batch_id,json.dumps(manifest,allow_nan=False),checksum,json.dumps(state)))
            self._save(db,batch_id,state)
            return deepcopy(state)

    def status(self,batch_id):
        with self._db() as db:
            return deepcopy(self._load(db,batch_id)[1])

    def cancel(self,batch_id):
        with self._db() as db:
            # Cancellation must remain recordable even if the external snapshot changed.
            _,state=self._load(db,batch_id,verify_snapshot=False)
            if state['status']=='simulated':
                return deepcopy(state)
            state['cancel_requested']=True
            db.execute("INSERT OR IGNORE INTO revocations SELECT id, 'batch_cancelled' FROM approvals WHERE batch=?",(batch_id,))
            active=any(r['status']=='simulating' for r in state['runs'].values())
            state['status']='cancel_requested' if active else 'cancelled'
            for run in state['runs'].values():
                if run['status']=='pending':
                    run['status']='cancelled'
            self._save(db,batch_id,state)
            return deepcopy(state)

    def authorization(self,batch_id,*,approval,approved_by,expires_at,permitted_attempts=None,now=None):
        with self._worker(batch_id):
            return self._authorization(batch_id,approval=approval,approved_by=approved_by,
                expires_at=expires_at,permitted_attempts=permitted_attempts,now=now)

    def _authorization(self,batch_id,*,approval,approved_by,expires_at,permitted_attempts=None,now=None):
        """Persist a human-intent record; no executable permission is minted."""
        with self._db() as db:
            manifest,_=self._load(db,batch_id)
            record=make_authorization(manifest,approval=approval,approved_by=approved_by,
                expires_at=expires_at,permitted_attempts=permitted_attempts,now=now)
            self._write(manifest,Path('authorizations')/(record['authorization_id']+'.json'),record)
            db.execute('INSERT INTO approvals VALUES(?,?,?)',
                       (record['authorization_id'],batch_id,json.dumps(record,allow_nan=False)))
            return record

    def check_authorization(self,batch_id,record,*,run_id,attempt,now=None):
        with self._db() as db:
            manifest,state=self._load(db,batch_id)
            if state['cancel_requested'] or state['status'] in ('cancelled','interrupted','simulating','cancel_requested','simulated'):
                raise PermissionError('batch state does not allow authorization consumption')
            validate_authorization(manifest,record,now=now)
            stored=db.execute('SELECT record FROM approvals WHERE id=?',(record['authorization_id'],)).fetchone()
            if stored is None or fingerprint(json.loads(stored[0]))!=fingerprint(record):
                raise PermissionError('authorization not registered or altered')
            if db.execute('SELECT 1 FROM revocations WHERE id=?',(record['authorization_id'],)).fetchone():
                raise PermissionError('authorization revoked by cancellation')
            if type(attempt) is not int or attempt not in record['permitted_attempts'].get(run_id,[]):
                raise PermissionError('attempt not explicitly authorized')
            if any(a['attempt']==attempt for a in state['runs'][run_id]['attempts']):
                raise PermissionError('attempt already reserved/consumed; no replay')
            return {'valid_for_planning':True,'live_execution_enabled':False}

    def execute(self,*args,**kwargs):
        raise PermissionError('live batch backend is disabled in phase 2.6, including with a valid authorization')

    @contextmanager
    def _worker(self,batch_id):
        lock=self.root/'simulation.lock'
        with lock.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps({'batch_id':batch_id,'pid':os.getpid()}))
        try:
            yield
        finally:
            lock.unlink(missing_ok=True)

    def resume_plan(self,batch_id,selected):
        """Explicit next-attempt selection; not a retry loop or live approval."""
        with self._db() as db:
            manifest,state=self._load(db,batch_id)
            if state['status'] in ('simulating','cancel_requested','simulated'):
                raise BatchBlocked('batch is active or already completed')
            if not isinstance(selected,dict) or not selected:
                raise ValueError('explicit run/attempt selection required')
            for run_id,attempt in selected.items():
                if run_id not in state['runs']:
                    raise ValueError('unknown run')
                run=state['runs'][run_id]
                if run['status'] in ('simulated','simulating') or type(attempt) is not int or attempt!=len(run['attempts'])+1:
                    raise BatchBlocked('completed, active or duplicate attempt')
                if attempt>manifest['budget']['max_attempts_per_test']:
                    raise BatchBlocked('attempt budget exhausted')
            return dict(schema_version='1.0',resume_id=uuid.uuid4().hex,batch_id=batch_id,
                manifest_sha256=state['manifest_sha256'],selected=dict(selected),simulation_only=True)

    def recover_interrupted(self,batch_id):
        """Only when no worker owns the shared lock. Never replay the uncertain attempt."""
        with self._worker(batch_id):
            with self._db() as db:
                _,state=self._load(db,batch_id)
                if not any(run['status']=='simulating' for run in state['runs'].values()):
                    raise BatchBlocked('no interrupted reservation to reconcile')
                for run in state['runs'].values():
                    if run['status']=='simulating':
                        run['status']='interrupted'
                        run['attempts'][-1]['status']='interrupted'
                state['status']='interrupted'
                self._save(db,batch_id,state)
                return deepcopy(state)

    def simulate(self,batch_id,*,outcomes=None,cancel_after=None,resume=None):
        """Deterministic logical-time simulation, without sleeps, callbacks or MCP.

        outcomes[run_id] may specify status, duration_seconds and partial_note.
        No external runner/transport is accepted. Simulation consumes attempt IDs.
        """
        outcomes=outcomes or {}
        with self._worker(batch_id):
            with self._db() as db:
                manifest,state=self._load(db,batch_id)
                if resume is None:
                    if state['status']!='planned':
                        raise BatchBlocked('explicit resume plan required; no automatic repetition')
                    selected={r:1 for r in state['runs']}
                else:
                    required={'schema_version','resume_id','batch_id','manifest_sha256','selected','simulation_only'}
                    if set(resume)!=required or resume['schema_version']!='1.0' or resume['simulation_only'] is not True or resume['batch_id']!=batch_id or resume['manifest_sha256']!=fingerprint(manifest):
                        raise PermissionError('invalid or outdated resume plan')
                    identifier(resume['resume_id'])
                    # Recheck persisted state, not just the proposal created earlier.
                    selected=resume['selected']
                    if not selected or state['status'] in ('simulating','cancel_requested','simulated'):
                        raise BatchBlocked('resume is not applicable')
                    for run_id,attempt in selected.items():
                        run=state['runs'].get(run_id)
                        if run is None or run['status'] in ('simulated','simulating') or type(attempt) is not int or attempt!=len(run['attempts'])+1 or attempt>manifest['budget']['max_attempts_per_test']:
                            raise BatchBlocked('resume would duplicate or exceed an attempt')
                if set(outcomes)-set(selected):
                    raise ValueError('simulation outcome outside selected runs')
                if cancel_after is not None and (type(cancel_after) is not int or cancel_after<0):
                    raise ValueError('invalid cancellation boundary')
                state['status']='simulating'
                state['cancel_requested']=False
                self._save(db,batch_id,state)
            started=time.monotonic()
            finished=0
            try:
                for spec in manifest['runs']:
                    run_id=spec['run_id']
                    if run_id not in selected:
                        continue
                    if cancel_after is not None and finished>=cancel_after:
                        self.cancel(batch_id)
                    with self._db() as db:
                        _,state=self._load(db,batch_id)
                        if state['cancel_requested']:
                            state['status']='cancelled'
                            self._save(db,batch_id,state)
                            return deepcopy(state)
                        budget=manifest['budget']
                        total=sum(len(r['attempts']) for r in state['runs'].values())
                        if total>=budget['max_backtests'] or state['simulation_seconds_used']+budget['timeout_per_test_seconds']>budget['timeout_batch_seconds'] or time.monotonic()-started>=budget['timeout_batch_seconds']:
                            raise BatchBlocked('attempt or time budget exhausted')
                        if self._usage(batch_id)>=budget['max_artifact_bytes'] or self.free_bytes()<budget['min_free_disk_bytes']:
                            raise BatchBlocked('storage budget exhausted')
                        attempt=selected[run_id]
                        state['runs'][run_id]['status']='simulating'
                        state['runs'][run_id]['attempts'].append({'attempt':attempt,'status':'simulating'})
                        self._save(db,batch_id,state) # Durable consumption BEFORE creating any result.
                    relative=Path('runs')/run_id/('attempt_'+str(attempt))
                    outcome=outcomes.get(run_id,{})
                    if not isinstance(outcome,dict) or set(outcome)-{'status','duration_seconds','partial_note'}:
                        raise ValueError('invalid synthetic outcome')
                    duration=outcome.get('duration_seconds',0)
                    if type(duration) not in (int,float) or not 0<=duration<1e100:
                        raise ValueError('invalid synthetic duration')
                    outcome_status=outcome.get('status','simulated')
                    if outcome_status not in ('simulated','failed'):
                        raise ValueError('invalid synthetic status')
                    if duration>budget['timeout_per_test_seconds']:
                        outcome_status='failed'
                    self._write(manifest,relative/'attempt.json',{'simulation_only':True,'run_id':run_id,
                        'attempt':attempt,'manifest_sha256':fingerprint(manifest),'requested':spec,
                        'synthetic_duration_seconds':duration,'outcome':outcome_status},relative)
                    if 'partial_note' in outcome:
                        self._write(manifest,relative/'partial.json',{'synthetic':True,'note':outcome['partial_note']},relative)
                    strategy=next(s for s in manifest['strategies'] if s['strategy_id']==spec['strategy_id'])
                    summary=summarize_run(None,parameters=dict(spec['parameters'],expert=strategy['ea']['path']),
                        local_run_id=batch_id+'_'+run_id+'_'+str(attempt),inputs=spec['inputs'],
                        execution={'status':'failed' if outcome_status=='failed' else 'simulated',
                                   'timeout_seconds':budget['timeout_per_test_seconds']})
                    summary['batch_context']=dict(batch_id=batch_id,manifest_sha256=fingerprint(manifest),
                        strategy_id=strategy['strategy_id'],strategy_version=strategy['version'],
                        declared_ea_hashes=dict(compiled_sha256=strategy['ea']['compiled_sha256'],source_sha256=strategy['ea']['source_sha256']),
                        hash_provenance='declared_not_runtime_verified',attempt=attempt,simulation_only=True)
                    summary['evidence_kind']='simulation'
                    summary['warnings'].append('declared_ea_hashes_not_runtime_verified')
                    self._write(manifest,relative/'run_summary.json',summary,relative)
                    with self._db() as db:
                        _,state=self._load(db,batch_id)
                        state['simulation_seconds_used']+=min(duration,budget['timeout_per_test_seconds'])
                        run=state['runs'][run_id]
                        run['status']=outcome_status
                        run['attempts'][-1].update(status=outcome_status,synthetic_duration_seconds=duration,
                            timeout=duration>budget['timeout_per_test_seconds'])
                        if outcome_status=='failed':
                            state['status']='failed'
                        self._save(db,batch_id,state)
                        if outcome_status=='failed':
                            return deepcopy(state) # Fail fast; no implicit next attempt.
                    finished+=1
                with self._db() as db:
                    _,state=self._load(db,batch_id)
                    state['status']='cancelled' if state['cancel_requested'] else ('simulated' if all(r['status']=='simulated' for r in state['runs'].values()) else 'paused')
                    self._save(db,batch_id,state)
                    return deepcopy(state)
            except Exception as exc:
                with self._db() as db:
                    _,state=self._load(db,batch_id,verify_snapshot=False)
                    for run in state['runs'].values():
                        if run['status']=='simulating':
                            run['status']='interrupted'
                            run['attempts'][-1]['status']='interrupted'
                    state['status']='blocked' if isinstance(exc,BatchBlocked) else 'failed'
                    state['error_type']=type(exc).__name__ # Never persist a possibly sensitive exception message.
                    self._save(db,batch_id,state)
                raise
