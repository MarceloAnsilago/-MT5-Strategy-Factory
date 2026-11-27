"""Exercise the documented offline example and the public pipeline boundaries."""

from hashlib import sha256
import json
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest

from examples.research_offline import main as run_example
from strategy_factory.generator import canonical, render
from strategy_factory.research.pipeline import load_config, resume_pipeline, run_pipeline


PROJECT = Path(__file__).resolve().parents[1]


def digest(data):
    return sha256(data).hexdigest()


class ResearchOfflineE2ETests(unittest.TestCase):
    def test_example_reproduces_sources_and_manifests(self):
        runs = []
        for _ in range(2):
            temporary = tempfile.TemporaryDirectory(
                dir=PROJECT / "artifacts/offline", prefix="sf-o06-e2e-",
            )
            self.addCleanup(temporary.cleanup)
            output_root = Path(temporary.name)
            output_root.rmdir()  # The pipeline creates its own exclusive directory.
            captured = StringIO()
            with redirect_stdout(captured):
                run_example(output_root=output_root)
            observed = json.loads(captured.getvalue())
            root = PROJECT / observed["output_root"]
            self.assertEqual(root.parent, PROJECT / "artifacts" / "offline")
            manifest = json.loads((root / "manifest.json").read_bytes())
            plan = {key: value for key, value in manifest.items()
                    if key not in {"status", "content_sha256", "audit"}}
            self.assertEqual(manifest["status"], "completed")
            self.assertEqual(observed["status"], manifest["status"])
            self.assertEqual(observed["content_sha256"], manifest["content_sha256"])
            self.assertEqual(digest(canonical(plan).encode()), manifest["content_sha256"])
            self.assertEqual(json.loads((root / "checkpoint.json").read_bytes()),
                             dict(plan, status="incomplete"))
            self.assertEqual(observed["resource_plan"], manifest["resource_plan"])
            self.assertEqual(plan["resource_plan"]["candidate_limit"], 32)
            self.assertEqual(plan["resource_plan"]["candidate_count"], 8)
            self.assertEqual(plan["evidence_kind"], "simulation")
            self.assertFalse(plan["backtest_performed"])
            self.assertFalse(plan["live_execution_enabled"])

            config = dict(load_config(), candidate_limit=32)
            inputs = {"config": digest(canonical(config).encode())}
            inputs.update({key: digest((PROJECT / path).read_bytes())
                           for key, path in config["inputs"].items()})
            self.assertEqual(plan["input_sha256"], inputs)
            hashes = plan["artifact_sha256"]
            report_name = plan["report_file"]
            report = json.loads((root / report_name).read_bytes())
            self.assertEqual(report["catalog"], plan["candidates"])
            for key in ("evidence_kind", "live_execution_enabled", "backtest_performed"):
                self.assertEqual(report[key], plan[key])
            self.assertTrue(report["fixture_comparison"]["ranked"])
            self.assertEqual(len(report["catalog"]), 8)
            expected_artifacts = {report_name}
            for candidate in report["catalog"]:
                source_name, spec_name = candidate["source_file"], candidate["spec_file"]
                expected_artifacts.update((source_name, spec_name))
                spec = json.loads((root / spec_name).read_bytes())
                normalized, source, metadata = render(spec)
                self.assertEqual((root / spec_name).read_bytes(), canonical(normalized).encode())
                self.assertEqual((root / source_name).read_bytes(), source.encode())
                self.assertEqual(candidate["candidate_id"], metadata["candidate_id"])
                self.assertEqual(candidate["source_sha256"], hashes[source_name])
                self.assertEqual(candidate["spec_sha256"], hashes[spec_name])
                self.assertEqual(candidate["status"], "source_only")
                self.assertIsNone(candidate["compiled_sha256"])
            self.assertEqual(set(hashes), expected_artifacts)
            for name, expected in hashes.items():
                self.assertEqual(digest((root / name).read_bytes()), expected, name)
            sizes = {path.name: path.stat().st_size for path in root.iterdir()}
            self.assertEqual(set(sizes), expected_artifacts | {
                ".run.lock", "checkpoint.json", "manifest.json",
            })
            self.assertEqual(observed["file_bytes"], sizes)
            self.assertEqual(observed["total_bytes"], sum(sizes.values()))
            self.assertGreaterEqual(observed["elapsed_seconds"], 0)
            runs.append((root, manifest))

        self.assertNotEqual(runs[0][0], runs[1][0])
        self.assertEqual(runs[0][1]["content_sha256"], runs[1][1]["content_sha256"])
        self.assertEqual(runs[0][1]["artifact_sha256"], runs[1][1]["artifact_sha256"])
        self.assertEqual(resume_pipeline(config, output_root=runs[0][0]), runs[0][1])

        root, manifest = runs[1]
        source_path = root / manifest["candidates"][0]["source_file"]
        source_path.write_bytes(source_path.read_bytes() + b"\n// tampered\n")
        before_resume = {path.name: path.read_bytes() for path in root.iterdir()}
        with self.assertRaisesRegex(ValueError, "artifact hash mismatch"):
            resume_pipeline(config, output_root=root)
        self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before_resume)
        with self.assertRaises(FileExistsError):
            run_pipeline(config, output_root=root)

    def test_invalid_requests_create_no_run(self):
        temporary = tempfile.TemporaryDirectory(
            dir=PROJECT / "artifacts/offline", prefix="sf-o06-negative-",
        )
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        root.rmdir()
        config = load_config()
        cases = (
            (dict(config, candidate_limit=33), root),
            (dict(config, candidate_limit=7), root),
            (dict(config, inputs=dict(config["inputs"], bars="other.csv")), root),
            (config, root / "nested"),
        )
        for request, output_root in cases:
            with self.subTest(request=request, output_root=output_root):
                with self.assertRaises(ValueError):
                    run_pipeline(request, output_root=output_root)
                self.assertFalse(root.exists())
