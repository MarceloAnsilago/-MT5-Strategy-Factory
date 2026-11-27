"""Command line for the local synthetic research pipeline."""

import argparse
import json
from uuid import uuid4

from .pipeline import resume_pipeline, run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config/research/pipeline.example.json")
    parser.add_argument("--output-root", help="Run directory under artifacts/offline")
    parser.add_argument("--resume", action="store_true", help="Verify and resume an existing run")
    args = parser.parse_args(argv)
    if args.resume and args.output_root is None:
        parser.error("--resume requires --output-root")
    output_root = args.output_root or f"artifacts/offline/pipeline-{uuid4().hex}"
    operation = resume_pipeline if args.resume else run_pipeline
    try:
        manifest = operation(args.config, output_root=output_root)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(json.dumps(dict(manifest, output_root=output_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
