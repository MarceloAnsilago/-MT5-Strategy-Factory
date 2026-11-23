"""Optional read-only regression for private local corpus; no data is published."""
import hashlib
from pathlib import Path
import unittest

from strategy_factory.history_audit import audit_local_file,audit_collection

ROOT=Path(__file__).resolve().parents[1]


class LocalHistoryRegression(unittest.TestCase):
    def test_observed_corpus_counts_m1_gap_and_preservation(self):
        names=('phase22_control/history.json','phase23_preparation/bars.json','phase23_preparation/ticks.json',
               'phase32d_audit_20261121/stop_window_current_m1.json','phase32g_trend_preflight_20261121/history_raw.json',
               'phase32g_trend_preflight_20261121/warmup_raw.json',
               'phase32h_execution_a7e690b3b483dde0_attempt1/history_preflight_raw.json')
        paths=[ROOT/'runs'/name for name in names]
        if not all(p.exists() for p in paths):self.skipTest('private snapshots intentionally absent from public repository')
        before={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        audits=[audit_local_file(p,source_id='local-'+str(i),kind='broker_ticks' if p.name=='ticks.json' else 'bars',expected_file_sha256=before[p]) for i,p in enumerate(paths)]
        collection=audit_collection(audits)
        counts={s['timeframe']:s['unique_rows'] for s in collection['series']}
        self.assertEqual(counts,{'M1':7,'M5':1252})
        self.assertEqual(collection['cross_source_duplicates'],{'M5':1629})
        self.assertFalse(collection['source_errors']);self.assertFalse(collection['conflicting_duplicates'])
        self.assertEqual(sum(c['classification']=='conditional_aggregate_match' for c in collection['M1_M5_comparison']),1)
        gaps=[g for a in audits for g in a['intervals'] if g['classification']=='unclassified_intraday_interval']
        self.assertEqual({(g['from_time'],g['to_time']) for g in gaps},{('2026-10-26T10:45:00','2026-10-26T10:55:00')})
        self.assertTrue(all(g['certified_missing_bars'] is None for g in gaps))
        self.assertEqual(before,{p:hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


if __name__=='__main__':unittest.main()
