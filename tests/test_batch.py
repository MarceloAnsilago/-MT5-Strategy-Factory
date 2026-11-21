"""Offline unit/integration tests. No MT5 adapters or live authorization used."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_manifest import validate_manifest,fingerprint,approval_phrase,make_authorization,validate_authorization,manifest_schema
from strategy_factory.batch_control import BatchController,BatchBlocked

ROOT=Path(__file__).resolve().parents[1]
EXAMPLE=ROOT/'config/batches/example.json'
NOW=datetime(2026,11,20,12,0,tzinfo=timezone.utc)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.manifest=read_artifact(EXAMPLE)

    def test_example_and_schema_stay_in_sync(self):
        self.assertEqual(validate_manifest(self.manifest),self.manifest)
        self.assertEqual(read_artifact(ROOT/'config/batches/manifest.schema.json'),manifest_schema())

    def test_phase32e_examples_are_single_attempt_plans_with_fictitious_paths(self):
        for name in ('phase32e_rsi.example.json','phase32e_trend.example.json'):
            doc=validate_manifest(read_artifact(ROOT/'config/batches'/name))
            self.assertEqual(len(doc['strategies']),1);self.assertEqual(len(doc['runs']),1)
            self.assertEqual(doc['budget']['max_backtests'],1)
            self.assertEqual(doc['budget']['max_attempts_per_test'],1)
            self.assertEqual(doc['budget']['timeout_batch_seconds']-doc['budget']['timeout_per_test_seconds'],45)
            self.assertTrue(doc['policy']['simulation_default'])
            self.assertFalse(doc['policy']['allow_live_trading'])
            ea=doc['strategies'][0]['ea']
            self.assertTrue(ea['path'].startswith('C:\\MT5-LAB\\'))
            self.assertIsNone(ea['source_sha256']);self.assertIsNone(ea['compiled_sha256'])

    def test_canonical_hash_and_semantic_changes(self):
        reordered=dict(reversed(list(self.manifest.items())))
        self.assertEqual(fingerprint(self.manifest),fingerprint(reordered))
        changed=deepcopy(self.manifest)
        changed['revision']+=1
        self.assertNotEqual(fingerprint(changed),fingerprint(self.manifest))

    def test_unknown_sensitive_fields_and_policies_rejected(self):
        for changes in ({'api_token':'SYNTHETIC'}, {'schema_version':'2.0'}):
            document=dict(self.manifest,**changes)
            with self.assertRaises(ValueError):
                validate_manifest(document)
        for key,value in (('allow_live_trading',True),('optimization',True),('local_agents_only',False),('forward_mode',1),('automatic_retries',True)):
            document=deepcopy(self.manifest)
            document['policy'][key]=value
            with self.assertRaises(ValueError):
                validate_manifest(document)

    def test_count_time_concurrency_and_storage_validation(self):
        for key,value in (('max_strategies',0),('max_backtests',1),('timeout_batch_seconds',359),
                          ('max_attempts_per_test',True),('max_concurrency',2),('max_artifact_bytes',1),('min_free_disk_bytes',-1)):
            document=deepcopy(self.manifest)
            document['budget'][key]=value
            with self.assertRaises(ValueError):
                validate_manifest(document)
        document=deepcopy(self.manifest)
        extra=deepcopy(document['strategies'][0]);extra['strategy_id']='other'
        document['strategies'].append(extra)
        with self.assertRaises(ValueError):
            validate_manifest(document)

    def test_identifiers_duplicates_unknown_strategy_and_invalid_parameters(self):
        cases=[]
        doc=deepcopy(self.manifest);doc['batch_id']='../escape';cases.append(doc)
        doc=deepcopy(self.manifest);doc['runs'][1]['run_id']=doc['runs'][0]['run_id'];cases.append(doc)
        doc=deepcopy(self.manifest);doc['runs'][1]['strategy_id']='missing';cases.append(doc)
        doc=deepcopy(self.manifest);doc['runs'][1]['parameters']=deepcopy(doc['runs'][0]['parameters']);cases.append(doc)
        doc=deepcopy(self.manifest);doc['runs'][0]['parameters']['timeframe']='M7';cases.append(doc)
        doc=deepcopy(self.manifest);doc['strategies'][0]['ea']['path']='relative.ex5';cases.append(doc)
        doc=deepcopy(self.manifest);doc['strategies'][0]['ea']['compiled_sha256']='invalid';cases.append(doc)
        for document in cases:
            with self.assertRaises(ValueError):
                validate_manifest(document)

    def test_exact_approval_hash_scope_and_expiry(self):
        record=make_authorization(self.manifest,approval=approval_phrase(self.manifest),approved_by='synthetic-operator',
            expires_at=(NOW+timedelta(minutes=5)).isoformat(),now=NOW)
        self.assertTrue(validate_authorization(self.manifest,record,now=NOW))
        changed=deepcopy(self.manifest);changed['revision']+=1
        with self.assertRaises(PermissionError):
            validate_authorization(changed,record,now=NOW)
        with self.assertRaises(PermissionError):
            validate_authorization(self.manifest,record,now=NOW+timedelta(minutes=6))
        altered=deepcopy(record);altered['scope']='live_trading'
        with self.assertRaises(PermissionError):
            validate_authorization(self.manifest,altered,now=NOW)
        with self.assertRaises(PermissionError):
            make_authorization(self.manifest,approval='sim',approved_by='synthetic',expires_at=record['expires_at'],now=NOW)

    def test_attempt_permits_are_exact_not_automatic_retries(self):
        for scope in ({'missing':[1]},{'petr4-first':[2]},{'petr4-first':[True]},{'petr4-first':[1,1]}):
            with self.assertRaises(ValueError):
                make_authorization(self.manifest,approval=approval_phrase(self.manifest),approved_by='synthetic',
                    expires_at=(NOW+timedelta(minutes=5)).isoformat(),permitted_attempts=scope,now=NOW)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.manifest=read_artifact(EXAMPLE)
        self.controller=BatchController(self.root)
        self.batch=self.manifest['batch_id']

    def plan(self,retries=1):
        self.manifest['budget']['max_attempts_per_test']=retries
        self.manifest['budget']['max_backtests']=2*retries
        self.manifest['budget']['timeout_batch_seconds']=360*retries
        return self.controller.plan(self.manifest)

    def test_offline_simulation_preserves_summary_11_unknowns(self):
        self.plan()
        with patch.object(socket,'socket',side_effect=AssertionError('network forbidden')):
            state=self.controller.simulate(self.batch)
        self.assertEqual(state['status'],'simulated')
        self.assertFalse(state['live_execution_enabled'])
        self.assertEqual(sum(len(r['attempts']) for r in state['runs'].values()),2)
        summaries=list((self.root/self.batch).glob('runs/*/attempt_1/run_summary.json'))
        self.assertEqual(len(summaries),2)
        for path in summaries:
            summary=read_artifact(path)
            self.assertEqual(summary['schema_version'],'1.1')
            self.assertEqual(summary['evidence_kind'],'simulation')
            self.assertIsNone(summary['metrics']['net_profit']['value'])
            self.assertEqual(summary['traceability']['costs']['commission_total']['status'],'unverifiable')
            self.assertEqual(summary['batch_context']['hash_provenance'],'declared_not_runtime_verified')

    def test_idempotent_planning_and_no_duplicate_run(self):
        first=self.plan()
        self.assertEqual(self.controller.plan(self.manifest),first)
        self.controller.simulate(self.batch)
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch)
        changed=deepcopy(self.manifest);changed['revision']+=1
        with self.assertRaises(BatchBlocked):
            self.controller.plan(changed)

    def test_cancellation_and_explicit_resume_pending_only(self):
        self.plan()
        state=self.controller.simulate(self.batch,cancel_after=1)
        self.assertEqual(state['status'],'cancelled')
        self.assertEqual(state['runs']['petr4-first']['status'],'simulated')
        self.assertEqual(state['runs']['petr4-second']['status'],'cancelled')
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch)
        resume=self.controller.resume_plan(self.batch,{'petr4-second':1})
        state=self.controller.simulate(self.batch,resume=resume)
        self.assertEqual(state['status'],'simulated')
        self.assertEqual(len(state['runs']['petr4-first']['attempts']),1)
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch,resume=resume)

    def test_failure_preserves_partial_results_and_requires_new_attempt(self):
        self.plan(retries=2)
        state=self.controller.simulate(self.batch,outcomes={'petr4-first':{'status':'failed','partial_note':'SYNTHETIC partial'}})
        self.assertEqual(state['status'],'failed')
        self.assertEqual(state['runs']['petr4-second']['attempts'],[])
        failed_summary=read_artifact(self.root/self.batch/'runs/petr4-first/attempt_1/run_summary.json')
        self.assertEqual(failed_summary['evidence_kind'],'simulation')
        original=self.root/self.batch/'runs/petr4-first/attempt_1/partial.json'
        before=original.read_bytes()
        with self.assertRaises(BatchBlocked):
            self.controller.resume_plan(self.batch,{'petr4-first':1})
        resume=self.controller.resume_plan(self.batch,{'petr4-first':2,'petr4-second':1})
        state=self.controller.simulate(self.batch,resume=resume)
        self.assertEqual(state['status'],'simulated')
        self.assertEqual(original.read_bytes(),before)
        self.assertEqual(len(state['runs']['petr4-first']['attempts']),2)

    def test_timeout_failure_does_not_retry(self):
        self.plan()
        state=self.controller.simulate(self.batch,outcomes={'petr4-first':{'duration_seconds':181}})
        self.assertEqual(state['status'],'failed')
        attempt=state['runs']['petr4-first']['attempts'][0]
        self.assertTrue(attempt['timeout'])
        self.assertEqual(len(state['runs']['petr4-first']['attempts']),1)
        with self.assertRaises(BatchBlocked):
            self.controller.resume_plan(self.batch,{'petr4-first':2})

    def test_runtime_batch_budget_blocks_before_new_attempt(self):
        self.plan()
        with self.controller._db() as db:
            _,state=self.controller._load(db,self.batch)
            state['simulation_seconds_used']=181
            self.controller._save(db,self.batch,state)
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch)
        state=self.controller.status(self.batch)
        self.assertEqual(state['status'],'blocked')
        self.assertFalse(any(r['attempts'] for r in state['runs'].values()))

    def test_per_attempt_storage_blocks_and_preserves_first_artifact(self):
        self.manifest['budget']['max_run_artifact_bytes']=2200
        self.plan()
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch,outcomes={'petr4-first':{'partial_note':'SYNTHETIC' * 1000}})
        state=self.controller.status(self.batch)
        self.assertEqual(state['status'],'blocked')
        self.assertTrue((self.root/self.batch/'runs/petr4-first/attempt_1/attempt.json').exists())
        self.assertEqual(state['runs']['petr4-first']['status'],'interrupted')

    def test_disk_and_total_artifact_budget_block_before_start(self):
        self.plan()
        self.controller.free_bytes=lambda:0
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch)
        self.assertFalse(any(r['attempts'] for r in self.controller.status(self.batch)['runs'].values()))

    def test_total_owned_artifact_quota_counts_existing_bytes(self):
        self.plan()
        remaining=self.manifest['budget']['max_artifact_bytes']-self.controller._usage(self.batch)
        (self.root/self.batch/'synthetic_padding.bin').write_bytes(b'0'*remaining)
        with self.assertRaises(BatchBlocked):
            self.controller.simulate(self.batch)
        self.assertEqual(self.controller.status(self.batch)['status'],'blocked')
        self.assertFalse(any(r['attempts'] for r in self.controller.status(self.batch)['runs'].values()))

    def test_attempt_artifacts_are_exact_utf8_bytes_on_windows(self):
        self.plan()
        self.controller.simulate(self.batch)
        data=(self.root/self.batch/'runs/petr4-first/attempt_1/attempt.json').read_bytes()
        self.assertTrue(data.startswith(b'{\n'))
        self.assertNotIn(b'\r\n',data)

    def test_shared_worker_lock_blocks_other_batches_and_recovery(self):
        self.plan()
        (self.root/'simulation.lock').write_text('SYNTHETIC stale or busy owner')
        with self.assertRaises(FileExistsError):
            self.controller.simulate(self.batch)
        with self.assertRaises(FileExistsError):
            self.controller.recover_interrupted(self.batch)
        self.assertEqual(self.controller.status(self.batch)['status'],'planned')

    def test_crash_reservation_recovery_consumes_attempt(self):
        self.plan(retries=2)
        with patch.object(self.controller,'_write',side_effect=SystemExit('SYNTHETIC interruption')):
            with self.assertRaises(SystemExit):
                self.controller.simulate(self.batch)
        self.assertEqual(self.controller.status(self.batch)['runs']['petr4-first']['status'],'simulating')
        recovered=self.controller.recover_interrupted(self.batch)
        self.assertEqual(recovered['runs']['petr4-first']['status'],'interrupted')
        with self.assertRaises(BatchBlocked):
            self.controller.resume_plan(self.batch,{'petr4-first':1})
        with self.assertRaises(BatchBlocked):
            self.controller.recover_interrupted(self.batch)

    def test_manifest_tampering_and_resume_hash_changes_are_blocked(self):
        self.plan()
        self.controller.cancel(self.batch)
        resume=self.controller.resume_plan(self.batch,{'petr4-first':1})
        resume['manifest_sha256']='0'*64
        with self.assertRaises(PermissionError):
            self.controller.simulate(self.batch,resume=resume)
        path=self.root/self.batch/'manifest.json'
        document=read_artifact(path);document['revision']+=1
        path.write_text(json.dumps(document))
        with self.assertRaises(BatchBlocked):
            self.controller.status(self.batch)
        self.assertEqual(self.controller.cancel(self.batch)['status'],'cancelled')

    def test_registered_approval_is_scoped_and_cannot_enable_live_backend(self):
        self.plan()
        record=self.controller.authorization(self.batch,approval=approval_phrase(self.manifest),approved_by='synthetic',
                expires_at=(NOW+timedelta(minutes=5)).isoformat(),now=NOW)
        check=self.controller.check_authorization(self.batch,record,run_id='petr4-first',attempt=1,now=NOW)
        self.assertFalse(check['live_execution_enabled'])
        with self.assertRaises(PermissionError):
            self.controller.execute(self.batch,authorization=record)
        for attempt in (True,2):
            with self.assertRaises(PermissionError):
                self.controller.check_authorization(self.batch,record,run_id='petr4-first',attempt=attempt,now=NOW)
        altered=deepcopy(record);altered['approved_by']='another'
        with self.assertRaises(PermissionError):
            self.controller.check_authorization(self.batch,altered,run_id='petr4-first',attempt=1,now=NOW)
        self.controller.cancel(self.batch)
        with self.assertRaises(PermissionError):
            self.controller.check_authorization(self.batch,record,run_id='petr4-first',attempt=1,now=NOW)

    def test_cancellation_revocation_survives_resume(self):
        self.plan()
        record=self.controller.authorization(self.batch,approval=approval_phrase(self.manifest),approved_by='synthetic',
                expires_at=(NOW+timedelta(minutes=5)).isoformat(),now=NOW)
        self.controller.cancel(self.batch)
        resume=self.controller.resume_plan(self.batch,{'petr4-second':1})
        state=self.controller.simulate(self.batch,resume=resume)
        self.assertEqual(state['status'],'paused')
        with self.assertRaises(PermissionError):
            self.controller.check_authorization(self.batch,record,run_id='petr4-first',attempt=1,now=NOW)

    def test_consumed_failed_attempt_cannot_reuse_approval(self):
        self.plan()
        record=self.controller.authorization(self.batch,approval=approval_phrase(self.manifest),approved_by='synthetic',
                expires_at=(NOW+timedelta(minutes=5)).isoformat(),now=NOW)
        self.controller.simulate(self.batch,outcomes={'petr4-first':{'status':'failed'}})
        with self.assertRaises(PermissionError):
            self.controller.check_authorization(self.batch,record,run_id='petr4-first',attempt=1,now=NOW)

    def test_cli_offline_workflow(self):
        for command in ('validate','propose-authorization','simulate'):
            result=subprocess.run([sys.executable,'-m','strategy_factory.batch','--root',str(self.root),command,str(EXAMPLE)],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertFalse(json.loads(result.stdout)['live_execution_enabled'])


if __name__=='__main__':
    unittest.main()
