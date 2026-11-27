import hashlib
import json
from pathlib import Path
import unittest
from uuid import uuid4

from strategy_factory.dataset_policy import validate_dataset_manifest
from strategy_factory.research import ApprovedDataset, approved_dataset, load_dataset


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/research/local_bars_synthetic.csv"
ORIGIN = "synthetic PETR4 research fixture"


class LocalDatasetTests(unittest.TestCase):
    def setUp(self):
        self.folder = ROOT / "artifacts/offline" / f"SF-O01-{uuid4().hex}"

    def synthetic_file(self, name, content, **kwargs):
        if not self.folder.exists():
            self.folder.mkdir()
            self.addCleanup(self.folder.rmdir)
        path = self.folder / name
        path.write_bytes(content)
        self.addCleanup(path.unlink)
        return ApprovedDataset(path, hashlib.sha256(content).hexdigest(), ORIGIN, **kwargs)

    def test_m5_fixture_preserves_order_hash_origin_and_gaps(self):
        raw = FIXTURE.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        with approved_dataset(ApprovedDataset(FIXTURE, digest, ORIGIN)):
            result = load_dataset(FIXTURE, expected_sha256=digest)
        audit = result["audit"]
        self.assertEqual(audit["file_sha256"], digest)
        self.assertEqual(audit["origin"], ORIGIN)
        self.assertEqual(audit["date_basis"], "unverified_source_clock")
        self.assertEqual(audit["intervals"][0]["omitted_grid_slots"], 1)
        self.assertEqual([row["time"] for row in result["snapshot"]["history"]],
                         ["2024-01-02T10:00:00", "2024-01-02T10:05:00", "2024-01-02T10:15:00"])
        manifest = validate_dataset_manifest(result["manifest"])
        self.assertEqual(manifest["certification_status"], "unverified")
        self.assertEqual(manifest["classification"], "observed_partial")
        self.assertFalse(manifest["coverage_certified"])
        self.assertFalse(manifest["live_execution_enabled"])
        self.assertEqual(manifest["exposures"][0]["source_sha256"], digest)
        self.assertEqual(FIXTURE.read_bytes(), raw)

    def test_m1_json_explicit_utc(self):
        row = dict(time="2024-01-02T10:01:00Z", open=30, high=31, low=29,
                   close=30, tick_volume=1, volume=10, spread=1)
        snapshot = dict(ok=True, symbol="PETR4", period="M1", history=[row], origin=ORIGIN)
        source = self.synthetic_file("m1.json", json.dumps(snapshot).encode(),
                                     period="M1", timezone_label="UTC")
        with approved_dataset(source):
            result = load_dataset(source.path, period="M1", timezone_label="UTC")
        self.assertEqual(result["snapshot"], snapshot)
        self.assertEqual(result["audit"]["date_basis"], "UTC")

    def test_invalid_bars(self):
        header = b"time,open,high,low,close,tick_volume,volume,spread\n"
        first = b"2024-01-02T10:00:00,30,31,29,30,1,10,1\n"
        cases = [
            first.replace(b"10:00", b"25:00"),
            first.replace(b"10:00:00", b"10:00:00+00:60"),
            first.replace(b"30,31", b"30,28"),
            first.replace(b",31,", b",NaN,"),
            first.replace(b",31,", b",inf,"),
            first + first.replace(b",31,", b",32,"),
            first + first.replace(b"10:00:00", b"10:05:00Z"),
            first.replace(b"10:00:00", b"10:00:00+01:00")
            + first.replace(b"10:00:00", b"10:05:00Z"),
            first + first.replace(b"10:00:00", b"09:55:00"),
        ]
        for index, rows in enumerate(cases):
            with self.subTest(index=index):
                source = self.synthetic_file(f"invalid-{index}.csv", header + rows)
                with approved_dataset(source), self.assertRaises(ValueError):
                    load_dataset(source.path)

    def test_altered_file_and_expected_hash(self):
        source = self.synthetic_file("changed.csv", FIXTURE.read_bytes())
        with approved_dataset(source):
            with self.assertRaisesRegex(ValueError, "expected SHA256"):
                load_dataset(source.path, expected_sha256="0" * 64)
            source.path.write_bytes(source.path.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                load_dataset(source.path)

    def test_approval_origin_and_path_are_required(self):
        with self.assertRaisesRegex(ValueError, "approved input manifest"):
            load_dataset(FIXTURE)
        with self.assertRaisesRegex(ValueError, "origin"):
            with approved_dataset(ApprovedDataset(FIXTURE, "0" * 64, " ")):
                self.fail("missing origin was accepted")
        with approved_dataset(ApprovedDataset(FIXTURE, "0" * 64, ORIGIN)):
            with self.assertRaisesRegex(ValueError, "in-scope"):
                load_dataset(FIXTURE.parent / ".." / FIXTURE.name)
            with self.assertRaisesRegex(ValueError, "approved input manifest"):
                load_dataset(FIXTURE.with_name("unlisted.csv"))


if __name__ == "__main__":
    unittest.main()
