"""Synthetic offline history audit and dataset policy regression tests."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from strategy_factory.analysis import read_artifact
from strategy_factory.batch_manifest import fingerprint
from strategy_factory.history_audit import audit_snapshot,audit_local_file,audit_collection,certify_history
from strategy_factory.dataset_policy import build_dataset_manifest,revise_dataset_manifest,validate_dataset_manifest,revalidate_dataset,assess_period_data,empty_broker_conditions,validate_conditions,attach_history_review
from strategy_factory.period_planning import validate_candidate_periods

ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,11,23,12,tzinfo=timezone.utc)


def bar(stamp='2026-10-26T10:00:00',**changes):
    return dict(dict(time=stamp,open=10,high=12,low=9,close=11,tick_volume=10,volume=100,spread=1),**changes)


def snapshot(rows=None,period='M5'):
    return dict(symbol='PETR4',period=period,ok=True,data_available_from='2021-01-01T00:00:00',history=rows if rows is not None else [bar()])


class AuditTests(unittest.TestCase):
    def audit(self,s=None,**kwargs):return audit_snapshot(s or snapshot(),source_id='synthetic',**kwargs)

    def test_observed_consistency_never_certifies_market_coverage(self):
        with patch.object(socket,'socket',side_effect=AssertionError('offline only')):a=self.audit()
        self.assertEqual(a['classification'],'observed_partial');self.assertFalse(a['coverage_certified'])
        self.assertIn('broker_timezone_unknown',a['warnings'])

    def test_intraday_gap_is_unclassified_not_automatically_missing_market_data(self):
        a=self.audit(snapshot([bar(),bar('2026-10-26T10:10:00')]))
        gap=a['intervals'][0];self.assertEqual(gap['omitted_grid_slots'],1)
        self.assertEqual(gap['classification'],'unclassified_intraday_interval')
        self.assertIsNone(gap['certified_missing_bars']);self.assertFalse(a['errors'])
        self.assertEqual(len(a['records']),2)  # No invented 10:05 candle.

    def test_overnight_weekend_interval_does_not_become_an_error(self):
        a=self.audit(snapshot([bar('2026-10-23T16:55:00'),bar('2026-10-26T10:00:00')]))
        self.assertEqual(a['intervals'][0]['classification'],'unclassified_between_dates')
        self.assertFalse(a['errors'])

    def test_equal_duplicates_are_counted_and_collection_deduplicated(self):
        a=self.audit(snapshot([bar(),bar()]));c=audit_collection([a])
        self.assertEqual(a['duplicate_rows'],1);self.assertEqual(c['series'][0]['unique_rows'],1)

    def test_conflicting_duplicate_is_invalid(self):
        a=self.audit(snapshot([bar(),bar(close=10)]));self.assertEqual(a['classification'],'invalid')
        self.assertTrue(any(e['code']=='conflicting_duplicate' for e in a['errors']))

    def test_conflicting_sources_are_not_silently_preferred(self):
        a=self.audit();b=audit_snapshot(snapshot([bar(close=10)]),source_id='another')
        c=audit_collection([a,b]);self.assertEqual(c['classification'],'invalid')
        self.assertEqual(len(c['conflicting_duplicates']),1)

    def test_invalid_ohlc_enclosures_and_negative_prices(self):
        for change in ({'high':10},{'low':11},{'open':0},{'close':-1}):
            with self.subTest(change=change):self.assertEqual(self.audit(snapshot([bar(**change)]))['classification'],'invalid')

    def test_volume_types_negative_spread_and_missing_fields(self):
        for change in ({'volume':-1},{'tick_volume':1.5},{'tick_volume':True},{'spread':-1}):
            self.assertEqual(self.audit(snapshot([bar(**change)]))['classification'],'invalid')
        row=bar();del row['volume'];self.assertEqual(self.audit(snapshot([row]))['classification'],'invalid')

    def test_nonfinite_numbers_fail_closed(self):
        with self.assertRaises(ValueError):self.audit(snapshot([bar(close=float('nan'))]))

    def test_chronological_reversal_remains_visible(self):
        a=self.audit(snapshot([bar('2026-10-26T10:05:00'),bar()]))
        self.assertTrue(any(e['code']=='chronological_reversal' for e in a['errors']))

    def test_bad_timestamps_and_grid_alignment_are_invalid(self):
        for stamp in ('2026-10-26','2026-13-26T10:00:00','2026-10-26T10:01:00','2026-10-26T10:00:00.001'):
            self.assertEqual(self.audit(snapshot([bar(stamp)]))['classification'],'invalid')

    def test_naive_timestamps_cannot_be_relabelled_utc(self):
        self.assertEqual(self.audit(timezone_label='UTC')['classification'],'invalid')

    def test_mixed_aware_naive_timestamps_are_invalid(self):
        a=self.audit(snapshot([bar(),bar('2026-10-26T10:05:00+00:00')]))
        self.assertEqual(a['classification'],'invalid')

    def test_explicit_offsets_normalize_same_instant_without_invented_broker_zone(self):
        a=self.audit(snapshot([bar('2026-10-26T10:00:00+00:00'),bar('2026-10-26T11:00:00+01:00')]),timezone_label='explicit_offsets')
        self.assertFalse(a['errors']);self.assertEqual(a['duplicate_rows'],1)
        self.assertEqual(a['date_basis'],'UTC');self.assertFalse(a['coverage_certified'])

    def test_incomplete_and_failed_snapshots_are_invalid(self):
        for changes in ({'truncated':True},{'complete':False},{'ok':False},{'history':None}):
            self.assertEqual(self.audit(dict(snapshot(),**changes))['classification'],'invalid')

    def test_identical_tick_timestamp_does_not_imply_duplicate_tick(self):
        s=snapshot([dict(time='2026-10-26T10:00:00',bid=10,ask=11),dict(time='2026-10-26T10:00:00',bid=10.5,ask=11)],period='tick')
        a=self.audit(s,kind='broker_ticks');self.assertEqual(a['duplicate_rows'],0)
        self.assertEqual(audit_collection([a])['series'][0]['unique_rows'],2)

    def test_generated_and_broker_ticks_are_separate_series(self):
        s=snapshot([dict(time='2026-10-26T10:00:00',bid=10,ask=11)],period='tick')
        a=audit_snapshot(s,source_id='broker',kind='broker_ticks');b=audit_snapshot(s,source_id='generated',kind='generated_ticks')
        self.assertEqual(len(audit_collection([a,b])['series']),2)

    def test_crossed_quotes_and_inconsistent_millisecond_timestamp_invalid(self):
        a=self.audit(snapshot([dict(time='2026-10-26T10:00:00Z',bid=11,ask=10)],period='tick'),kind='broker_ticks')
        self.assertEqual(a['classification'],'invalid')
        a=self.audit(snapshot([dict(time='2026-10-26T10:00:00Z',bid=10,ask=11,time_msc=0)],period='tick'),kind='broker_ticks')
        self.assertEqual(a['classification'],'invalid')

    def test_single_complete_m1_bucket_can_only_be_conditionally_matched(self):
        minute=[bar('2026-10-26T10:0'+str(i)+':00') for i in range(5)]
        a=self.audit(snapshot(minute,period='M1'));b=audit_snapshot(snapshot([bar(tick_volume=50,volume=500)]),source_id='m5')
        c=audit_collection([a,b]);self.assertEqual(c['M1_M5_comparison'][0]['classification'],'conditional_aggregate_match')
        self.assertFalse(c['coverage_certified'])

    def test_m1_m5_discrepancy_is_invalid_and_partial_buckets_not_filled(self):
        minute=[bar('2026-10-26T10:0'+str(i)+':00') for i in range(5)]
        a=self.audit(snapshot(minute,period='M1'));b=audit_snapshot(snapshot(),source_id='m5')
        self.assertEqual(audit_collection([a,b])['M1_M5_comparison'][0]['classification'],'mismatch')
        a=self.audit(snapshot(minute[:2],period='M1'))
        self.assertEqual(audit_collection([a,b])['M1_M5_comparison'][0]['classification'],'incomplete_M1_bucket')

    def test_certification_promotion_is_rejected(self):
        with self.assertRaises(PermissionError):certify_history(self.audit(),approved=True)
        a=self.audit();a['coverage_certified']=True
        with self.assertRaises(PermissionError):audit_collection([a])


class DatasetPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'synthetic.json'
        rows=[bar('2026-10-26T10:00:00'),bar('2026-10-27T10:00:00')]
        self.path.write_text(json.dumps(snapshot(rows)),encoding='utf-8')
        self.audit=audit_local_file(self.path,source_id='fixture',capture_time=NOW.isoformat())
        self.collection=audit_collection([self.audit])
        self.manifest=build_dataset_manifest(self.collection,exposures=[],reviewed_at=NOW.isoformat(),valid_until=(NOW+timedelta(days=1)).isoformat())
        self.periods=dict(development=dict(warmup_from='2026-10-26',from_date='2026-10-27',to_date='2026-10-28',history_status='unverified',selection_basis='prospective_not_result_selected'),out_of_sample=None,final_test=None)

    def revalidate(self,manifest=None,**changes):
        options=dict(expected_version=self.manifest['dataset_version'],expected_exposure_sha256=self.manifest['exposure_registry_sha256'],expected_conditions_version=None,now=NOW)
        options.update(changes)
        return revalidate_dataset(manifest or self.manifest,{'fixture':self.path},**options)

    def test_dataset_version_is_content_bound_and_still_unverified(self):
        self.assertEqual(validate_dataset_manifest(self.manifest),self.manifest)
        self.assertEqual(self.revalidate()['classification'],'CONSISTENT_UNVERIFIED')
        self.assertFalse(self.revalidate()['coverage_certified'])

    def test_raw_source_change_invalidates_evidence_even_if_json_values_same(self):
        self.path.write_text(self.path.read_text()+'\n')
        self.assertIn('source_changed_or_missing',self.revalidate()['blockers'])
        with self.assertRaises(ValueError):audit_local_file(self.path,source_id='fixture',expected_file_sha256=self.audit['file_sha256'])

    def test_missing_source_invalidates_evidence(self):
        self.path.unlink();self.assertEqual(self.revalidate()['changed_sources'],['fixture'])

    def test_expired_or_unapproved_freshness_is_not_silently_reused(self):
        self.assertIn('review_expired',self.revalidate(now=NOW+timedelta(days=2))['blockers'])
        m=build_dataset_manifest(self.collection,exposures=[],reviewed_at=NOW.isoformat())
        self.assertIn('freshness_policy_not_approved',self.revalidate(m,expected_version=m['dataset_version'])['blockers'])

    def test_exposure_registry_and_broker_conditions_versions_invalidate_binding(self):
        self.assertIn('exposure_registry_changed',self.revalidate(expected_exposure_sha256='a'*64)['blockers'])
        self.assertIn('broker_conditions_version_changed',self.revalidate(expected_conditions_version='future-v2')['blockers'])

    def test_dataset_revisions_cannot_forget_prior_result_exposure(self):
        exposure=dict(exposure_id='known',kind='strategy_results',from_date='2026-11-03',to_date='2026-11-07',strategy_ids=['synthetic-ea'],source_sha256='a'*64,known_at=NOW.isoformat())
        first=revise_dataset_manifest(self.manifest,self.collection,exposures=[exposure],reviewed_at=NOW.isoformat())
        self.assertEqual(first['previous_dataset_version'],self.manifest['dataset_version'])
        self.assertNotEqual(first['dataset_version'],self.manifest['dataset_version'])
        with self.assertRaises(PermissionError):revise_dataset_manifest(first,self.collection,exposures=[],reviewed_at=NOW.isoformat())

    def test_manifest_hash_and_certification_flag_tampering_rejected(self):
        m=deepcopy(self.manifest);m['classification']='invalid'
        with self.assertRaises(ValueError):validate_dataset_manifest(m)
        m=deepcopy(self.manifest);m['coverage_certified']=True
        m['dataset_version']=fingerprint({k:v for k,v in m.items() if k!='dataset_version'})
        with self.assertRaises(PermissionError):validate_dataset_manifest(m)

    def test_warmup_and_missing_m1_are_explicit_blockers(self):
        r=assess_period_data(self.collection,self.manifest,self.periods,model='every tick')
        self.assertIn('insufficient_observed_M5_warmup',r['stages']['development']['blockers'])
        self.assertIn('M1_missing_for_generated_ticks',r['stages']['development']['blockers'])
        self.assertFalse(r['ready_for_execution'])

    def test_generated_ticks_cannot_substitute_for_broker_ticks(self):
        r=assess_period_data(self.collection,self.manifest,self.periods,model='real ticks')
        self.assertIn('broker_ticks_missing',r['stages']['development']['blockers'])
        self.assertIn('M1_missing_for_real_tick_consistency_and_fallback_detection',r['stages']['development']['blockers'])

    def test_overlap_and_known_final_result_window_are_rejected(self):
        p=deepcopy(self.periods);p['out_of_sample']=deepcopy(p['development'])
        with self.assertRaises(ValueError):assess_period_data(self.collection,self.manifest,p,model='every tick')
        p=dict(development=None,out_of_sample=None,final_test=dict(self.periods['development'],from_date='2026-11-03',to_date='2026-11-07',warmup_from='2026-11-02'))
        with self.assertRaises(ValueError):validate_candidate_periods(p)

    def test_unknown_financial_conditions_remain_none_not_zero(self):
        c=empty_broker_conditions();self.assertIsNone(c['commission']);self.assertIsNone(c['required_margin'])
        c['commission']=0
        with self.assertRaises(ValueError):validate_conditions(c)

    def test_retrospective_summary_attachment_preserves_metrics_and_scope(self):
        paths=list((ROOT/'runs').glob('phase32d*/run_summary_1_1_audited.json'))
        if not paths:self.skipTest('private audited summary intentionally absent in public clone')
        s=read_artifact(paths[0]);before=deepcopy(s)
        review=dict(schema_version='3.3E-run-review-1',run_id=s['run_id'],parameters_sha256=fingerprint(s['parameters']),dataset_version=self.manifest['dataset_version'],classification='BLOCKED_MISSING_EVIDENCE',coverage_certified=False,live_execution_enabled=False,details={})
        result=attach_history_review(s,review)
        self.assertEqual(s,before);self.assertEqual(result['metrics'],s['metrics']);self.assertEqual(result['traceability'],s['traceability'])
        with self.assertRaises(ValueError):attach_history_review(s,dict(review,run_id='wrong'))
        with self.assertRaises(PermissionError):attach_history_review(s,dict(review,coverage_certified=True))


if __name__=='__main__':unittest.main()
