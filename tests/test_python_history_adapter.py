"""Finite fixtures only: this suite forbids importing the terminal package."""
import builtins
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from strategy_factory.batch_manifest import fingerprint
from strategy_factory.python_history_adapter import (
    DisabledPythonHistoryAdapter, OfflinePythonHistoryAdapter, RecordedPythonSource,
    proposal, validate_plan, api_interval, logical_key, verify_identity, error_record,
    LAB_ROOT, OPERATION_COST, analyze_bars)

NOW=datetime(2026,11,24,12,tzinfo=timezone.utc)
DATA=r'C:\Users\User\AppData\Roaming\MetaQuotes\Terminal\38FF261A42172F3478E54D3A1A8FE02B'
DTYPE=[('time','<i8'),('open','<f8'),('high','<f8'),('low','<f8'),('close','<f8'),
       ('tick_volume','<u8'),('spread','<i4'),('real_volume','<u8')]


def observation():
    return dict(observed_at=NOW.isoformat(),
        terminal=dict(path=proposal()['installation'],data_path=DATA,build=6230,
                      name='Rico - MetaTrader 5',connected=True),
        account=dict(server='Rico-DEMO',trade_mode=0,binding='synthetic-demo-account'),
        symbol=dict(name='PETR4',select=True,custom=False),metadata_errors=[(1,'ok')]*3)


def times(page):
    start,end=api_interval(page)
    step=60 if page['timeframe']=='M1' else 300
    return list(range(int(start.timestamp()),int(end.timestamp())+1,step))


def consent():
    p=proposal()
    return dict(purpose='synthetic_offline_only',plan_sha256=fingerprint(p),
        from_utc=NOW.isoformat(),to_utc=(NOW+timedelta(hours=1)).isoformat(),
        account_binding='synthetic-demo-account',
        expected_grids={logical_key(r):times(r) for r in p['pages']})


def replies():
    return {logical_key(p):dict(before=observation(),after=observation(),last_error=(1,'Success'),
        bars=np.array([(t,10,12,9,11,10 if p['timeframe']=='M1' else 50,1,
                        100 if p['timeframe']=='M1' else 500) for t in times(p)],dtype=DTYPE))
        for p in proposal()['pages']}


class ContractTests(unittest.TestCase):
    def test_published_proposal_matches_code_and_grants_no_authorization(self):
        path=Path(__file__).resolve().parents[1]/'config/history/python_mt5.homologation.proposal.json'
        plan=json.loads(path.read_text(encoding='utf-8'))
        self.assertEqual(validate_plan(plan),proposal())
        for field in ('account_binding','valid_from','valid_to','calendar_evidence','prior_attempt_review'):
            self.assertIsNone(plan[field])
        self.assertFalse(plan['acquisition_enabled'])

    def test_real_adapter_is_unconditionally_disabled(self):
        adapter=DisabledPythonHistoryAdapter()
        for kwargs in ({},{'approved':True,'plan':proposal()}):
            with self.assertRaisesRegex(PermissionError,'DISABLED'):adapter.acquire(**kwargs)
        with self.assertRaises(PermissionError):adapter.initialize('terminal64.exe')

    def test_original_mcp_approval_cannot_enable_new_backend(self):
        from strategy_factory.history_transport import approval_scope
        with self.assertRaises(PermissionError):validate_plan(approval_scope())
        for key,value in [('acquisition_enabled',True),('status','APPROVED'),('account_binding','anything')]:
            with self.subTest(key=key),self.assertRaises(PermissionError):
                validate_plan(dict(proposal(),**{key:value}))

    def test_boolean_and_numeric_aliases_cannot_change_the_offline_contract(self):
        for key,value in [('acquisition_enabled',0),('live_execution_enabled',0),
                          ('automatic_retries',0),('max_concurrency',True),('build',6230.0)]:
            with self.subTest(key=key),self.assertRaises(PermissionError):
                validate_plan(dict(proposal(),**{key:value}))

    def test_extra_page_parameters_and_unbound_account_are_rejected(self):
        with self.assertRaises(ValueError):api_interval(dict(proposal()['pages'][0],symbol='OTHER'))
        for binding in (None,'',False):
            with self.subTest(binding=binding),self.assertRaises(PermissionError):
                verify_identity(observation(),proposal(),binding,NOW)

    def test_interval_utc_exclusive_end_and_invalid_inputs(self):
        page=proposal()['pages'][0]
        a,b=api_interval(page)
        self.assertEqual((b-a).total_seconds(),299)
        self.assertEqual(b.second,59)
        for delta in [dict(from_utc='2026-11-03T13:00:00'),dict(from_utc='2026-11-03T13:00:00-03:00'),
                      dict(timeframe='tick'),dict(to_utc=page['from_utc']),
                      dict(to_utc='2026-11-05T13:00:00+00:00'),dict(from_utc='2026-11-03T13:00:01+00:00')]:
            with self.subTest(delta=delta),self.assertRaises(ValueError):api_interval(dict(page,**delta))

    def test_identity_mismatches_and_private_fields_not_persisted(self):
        p=proposal();obs=observation()
        good=verify_identity(obs,p,'synthetic-demo-account',NOW)
        self.assertNotIn('binding',good)
        for part,key,value in [('terminal','path',r'C:\Other MT5'),('terminal','data_path',r'C:\OtherData'),
             ('terminal','build',6231),('terminal','build',True),('terminal','connected',False),
             ('account','server','Rico-REAL'),('account','trade_mode',2),('account','binding','other'),
             ('symbol','name','PETR4F'),('symbol','select',False),('symbol','custom',True)]:
            altered=deepcopy(obs);altered[part][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(PermissionError):
                verify_identity(altered,p,'synthetic-demo-account',NOW)
        for age in (-1,61):
            altered=deepcopy(obs);altered['observed_at']=(NOW-timedelta(seconds=age)).isoformat()
            with self.assertRaises(PermissionError):verify_identity(altered,p,'synthetic-demo-account',NOW)

    def test_structured_errors_redact_private_description(self):
        out=error_record((-6,'password=private account=123'))
        self.assertEqual(out['category'],'authentication_failed')
        self.assertNotIn('private',json.dumps(out));self.assertNotIn('123',json.dumps(out))
        self.assertEqual(error_record((-10005,'timeout'))['category'],'ipc_timeout')
        with self.assertRaises(ValueError):error_record(('1','bad'))


class LaboratoryTests(unittest.TestCase):
    def setUp(self):
        LAB_ROOT.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=LAB_ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'session'
        self.consent=consent()
        self.lab=OfflinePythonHistoryAdapter(self.root,proposal(),self.consent,now=NOW)
        self.pages=replies();self.source=RecordedPythonSource(self.pages)

    def run_page(self, **kwargs):
        return self.lab.acquire_next(self.source,now=lambda:NOW,free_bytes=lambda:10**12,**kwargs)

    def reopen(self):
        return OfflinePythonHistoryAdapter(self.root,proposal(),self.consent,now=NOW)

    def test_four_pages_finite_pilot_preserves_numpy_and_blocks_expansion(self):
        original_import=builtins.__import__
        def guarded(name,*a,**kw):
            if name.lower().startswith('metatrader5'):raise AssertionError('terminal import forbidden')
            return original_import(name,*a,**kw)
        with patch('builtins.__import__',side_effect=guarded):
            for _ in range(4):self.run_page()
        status=self.reopen().status()
        self.assertEqual(status['state'],'OFFLINE_PILOT_REVIEW_REQUIRED')
        self.assertEqual(status['operations_reserved'],4*OPERATION_COST)
        self.assertEqual(status['records'],12)
        self.assertFalse(status['coverage_certified'])
        with self.assertRaises(PermissionError):self.run_page()
        self.assertEqual(len(self.source.calls),4)
        arr=np.load(self.root/'call-000000/array.npy',allow_pickle=False)
        np.testing.assert_array_equal(arr,self.pages[logical_key(proposal()['pages'][0])]['bars'])
        self.assertEqual(arr.dtype.names,tuple(n for n,_ in DTYPE))

    def test_resume_uses_next_page_and_never_repeats(self):
        self.run_page();self.lab=self.reopen();self.run_page()
        self.assertEqual(len(set(self.source.calls)),2)

    def test_arbitrary_callback_module_and_subclass_are_rejected(self):
        class Derived(RecordedPythonSource):pass
        for source in (lambda:None,object(),Derived(self.pages)):
            with self.assertRaises(PermissionError):self.lab.acquire_next(source,now=lambda:NOW)
        self.assertEqual(self.lab.status()['pages'],0)

    def test_expired_window_has_no_intent_or_dispatch(self):
        with self.assertRaises(PermissionError):
            self.lab.acquire_next(self.source,now=lambda:NOW+timedelta(hours=1))
        self.assertEqual(self.source.calls,[]);self.assertEqual(self.lab.status()['pages'],0)

    def test_cooperative_stop_before_intent_does_not_consume_a_fixture(self):
        with self.assertRaisesRegex(PermissionError,'interruption'):self.run_page(stop=lambda:True)
        self.assertFalse(self.source.calls)
        self.assertEqual(self.lab.status()['pages'],0)

    def test_stop_after_intent_blocks_resume_without_repeating(self):
        signals=iter([False,True])
        with self.assertRaisesRegex(PermissionError,'interruption'):self.run_page(stop=lambda:next(signals))
        self.assertFalse(self.source.calls)
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')
        self.assertTrue((self.root/'call-000000/receipt.json').exists())
        with self.assertRaises(PermissionError):self.run_page()

    def test_stop_after_response_preserves_array_and_structured_error(self):
        signals=iter([False,False,True])
        with self.assertRaisesRegex(PermissionError,'interruption'):self.run_page(stop=lambda:next(signals))
        self.assertTrue((self.root/'call-000000/array.npy').exists())
        result=json.loads((self.root/'call-000000/result.json').read_text())
        self.assertEqual(result['error']['code'],1)
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')
        with self.assertRaises(PermissionError):self.run_page()
        self.assertEqual(len(self.source.calls),1)

    def test_reparse_point_is_refused_before_resolving_or_creating_the_ledger(self):
        from types import SimpleNamespace
        candidate=Path(self.temp.name)/'reparse-session'
        original=Path.lstat
        def lstat(path,*args,**kwargs):
            if path==candidate.absolute():return SimpleNamespace(st_file_attributes=0x400,st_mode=0o040755)
            return original(path,*args,**kwargs)
        with patch.object(Path,'lstat',lstat),self.assertRaisesRegex(PermissionError,'reparse'):
            OfflinePythonHistoryAdapter(candidate,proposal(),consent(),now=NOW)
        self.assertFalse(candidate.exists())

    def test_changed_consent_or_prior_index_blocks(self):
        for attr in ('consent','prior'):
            with self.subTest(attr=attr):
                if attr=='consent':self.lab.consent['expected_grids']={}
                else:self.lab.prior.append({'request':{}})
                with self.assertRaises(PermissionError):self.run_page()
                self.lab=self.reopen()

    def test_no_space_blocks_before_intent(self):
        with self.assertRaises(OSError):self.lab.acquire_next(self.source,now=lambda:NOW,free_bytes=lambda:0)
        self.assertEqual(self.lab.status()['pages'],0);self.assertEqual(self.source.calls,[])

    def test_prior_backend_attempt_with_unknown_timezone_blocks_conservatively(self):
        other=Path(self.temp.name)/'other'
        prior=[dict(request=dict(symbol='PETR4',period='M1',datetime_from='2026-11-03T00:00:00',datetime_to='2026-11-04T00:00:00'))]
        lab=OfflinePythonHistoryAdapter(other,proposal(),consent(),now=NOW,prior_intents=prior)
        with self.assertRaisesRegex(PermissionError,'prior backend'):lab.acquire_next(self.source,now=lambda:NOW)
        self.assertEqual(lab.status()['pages'],0)

    def test_provider_error_empty_none_and_unknown_code_are_durable(self):
        for index,(bars,error) in enumerate([(None,(-4,'no history')),(None,(1,'ok')),
                 (np.array([],dtype=DTYPE),(1,'ok')),(None,(-12345,'unknown private text'))]):
            root=Path(self.temp.name)/str(index)
            lab=OfflinePythonHistoryAdapter(root,proposal(),consent(),now=NOW)
            data=replies();key=logical_key(proposal()['pages'][0]);data[key].update(bars=bars,last_error=error)
            source=RecordedPythonSource(data)
            with self.assertRaises(ValueError):lab.acquire_next(source,now=lambda:NOW,free_bytes=lambda:10**12)
            self.assertEqual(lab.status()['state'],'BLOCKED')
            with self.assertRaises(PermissionError):lab.acquire_next(source,now=lambda:NOW)
            self.assertEqual(len(source.calls),1)
            saved=json.loads((root/'call-000000/result.json').read_text())
            self.assertEqual(saved['error']['code'],error[0])

    def test_incomplete_and_unproven_grids_stay_blocked(self):
        for index,expected in enumerate((None,[])):
            c=consent();key=logical_key(proposal()['pages'][0])
            if expected is None:del c['expected_grids'][key]
            else:c['expected_grids'][key]=expected
            lab=OfflinePythonHistoryAdapter(Path(self.temp.name)/str(index),proposal(),c,now=NOW)
            with self.assertRaisesRegex(ValueError,'ambiguous'):lab.acquire_next(self.source,now=lambda:NOW,free_bytes=lambda:10**12)
            self.assertEqual(lab.status()['state'],'BLOCKED')

    def test_gap_is_detected_without_filling_or_claiming_market_calendar(self):
        p=proposal()['pages'][0];key=logical_key(p)
        bars=self.pages[key]['bars'][[0,2,3,4]]
        audit=analyze_bars(bars,p,times(p))
        self.assertEqual(audit['missing_expected'],[times(p)[1]])
        self.assertFalse(audit['fixture_complete']);self.assertFalse(audit['coverage_certified'])
        self.assertTrue(audit['audit']['intervals'])

    def test_invalid_bars_are_not_repaired(self):
        p=proposal()['pages'][0];bars=self.pages[logical_key(p)]['bars']
        invalid=[]
        reverse=bars[::-1].copy();invalid.append(reverse)
        duplicate=bars.copy();duplicate['time'][1]=duplicate['time'][0];invalid.append(duplicate)
        nan=bars.copy();nan['open'][0]=float('nan');invalid.append(nan)
        ohlc=bars.copy();ohlc['high'][0]=1;invalid.append(ohlc)
        boundary=bars.copy();boundary['time'][-1]=int(datetime.fromisoformat(p['to_utc']).timestamp());invalid.append(boundary)
        grid=bars.copy();grid['time'][0]+=1;invalid.append(grid)
        invalid.extend([bars.reshape(1,5),np.array([object()],dtype=object)])
        for i,arr in enumerate(invalid):
            with self.subTest(i=i),self.assertRaises(ValueError):analyze_bars(arr,p,times(p))

    def test_post_identity_change_blocks_after_preserving_raw(self):
        key=logical_key(proposal()['pages'][0]);self.pages[key]['after']['account']['server']='other'
        self.source=RecordedPythonSource(self.pages)
        with self.assertRaises(PermissionError):self.run_page()
        self.assertTrue((self.root/'call-000000/array.npy').exists())
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')

    def test_processing_deadline_or_window_expiry_keeps_receipt(self):
        ticks=iter([0,601,601])
        with self.assertRaises(TimeoutError):self.run_page(clock=lambda:next(ticks))
        self.assertTrue((self.root/'call-000000/receipt.json').exists())
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')

    def test_missing_receipt_blocks_resume_and_prevents_second_worker(self):
        import strategy_factory.python_history_adapter as module
        original=module._save
        def fail_receipt(path,data):
            if path.name=='receipt.json':raise OSError('synthetic disk failure')
            return original(path,data)
        with patch.object(module,'_save',side_effect=fail_receipt):
            with self.assertRaises(OSError):self.run_page()
        reopened=self.reopen()
        self.assertIn('unknown_outcome',reopened.status()['blockers'])
        with self.assertRaises(PermissionError):reopened.acquire_next(self.source,now=lambda:NOW)
        self.assertEqual(len(self.source.calls),1)

    def test_artifact_or_receipt_tampering_blocks_resume(self):
        self.run_page();p=self.root/'call-000000/array.npy'
        p.write_bytes(p.read_bytes()+b'tamper')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.reopen()

    def test_unknown_artifact_and_session_change_block_resume(self):
        (self.root/'unknown.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'unexpected'):self.reopen()

    def test_second_worker_reservation_is_exclusive(self):
        import strategy_factory.python_history_adapter as module
        original=module._save
        second=self.reopen()
        def intercept(path,data):
            original(path,data)
            if path.name=='intent.json':
                with self.assertRaises(PermissionError):second.acquire_next(self.source,now=lambda:NOW)
        with patch.object(module,'_save',side_effect=intercept):self.run_page()
        self.assertEqual(len(self.source.calls),1)

    def test_M1_M5_conflict_stops_second_page(self):
        self.run_page()
        p=proposal()['pages'][1];key=logical_key(p)
        self.pages[key]['bars']['real_volume'][0]=999
        self.source=RecordedPythonSource(self.pages)
        with self.assertRaisesRegex(ValueError,'M1_M5_conflict'):self.run_page()
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')

    def test_resource_caps_cannot_be_bypassed_by_instance_counters(self):
        self.lab.calls=999;self.lab.operations=999;self.lab.records=999
        self.run_page()
        self.assertEqual(self.lab.status()['pages'],1)
        self.assertEqual(self.lab.status()['operations_reserved'],OPERATION_COST)
        # Inject exhausted reloaded counters solely to exercise each dispatch gate.
        original=self.lab.reload
        for field,value,error in [('operations',80,PermissionError),('records',8000,PermissionError),
                                  ('elapsed',600,PermissionError),('storage',33554432,OSError)]:
            def reload(): original();setattr(self.lab,field,value)
            with self.subTest(field=field),patch.object(self.lab,'reload',side_effect=reload):
                with self.assertRaises(error):self.run_page()
        self.assertEqual(len(self.source.calls),1)

    def test_oversized_arrays_preserve_hash_without_silent_truncation(self):
        p=proposal()['pages'][0];key=logical_key(p)
        large=np.zeros(40000,dtype=DTYPE);self.pages[key]['bars']=large
        self.source=RecordedPythonSource(self.pages)
        with self.assertRaisesRegex(ValueError,'oversized'):self.run_page()
        folder=self.root/'call-000000'
        result=json.loads((folder/'result.json').read_text())
        buffer=io.BytesIO();np.save(buffer,large,allow_pickle=False)
        self.assertEqual(result['array_sha256'],hashlib.sha256(buffer.getvalue()).hexdigest())
        self.assertFalse((folder/'array.npy').exists())
        self.assertTrue((folder/'receipt.json').exists())
        self.assertEqual(self.reopen().status()['state'],'BLOCKED')

    def test_original_or_real_consent_is_rejected_before_storage(self):
        from strategy_factory.history_transport import approval_scope
        root=Path(self.temp.name)/'rejected'
        with self.assertRaises(PermissionError):OfflinePythonHistoryAdapter(root,proposal(),approval_scope(),now=NOW)
        self.assertFalse(root.exists())
        c=consent();c['purpose']='human_approved_real'
        with self.assertRaises(PermissionError):OfflinePythonHistoryAdapter(root,proposal(),c,now=NOW)
        self.assertFalse(root.exists())

    def test_wrong_metadata_error_is_structured_and_private_text_is_not_stored(self):
        key=logical_key(proposal()['pages'][0])
        self.pages[key]['before']['metadata_errors'][0]=(-6,'password=private-data')
        self.source=RecordedPythonSource(self.pages)
        with self.assertRaises(PermissionError):self.run_page()
        failure=json.loads((self.root/'call-000000/failure.json').read_text())
        self.assertEqual(failure['metadata_errors'][0]['code'],-6)
        self.assertNotIn('private-data',json.dumps(failure))

    def test_outside_namespace_is_refused_without_modifying_old_session(self):
        outside=LAB_ROOT.parent/'history_acquisition'/'must-not-exist'
        with self.assertRaises(PermissionError):OfflinePythonHistoryAdapter(outside,proposal(),consent(),now=NOW)
        self.assertFalse(outside.exists())


if __name__=='__main__':unittest.main()
