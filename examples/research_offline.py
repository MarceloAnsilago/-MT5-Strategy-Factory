"""Run the versioned synthetic research example and print observed measurements."""

import json
from pathlib import Path
import sys
from time import perf_counter
from uuid import uuid4

PROJECT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(PROJECT))

from strategy_factory.research.pipeline import run_pipeline


def main(*, output_root=None):
    """Run the real example; callers may supply a fresh isolated output path."""
    output_root = Path(output_root) if output_root is not None else (
        PROJECT / "artifacts/offline" / f"sf-o06-example-{uuid4().hex}"
    )
    started = perf_counter()
    manifest = run_pipeline(
        {"schema_version": "1.0", "candidate_limit": 32},
        output_root=PROJECT / output_root,
    )
    elapsed = perf_counter() - started
    files = sorted(path for path in (PROJECT / output_root).iterdir() if path.is_file())
    sizes = {path.name: path.stat().st_size for path in files}
    print(json.dumps({
        "output_root": output_root.relative_to(PROJECT).as_posix(),
        "status": manifest["status"],
        "content_sha256": manifest["content_sha256"],
        "resource_plan": manifest["resource_plan"],
        "elapsed_seconds": elapsed,
        "file_bytes": sizes,
        "total_bytes": sum(sizes.values()),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
