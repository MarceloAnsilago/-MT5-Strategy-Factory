"""Reproducible local pipeline for the versioned synthetic fixtures."""

from collections.abc import Mapping
from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from ..generator import MAX_CANDIDATES, canonical, integer, render
from .candidate_catalog import build_catalog, expand_grid
from .experiment_comparison import compare_experiments
from .local_dataset import ApprovedDataset, approved_dataset, load_dataset


_PROJECT = Path(__file__).resolve().parents[2]
_OFFLINE = _PROJECT / "artifacts" / "offline"
_DEFAULT_CONFIG = Path("config/research/pipeline.example.json")
_GRID = Path("config/research/candidate_grid.example.json")
_FIXTURES = Path("tests/fixtures/research")
_BARS = "local_bars_synthetic.csv"
_SUMMARIES = "summaries_synthetic.json"
_INPUT_PATHS = {
    "bars": (_FIXTURES / _BARS).as_posix(),
    "summaries": (_FIXTURES / _SUMMARIES).as_posix(),
    "grid": _GRID.as_posix(),
}
_FIXTURE_HASHES = {
    _BARS: "a74738d1ae42f37c5aab601018b38f85b4ce26acb9cbe3e8bdaf931714c06730",
    _SUMMARIES: "9681cb80c376b0ba1e040867e59a7f4753f50468692f432c6e5bcfefa4ce16f1",
}
_MAX_INPUT_BYTES = 128 * 1024
_STAGING_NAME = re.compile(r"\.staging-[0-9a-f]{32}")


def _json_bytes(value):
    return canonical(value).encode("utf-8")


def _hash(data):
    return sha256(data).hexdigest()


def _read_local(relative_path):
    path = _PROJECT / relative_path
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"expected a regular checkout file: {relative_path}")
    with path.open("rb") as stream:
        data = stream.read(_MAX_INPUT_BYTES + 1)
    if len(data) > _MAX_INPUT_BYTES:
        raise ValueError(f"input exceeds byte limit: {relative_path}")
    return data


def load_config(path=_DEFAULT_CONFIG):
    """Read a pipeline configuration from the checkout's research config directory."""
    path = Path(os.path.abspath(_PROJECT / path))
    if path.parent != _PROJECT / "config" / "research":
        raise ValueError("configuration must be under config/research")
    return json.loads(_read_local(path.relative_to(_PROJECT)).decode("utf-8-sig"))


def _fixture(name):
    data = _read_local(_FIXTURES / name)
    if _hash(data.replace(b"\r\n", b"\n")) != _FIXTURE_HASHES[name]:
        raise ValueError(f"versioned fixture hash mismatch: {name}")
    return data


def _plan(config):
    if isinstance(config, (str, os.PathLike)):
        config = load_config(config)
    required = {"schema_version", "candidate_limit"}
    if not isinstance(config, Mapping) or set(config) not in (required, required | {"inputs"}):
        raise ValueError("configuration requires schema_version and candidate_limit")
    if config["schema_version"] != "1.0":
        raise ValueError("unsupported pipeline configuration version")
    if config.get("inputs", _INPUT_PATHS) != _INPUT_PATHS:
        raise ValueError("configuration must use the checkout's versioned synthetic inputs")
    limit = config["candidate_limit"]
    integer(limit, 1, MAX_CANDIDATES)

    bars = _fixture(_BARS)
    summaries = _fixture(_SUMMARIES)
    grid = _read_local(_GRID)
    dataset_source = ApprovedDataset(_FIXTURES / _BARS, _hash(bars), "synthetic fixture")
    with approved_dataset(dataset_source):
        dataset = load_dataset(dataset_source.path)
    specifications = expand_grid(**json.loads(grid), limit=limit)
    catalog = build_catalog(specifications, limit=limit)
    files = {}
    by_spec = {record["spec_sha256"]: record for record in catalog}
    for specification in specifications:
        spec, source, metadata = render(specification)
        record = by_spec.pop(metadata["spec_sha256"], None)
        if record is None:
            continue
        spec_file = f'{record["candidate_id"]}.spec.json'
        record["spec_file"] = spec_file
        files[spec_file] = _json_bytes(spec)
        files[record["source_file"]] = source.encode("utf-8")

    comparison = compare_experiments(json.loads(summaries))
    files["report.json"] = _json_bytes({
        "evidence_kind": "simulation",
        "live_execution_enabled": False,
        "backtest_performed": False,
        "explanation": (
            "The bars support a synthetic dataset audit. The comparison uses "
            "prewritten synthetic summaries and assigns no results to generated candidates."
        ),
        "dataset_audit": dataset["audit"],
        "catalog": catalog,
        "fixture_comparison": comparison,
    })
    plan = {
        "schema_version": "1.0",
        "evidence_kind": "simulation",
        "live_execution_enabled": False,
        "backtest_performed": False,
        "resource_plan": {
            "workers": 1,
            "candidate_limit": limit,
            "input_byte_limit_per_file": _MAX_INPUT_BYTES,
            "candidate_count": len(catalog),
        },
        "input_sha256": {
            "config": _hash(_json_bytes(dict(config, inputs=_INPUT_PATHS))),
            "grid": _hash(grid),
            "bars": _hash(bars),
            "summaries": _hash(summaries),
        },
        "report_file": "report.json",
        "candidates": catalog,
        "artifact_sha256": {name: _hash(data) for name, data in files.items()},
    }
    return plan, files


def _output_path(output_root):
    root = Path(os.path.abspath(_PROJECT / output_root))
    if root.parent != _OFFLINE or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", root.name):
        raise ValueError("output_root must name one run under artifacts/offline")
    if root.name.endswith(".") or root.is_reserved() or root.resolve() != root:
        raise ValueError("output_root must use a regular checkout path")
    return root


def _verify(path, expected):
    if path.resolve(strict=True) != path or not path.is_file():
        raise ValueError(f"invalid run artifact: {path.name}")
    with path.open("rb") as stream:
        actual = stream.read(len(expected) + 1)
    if _hash(actual) != _hash(expected):
        raise ValueError(f"run artifact hash mismatch: {path.name}")


def _publish(path, data):
    """Publish a fully written file while holding the run lock."""
    staged = path.parent / f".staging-{uuid4().hex}"
    try:
        with staged.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        staged.replace(path)
    finally:
        staged.unlink(missing_ok=True)


@contextmanager
def _run_lock(root, *, create=False):
    path = root / ".run.lock"
    if not create and (path.resolve(strict=True) != path or not path.is_file()):
        raise ValueError("invalid run lock path")
    with path.open("x+b" if create else "r+b") as stream:
        # Closing the descriptor releases the lock even after process interruption.
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


def _continue_run(root, plan, files):
    run_metadata = {".run.lock", "checkpoint.json", "manifest.json"}
    for path in root.iterdir():
        if path.name in files:
            _verify(path, files[path.name])
        elif path.name not in run_metadata and not _STAGING_NAME.fullmatch(path.name):
            raise ValueError(f"unexpected run artifact: {path.name}")

    manifest_path = root / "manifest.json"
    completed = manifest_path.exists() or manifest_path.is_symlink()
    if not completed:
        for name, data in files.items():
            path = root / name
            if not path.exists():
                _publish(path, data)

    for name, data in files.items():
        _verify(root / name, data)
    manifest = dict(plan, status="completed", content_sha256=_hash(_json_bytes(plan)))
    if not completed:
        result = dict(
            manifest, audit={"completed_at": datetime.now(timezone.utc).isoformat()},
        )
        _publish(manifest_path, _json_bytes(result))
        return result

    if manifest_path.resolve(strict=True) != manifest_path or not manifest_path.is_file():
        raise ValueError("invalid manifest path")
    with manifest_path.open("rb") as stream:
        limit = len(_json_bytes(manifest)) + 128
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("completed manifest exceeds expected size")
    result = json.loads(data)
    if not isinstance(result, dict):
        raise ValueError("invalid completed manifest")
    audit = result.pop("audit", None)
    if result != manifest or not isinstance(audit, dict) or set(audit) != {"completed_at"}:
        raise ValueError("completed manifest differs from expected content")
    completed_at = audit["completed_at"]
    if not isinstance(completed_at, str) or datetime.fromisoformat(completed_at).tzinfo != timezone.utc:
        raise ValueError("invalid completion timestamp")
    return dict(result, audit=audit)


def run_pipeline(config, *, output_root):
    """Create an exclusive run directory and return its completed manifest."""
    root = _output_path(output_root)
    if root.exists():
        raise FileExistsError(root)
    plan, files = _plan(config)
    _OFFLINE.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    checkpoint = _json_bytes(dict(plan, status="incomplete"))
    with _run_lock(root, create=True):
        _publish(root / "checkpoint.json", checkpoint)
        return _continue_run(root, plan, files)


def resume_pipeline(config, *, output_root):
    """Verify the original plan and existing files before filling missing artifacts."""
    root = _output_path(output_root)
    plan, files = _plan(config)
    with _run_lock(root):
        _verify(root / "checkpoint.json", _json_bytes(dict(plan, status="incomplete")))
        return _continue_run(root, plan, files)
