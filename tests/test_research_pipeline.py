"""End-to-end checks for the offline fixture pipeline."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from strategy_factory.research import pipeline


_PROJECT = Path(__file__).resolve().parents[1]


class ResearchPipelineTests(unittest.TestCase):
    def setUp(self):
        self.root = _PROJECT / "artifacts" / "offline" / f"sf-o05-test-{uuid4().hex}"
        self.config = pipeline.load_config()

    def test_cli_and_api_produce_identical_hashed_artifacts(self):
        cli = subprocess.run(
            [sys.executable, "-B", "-m", "strategy_factory.research.cli",
             "--config", "config/research/pipeline.example.json", "--output-root", str(self.root)],
            cwd=_PROJECT, capture_output=True, text=True, check=True,
        )
        first = json.loads((self.root / "manifest.json").read_bytes())
        self.assertEqual(json.loads(cli.stdout)["content_sha256"], first["content_sha256"])
        second_root = self.root.with_name(self.root.name + "-repeat")
        second = pipeline.run_pipeline(self.config, output_root=second_root)
        for key in ("content_sha256", "artifact_sha256", "input_sha256", "resource_plan"):
            self.assertEqual(first[key], second[key])
        self.assertEqual(first["evidence_kind"], "simulation")
        self.assertFalse(first["live_execution_enabled"])
        report = json.loads((self.root / "report.json").read_bytes())
        self.assertEqual(first["report_file"], "report.json")
        self.assertEqual(first["candidates"], report["catalog"])
        self.assertFalse(report["backtest_performed"])
        self.assertTrue(report["fixture_comparison"]["ranked"])
        self.assertEqual(len(report["catalog"]), 8)
        for name, expected in first["artifact_sha256"].items():
            self.assertEqual(sha256((self.root / name).read_bytes()).hexdigest(), expected)
        for record in report["catalog"]:
            self.assertEqual(record["status"], "source_only")
            self.assertIsNone(record["compiled_sha256"])
            self.assertEqual(first["artifact_sha256"][record["source_file"]], record["source_sha256"])
            self.assertEqual(first["artifact_sha256"][record["spec_file"]], record["spec_sha256"])
        with self.assertRaises(FileExistsError):
            pipeline.run_pipeline(self.config, output_root=self.root)

    def interrupt_before_report(self):
        publish = pipeline._publish

        def interrupted(path, data):
            if path.name == "report.json":
                raise KeyboardInterrupt
            publish(path, data)

        with patch.object(pipeline, "_publish", side_effect=interrupted):
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run_pipeline(self.config, output_root=self.root)
        checkpoint = json.loads((self.root / "checkpoint.json").read_bytes())
        self.assertEqual(checkpoint["status"], "incomplete")
        self.assertFalse((self.root / "manifest.json").exists())
        return self.root / next(name for name in checkpoint["artifact_sha256"] if name.endswith(".mq5"))

    def test_resume_publishes_only_missing_artifacts(self):
        source = self.interrupt_before_report()
        modified = source.stat().st_mtime_ns
        with self.assertRaisesRegex(ValueError, "checkpoint.json"):
            pipeline.resume_pipeline(dict(self.config, candidate_limit=9), output_root=self.root)
        result = pipeline.resume_pipeline(self.config, output_root=self.root)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(source.stat().st_mtime_ns, modified)
        self.assertEqual(pipeline.resume_pipeline(self.config, output_root=self.root), result)

    def test_resume_rejects_tampering_before_writing(self):
        source = self.interrupt_before_report()
        source.write_bytes(b"altered")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            pipeline.resume_pipeline(self.config, output_root=self.root)
        self.assertEqual(source.read_bytes(), b"altered")
        self.assertFalse((self.root / "report.json").exists())

    def test_candidate_limit_rejects_grid_before_creating_run(self):
        with self.assertRaises(ValueError):
            pipeline.run_pipeline(dict(self.config, candidate_limit=7), output_root=self.root)
        self.assertFalse(self.root.exists())

    def test_rejects_inputs_outside_versioned_fixtures(self):
        config = dict(self.config, inputs=dict(self.config["inputs"], bars="alternate.csv"))
        with self.assertRaisesRegex(ValueError, "versioned synthetic inputs"):
            pipeline.run_pipeline(config, output_root=self.root)
        self.assertFalse(self.root.exists())
