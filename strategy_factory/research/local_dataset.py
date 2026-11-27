"""Load a single declared synthetic source for offline research."""

from contextlib import contextmanager
from contextvars import ContextVar
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re

from ..batch_manifest import sha
from ..dataset_policy import build_dataset_manifest
from ..history_audit import BAR_FIELDS, audit_collection, audit_snapshot


_PROJECT = Path(__file__).resolve().parents[2]
_SOURCE_ROOTS = (
    _PROJECT / "artifacts" / "offline",
    _PROJECT / "tests" / "fixtures" / "research",
)
_COLUMNS = ("time", *BAR_FIELDS)
_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")


@dataclass(frozen=True)
class ApprovedDataset:
    """Caller-approved input manifest for one synthetic source."""

    path: Path
    sha256: str
    origin: str
    period: str = "M5"
    timezone_label: str = "unknown"


_APPROVED: ContextVar[ApprovedDataset | None] = ContextVar("approved_dataset", default=None)


def _source_path(path):
    path = Path(path)
    if not path.is_absolute():
        if path.anchor:
            raise ValueError("ambiguous source path")
        path = _PROJECT / path
    if (
        ".." in path.parts
        or not any(root in path.parents for root in _SOURCE_ROOTS)
        or any(":" in part or part.endswith((" ", ".")) for part in path.parts[1:])
        or path.is_reserved()
        or path.suffix.lower() not in (".csv", ".json")
    ):
        raise ValueError("source must be an in-scope CSV or JSON path")
    return path


@contextmanager
def approved_dataset(manifest: ApprovedDataset):
    """Scope loading to a manifest already approved by the caller."""
    sha(manifest.sha256)
    if manifest.sha256 is None:
        raise ValueError("approved source SHA256 required")
    if not isinstance(manifest.origin, str) or not manifest.origin.strip():
        raise ValueError("declared synthetic origin required")
    _source_path(manifest.path)
    token = _APPROVED.set(manifest)
    try:
        yield
    finally:
        _APPROVED.reset(token)


def _finite(value):
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite source number")
    return number


def _json_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON field: {key}")
        obj[key] = value
    return obj


def _csv_snapshot(text, symbol, period):
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=",", strict=True)
    if tuple(next(reader, ())) != _COLUMNS:
        raise ValueError("unexpected CSV columns")
    history = []
    for row in reader:
        if len(row) != len(_COLUMNS) or not all(_DECIMAL.fullmatch(v) for v in row[1:]):
            raise ValueError(f"invalid CSV row at line {reader.line_num}")
        values = [int(v) if "." not in v else _finite(v) for v in row[1:]]
        history.append(dict(zip(_COLUMNS, [row[0], *values])))
    return dict(ok=True, symbol=symbol, period=period, history=history)


def load_dataset(path, *, symbol="PETR4", period="M5", timezone_label="unknown",
                 expected_sha256=None):
    """Return the snapshot, its audit and an unverified dataset manifest."""
    source = _source_path(path)
    approved = _APPROVED.get()
    if approved is None or source != _source_path(approved.path):
        raise ValueError("source path requires an approved input manifest")
    if (symbol, period, timezone_label) != ("PETR4", approved.period, approved.timezone_label):
        raise ValueError("source scope differs from approved input manifest")
    if period not in ("M1", "M5") or timezone_label not in ("unknown", "UTC", "explicit_offsets"):
        raise ValueError("unsupported bar period or timezone declaration")
    if expected_sha256 is not None and expected_sha256 != approved.sha256:
        raise ValueError("expected SHA256 differs from approved source")
    if source.resolve(strict=True) != source or not source.is_file():
        raise ValueError("source must be a regular file at the approved path")
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != approved.sha256:
        raise ValueError("source SHA256 mismatch")
    text = raw.decode("utf-8-sig")
    if source.suffix.lower() == ".csv":
        try:
            snapshot = _csv_snapshot(text, symbol, period)
        except csv.Error as exc:
            raise ValueError("invalid CSV syntax") from exc
    else:
        snapshot = json.loads(text, parse_float=_finite, parse_constant=_finite,
                              object_pairs_hook=_json_object)
    if not isinstance(snapshot, dict) or (snapshot.get("symbol"), snapshot.get("period")) != (symbol, period):
        raise ValueError("snapshot symbol or period differs from approved input manifest")
    if snapshot.get("origin", approved.origin) != approved.origin:
        raise ValueError("snapshot origin differs from approved input manifest")
    if any(snapshot.get(key, timezone_label) != timezone_label for key in ("timezone", "timezone_label")):
        raise ValueError("snapshot timezone differs from approved input manifest")

    audit = audit_snapshot(snapshot, source_id="local_synthetic", timezone_label=timezone_label,
                           file_sha256=digest, origin=approved.origin)
    if audit["errors"]:
        raise ValueError(f"invalid snapshot: {audit['errors']}")
    if not audit["records"]:
        raise ValueError("snapshot must contain at least one bar")
    times = [row["time"] for row in snapshot["history"]]
    if any(value[-6:-5] in ("+", "-") and int(value[-2:]) >= 60 for value in times):
        raise ValueError("invalid timestamp offset minutes")
    stamps = [datetime.fromisoformat(value) for value in times]
    if len({stamp.utcoffset() for stamp in stamps}) > 1:
        raise ValueError("mixed timestamp offsets")

    # Exposure covers observed dates in the audit's date basis, with an exclusive end.
    exposure = dict(exposure_id="synthetic_data_access", kind="data_access",
                    from_date=min(audit["sessions"]),
                    to_date=(datetime.fromisoformat(max(audit["sessions"])).date()
                             + timedelta(days=1)).isoformat(),
                    strategy_ids=[], source_sha256=digest, known_at=None)
    manifest = build_dataset_manifest(audit_collection([audit]), exposures=[exposure],
                                      reviewed_at=datetime.now(timezone.utc).isoformat())
    return dict(snapshot=snapshot, audit=audit, manifest=manifest)
