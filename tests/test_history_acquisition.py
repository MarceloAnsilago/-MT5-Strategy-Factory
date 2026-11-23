"""Finite synthetic acquisition fixtures; real history endpoints are never used."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.history_audit import audit_collection, audit_snapshot
from strategy_factory.history_acquisition import (
    acquisition_proposal, validate_proposal, page_requests, plan_status, CHECKS,
    BlockedHistoryAdapter, SyntheticHistorySource, OfflineHistoryAcquisition,
    validate_fixture_consent, review_acquired_dataset, review_session_grid)

NOW = datetime(2026, 11, 23, 12, tzinfo=timezone.utc)
CONNECTION = dict(server='Rico-DEMO', build=6230, installation_sha256='a'*64)


def proposal():
    return acquisition_proposal(CONNECTION)


def consent(plan):
    digest = fingerprint(plan)
    return dict(schema_version='3.3F-consent-fixture-1', purpose='synthetic_offline_only',
        plan_sha256=digest, issued_at=NOW.isoformat(), expires_at=(NOW+timedelta(hours=1)).isoformat(),
        actor='synthetic-human-reviewer', statement='SYNTHETIC ACQUISITION ONLY '+digest,
        live_execution_enabled=False)


def bar(stamp, **changes):
    return dict(dict(time=stamp, open=10, high=12, low=9, close=11,
        tick_volume=10, volume=100, spread=1), **changes)


def payload(request, rows=None, **changes):
    return dict(dict(ok=True, symbol='PETR4', period=request['period'], complete=True,
        connection=deepcopy(CONNECTION), history=rows if rows is not None else [bar(request['datetime_from'][:10]+'T10:00:00')]), **changes)


def raw(document):
    return json.dumps(document).encode('utf-8')


class AcquisitionContracts(unittest.TestCase):
    def test_proposal_has_no_availability_claim_or_execution_permission(self):
        plan = proposal()
        self.assertFalse(plan['availability_verified'])
        self.assertFalse(plan['tick_option_included'])
        self.assertFalse(plan_status(plan)['live_execution_enabled'])
        self.assertEqual(plan_status(plan)['state'], 'ACQUISITION_PLAN_READY')
        self.assertEqual(plan_status(plan, awaiting_approval=True)['state'], 'AWAITING_HUMAN_APPROVAL')

    def test_daily_pagination_is_half_open_contiguous_and_within_budget(self):
        plan = proposal(); requests = page_requests(plan)
        days = (datetime.fromisoformat(plan['datetime_to'])-datetime.fromisoformat(plan['datetime_from'])).days
        self.assertEqual(len(requests), 2*days)
        self.assertEqual(requests[0]['datetime_from'], plan['datetime_from'])
        self.assertEqual(requests[-1]['datetime_to'], plan['datetime_to'])
        for a, b in zip(requests[::2], requests[2::2]):
            self.assertEqual(a['datetime_to'], b['datetime_from'])
        self.assertLessEqual(len(requests), plan['max_calls'])

    def test_unsafe_flags_unknown_fields_and_limits_rejected(self):
        for key, value in [('live_execution_enabled',True),('local_only_guaranteed',True),
                           ('max_concurrency',2),('limit_per_call',100000),('max_calls',1),
                           ('max_records',1),('max_storage_bytes',False),('authorization_max_hours',25),
                           ('extra_permission',True)]:
            plan = proposal(); plan[key] = value
            with self.subTest(key=key), self.assertRaises((ValueError, PermissionError)):
                validate_proposal(plan)

    def test_periods_must_fit_scope_and_final_excludes_known_results(self):
        plan = proposal(); plan['periods']['final_test']['to_date'] = '2026-11-07'
        with self.assertRaises(ValueError): validate_proposal(plan)
        plan = proposal(); plan['periods']['out_of_sample']['warmup_from'] = '2025-06-01'
        with self.assertRaises(ValueError): validate_proposal(plan)

    def test_real_adapter_remains_blocked_even_with_supplied_approval(self):
        with patch.object(socket, 'socket', side_effect=AssertionError('network forbidden')):
            with self.assertRaisesRegex(PermissionError,'ACQUISITION_BLOCKED'):
                BlockedHistoryAdapter().acquire(proposal(), authorization={'approved':True})

    def test_missing_and_agent_originated_consent_rejected(self):
        plan = proposal()
        for record in (None, dict(consent(plan), actor='agent'), dict(consent(plan), purpose='real_acquisition')):
            with self.assertRaises((ValueError,PermissionError)):
                validate_fixture_consent(record, plan, now=NOW)

    def test_expired_premature_overlong_and_scope_changed_consent_rejected(self):
        plan = proposal(); fixture = consent(plan)
        for moment in (NOW-timedelta(seconds=1), NOW+timedelta(hours=1)):
            with self.assertRaises(PermissionError): validate_fixture_consent(fixture,plan,now=moment)
        with self.assertRaises(PermissionError):
            validate_fixture_consent(dict(fixture,expires_at=(NOW+timedelta(hours=25)).isoformat()),plan,now=NOW)
        plan['max_calls'] += 1
        with self.assertRaises(PermissionError): validate_fixture_consent(fixture,plan,now=NOW)


class AcquisitionPersistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)/'lab'
        self.plan = proposal(); self.fixture = consent(self.plan)
        self.requests = page_requests(self.plan)

    def lab(self, **kwargs):
        return OfflineHistoryAcquisition(self.root,self.plan,self.fixture,now=NOW,**kwargs)

    def source(self, documents):
        return SyntheticHistorySource({fingerprint(r):raw(d) if isinstance(d,dict) else d for r,d in zip(self.requests,documents)})

    def run_pages(self, lab, source, count=1, **kwargs):
        return lab.run(source,now=lambda:NOW,stop=lambda:len(lab.receipts)>=count,
            free_bytes=lambda:10**12, **kwargs)

    def test_consent_required_before_any_directory_or_call(self):
        with self.assertRaises(PermissionError): OfflineHistoryAcquisition(self.root,self.plan,None,now=NOW)
        self.assertFalse(self.root.exists())

    def test_pages_provenance_hashes_unknowns_and_safe_resume(self):
        source = self.source([payload(r) for r in self.requests[:3]])
        with patch.object(socket,'socket',side_effect=AssertionError('offline only')):
            lab=self.lab(); result=self.run_pages(lab,source)
            self.assertEqual(result['pages_committed'],1)
            receipt=lab.receipts[0]
            self.assertEqual(receipt['raw_sha256'],hashlib.sha256((self.root/'page-000000/raw.json').read_bytes()).hexdigest())
            self.assertEqual(receipt['request'],self.requests[0])
            self.assertEqual(receipt['connection'],CONNECTION)
            self.assertIsNone(receipt['broker_timezone']);self.assertIsNone(receipt['price_adjustments'])
            self.assertIsNotNone(datetime.fromisoformat(receipt['captured_at']).utcoffset())
            reopened=self.lab(reopen=True); self.run_pages(reopened,source,count=3)
            self.assertEqual(len(source.calls),3)
            self.assertEqual(reopened.receipts[1]['previous_receipt_sha256'],receipt['receipt_sha256'])

    def test_incomplete_or_failed_response_blocks_cursor_and_resume(self):
        lab=self.lab(); source=self.source([payload(self.requests[0],complete=False)])
        with self.assertRaises(ValueError): self.run_pages(lab,source)
        self.assertEqual(len(lab.receipts),0)
        with self.assertRaisesRegex(ValueError,'orphaned'): self.lab(reopen=True)

    def test_empty_page_is_persisted_without_certifying_market_absence(self):
        lab=self.lab();source=self.source([payload(self.requests[0],rows=[])])
        result=self.run_pages(lab,source)
        self.assertEqual(result['state'],'DATASET_PARTIAL')
        self.assertEqual(result['rows'],0)
        self.assertIsNone(lab.receipts[0]['returned_from'])
        self.assertFalse(result['coverage_certified'])
        self.assertEqual(len(self.lab(reopen=True).receipts),1)

    def test_connection_failure_persists_intent_and_has_no_automatic_retry(self):
        lab=self.lab(); source=self.source([ConnectionError('synthetic disconnect')])
        with self.assertRaises(ConnectionError): self.run_pages(lab,source)
        self.assertEqual(len(source.calls),1)
        self.assertTrue((self.root/'page-000000/request.json').exists())
        with self.assertRaises(ValueError): self.lab(reopen=True)

    def test_raw_page_size_limit(self):
        lab=self.lab(); source=self.source([b' '* (self.plan['max_raw_page_bytes']+1)])
        with self.assertRaisesRegex(ValueError,'byte limit'): self.run_pages(lab,source)

    def test_limit_saturation_does_not_silently_skip_remainder(self):
        lab=self.lab(); request=self.requests[0]
        source=self.source([payload(request,rows=[bar('2024-01-01T10:00:00')]*request['limit'])])
        with self.assertRaisesRegex(ValueError,'truncation'): self.run_pages(lab,source)

    def test_stop_before_call_preserves_safe_resume_boundary(self):
        lab=self.lab(); source=self.source([])
        result=self.run_pages(lab,source,count=0)
        self.assertEqual(result['reason'],'interrupted_before_next_page');self.assertFalse(source.calls)
        self.assertFalse(self.lab(reopen=True).receipts)

    def test_stop_after_response_never_advances_commit(self):
        lab=self.lab(); source=self.source([payload(self.requests[0])]); checks=iter([False,True])
        result=lab.run(source,now=lambda:NOW,stop=lambda:next(checks),free_bytes=lambda:10**12)
        self.assertEqual(result['pages_committed'],0)
        with self.assertRaisesRegex(ValueError,'orphaned'): self.lab(reopen=True)

    def test_arbitrary_callback_or_subclass_transport_rejected(self):
        lab=self.lab()
        with self.assertRaises(PermissionError):self.run_pages(lab,lambda request:b'{}')
        class DisguisedSource(SyntheticHistorySource): pass
        with self.assertRaises(PermissionError):self.run_pages(lab,DisguisedSource({}))

    def test_identical_duplicates_observed_and_conflicts_rejected(self):
        lab=self.lab(); row=bar('2024-01-01T10:00:00')
        source=self.source([payload(self.requests[0],rows=[row,row])])
        self.run_pages(lab,source)
        self.assertEqual(lab.audits[0]['duplicate_rows'],1)
        request=self.requests[1]
        conflict=payload(request,rows=[row,dict(row,close=10)])
        with self.assertRaisesRegex(ValueError,'integrity'):self.run_pages(lab,self.source([payload(self.requests[0]),conflict]),count=2)

    def test_response_scope_date_and_build_changes_block(self):
        for changes in [dict(connection=dict(CONNECTION,build=6231)),dict(period='H1'),dict(ok=False),
                        dict(history=[bar('2024-01-02T10:00:00')])]:
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as directory:
                lab=OfflineHistoryAcquisition(Path(directory)/'lab',self.plan,self.fixture,now=NOW)
                with self.assertRaises(ValueError):self.run_pages(lab,self.source([payload(self.requests[0],**changes)]))

    def test_hash_mismatch_or_audit_tampering_blocks_resume(self):
        lab=self.lab();self.run_pages(lab,self.source([payload(self.requests[0])]))
        path=self.root/'page-000000/raw.json'; original=path.read_bytes()
        path.write_bytes(original+b' ')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.lab(reopen=True)
        path.write_bytes(original)
        audit=self.root/'page-000000/audit.json';audit.write_bytes(audit.read_bytes()+b' ')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.lab(reopen=True)

    def test_changed_plan_or_consent_cannot_resume_existing_lab(self):
        self.lab();self.plan['max_calls']+=1;self.fixture=consent(self.plan)
        with self.assertRaises(PermissionError):self.lab(reopen=True)

    def test_expiry_checked_on_resume_before_call(self):
        lab=self.lab();source=self.source([])
        with self.assertRaises(PermissionError):lab.run(source,now=lambda:NOW+timedelta(days=1),free_bytes=lambda:10**12)
        self.assertFalse(source.calls)

    def test_storage_failure_leaves_detectable_uncommitted_page(self):
        lab=self.lab();source=self.source([payload(self.requests[0])]);original=Path.open
        def failing(path,*args,**kwargs):
            if path.name=='audit.json' and args and args[0]=='xb':raise OSError('synthetic disk failure')
            return original(path,*args,**kwargs)
        with patch.object(Path,'open',failing):
            with self.assertRaises(OSError):self.run_pages(lab,source)
        self.assertEqual(len(lab.receipts),0)
        with self.assertRaisesRegex(ValueError,'orphaned'):self.lab(reopen=True)

    def test_storage_budget_and_disk_free_limit(self):
        lab=self.lab();source=self.source([payload(self.requests[0])])
        with self.assertRaises(OSError):lab.run(source,now=lambda:NOW,free_bytes=lambda:0)
        self.assertFalse(source.calls)
        self.plan['max_storage_bytes']=self.plan['max_raw_page_bytes']
        # Test actual aggregate bytes, not only the raw page cap.
        self.fixture=consent(self.plan)
        with tempfile.TemporaryDirectory() as directory:
            lab=OfflineHistoryAcquisition(Path(directory)/'lab',self.plan,self.fixture,now=NOW)
            doc=payload(self.requests[0],padding='x'*(self.plan['max_raw_page_bytes']-1000))
            with self.assertRaisesRegex(ValueError,'storage budget'):self.run_pages(lab,self.source([doc]))

    def test_cooperative_timeout_never_starts_next_call(self):
        lab=self.lab();source=self.source([]);clock=iter([0,self.plan['max_elapsed_seconds']])
        result=self.run_pages(lab,source,clock=lambda:next(clock))
        self.assertEqual(result['reason'],'cooperative_timeout');self.assertFalse(source.calls)


class DataReview(unittest.TestCase):
    def collection(self):
        request=page_requests(proposal())[0]
        minute=[bar('2024-01-01T10:0'+str(i)+':00') for i in range(5)]
        return audit_collection([
            audit_snapshot(payload(request,minute),source_id='m1'),
            audit_snapshot(payload(dict(request,period='M5'),[bar('2024-01-01T10:00:00',tick_volume=50,volume=500)]),source_id='m5')])

    def evidence(self,collection):
        digest=fingerprint(collection);checks={};sources={}
        for name in CHECKS:
            source=dict(collection_sha256=digest,check=name,status='pass',limitations=[],
                details={'synthetic_assertion_only':True},kind='synthetic')
            checksum=fingerprint(source);sources[checksum]=source
            checks[name]=dict(status='pass',source_sha256=checksum,limitations=[])
        return dict(collection_sha256=digest,checks=checks,sources=sources)

    def change_check(self,evidence,name,status):
        check=evidence['checks'][name];source=deepcopy(evidence['sources'][check['source_sha256']])
        source['status']=status;checksum=fingerprint(source)
        evidence['sources'][checksum]=source;check.update(status=status,source_sha256=checksum)

    def test_all_applicable_checks_complete_is_audited_but_never_certified_or_executable(self):
        collection=self.collection();review=review_acquired_dataset(collection,self.evidence(collection))
        self.assertEqual(review['state'],'DATASET_AUDITED')
        for key in ('coverage_certified','economic_quality_verified','statistical_sufficiency_verified','acquisition_enabled','live_execution_enabled'):
            self.assertIs(review[key],False)

    def test_unknown_origin_calendar_adjustments_events_or_warmup_remain_partial(self):
        collection=self.collection()
        for name in CHECKS:
            evidence=self.evidence(collection);self.change_check(evidence,name,'unknown')
            with self.subTest(name=name):
                review=review_acquired_dataset(collection,evidence)
                self.assertEqual(review['state'],'DATASET_PARTIAL');self.assertIn(name,review['blockers'])

    def test_missing_provenance_and_failed_data_checks_block_review(self):
        collection=self.collection();evidence=self.evidence(collection)
        evidence['checks']['origin']['source_sha256']=None
        self.change_check(evidence,'session_continuity','fail')
        review=review_acquired_dataset(collection,evidence)
        self.assertEqual(review['state'],'DATASET_PARTIAL')

    def test_dataset_version_change_and_invented_check_rejected(self):
        collection=self.collection();evidence=self.evidence(collection);evidence['collection_sha256']='c'*64
        with self.assertRaises(ValueError):review_acquired_dataset(collection,evidence)
        evidence=self.evidence(collection);evidence['checks']['strategy_profit']={}
        with self.assertRaises(ValueError):review_acquired_dataset(collection,evidence)

    def test_review_source_hash_or_scope_cannot_be_invented(self):
        collection=self.collection();evidence=self.evidence(collection)
        evidence['checks']['origin']['source_sha256']='e'*64
        with self.assertRaises(ValueError):review_acquired_dataset(collection,evidence)


class SessionCoverage(unittest.TestCase):
    def fixture(self):
        audit=audit_snapshot(dict(ok=True,symbol='PETR4',period='M1',history=[
            bar('2024-01-02T10:00:00+00:00'),bar('2024-01-02T10:02:00+00:00')]),
            source_id='synthetic',timezone_label='UTC')
        calendar=dict(audit_sha256=fingerprint(audit),source_sha256='d'*64,timezone='UTC',
            expected_bar_times=['2024-01-02T10:0'+str(i)+':00+00:00' for i in range(3)],no_trade={})
        return audit,calendar

    def test_expected_missing_slot_is_unresolved_without_no_trade_evidence(self):
        audit,calendar=self.fixture();review=review_session_grid(audit,calendar)
        self.assertEqual(review['state'],'DATASET_PARTIAL')
        self.assertEqual(review['unresolved_slots'],['2024-01-02T10:01:00+00:00'])
        self.assertEqual(review['bars_filled'],0)

    def test_sourced_absence_of_trading_is_not_fabricated_missing_candle(self):
        audit,calendar=self.fixture();calendar['no_trade']['2024-01-02T10:01:00+00:00']='e'*64
        review=review_session_grid(audit,calendar)
        self.assertEqual(review['state'],'DATASET_AUDITED');self.assertFalse(review['coverage_certified'])
        self.assertEqual(len(audit['records']),2);self.assertEqual(review['bars_filled'],0)

    def test_unknown_timezone_or_calendar_origin_remains_partial(self):
        audit,calendar=self.fixture();calendar['timezone']='unknown';calendar['source_sha256']=None
        review=review_session_grid(audit,calendar)
        self.assertIn('calendar_broker_timezone_unverified',review['blockers'])
        self.assertIn('calendar_source_unknown',review['blockers'])

    def test_calendar_version_grid_and_unscoped_no_trade_rejected(self):
        audit,calendar=self.fixture();calendar['audit_sha256']='f'*64
        with self.assertRaises(ValueError):review_session_grid(audit,calendar)
        audit,calendar=self.fixture();calendar['no_trade']['2024-01-03T10:00:00+00:00']='e'*64
        with self.assertRaises(ValueError):review_session_grid(audit,calendar)


if __name__=='__main__':unittest.main()
