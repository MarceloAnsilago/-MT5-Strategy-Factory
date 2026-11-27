"""In-memory catalogs and parameter grids for the offline generator."""

from collections.abc import Mapping
from copy import deepcopy
from itertools import product

from ..generator import MAX_CANDIDATES, canonical, digest, integer, render, validate_spec


def build_catalog(specifications, *, limit=MAX_CANDIDATES):
    """Return source metadata for unique candidates in first-seen order."""
    integer(limit, 1, MAX_CANDIDATES)
    records = []
    seen = set()
    for specification in specifications:
        _, _, metadata = render(specification)
        identity = {(key, metadata[key]) for key in
                    ("candidate_id", "spec_sha256", "source_sha256")}
        if seen.intersection(identity):
            continue
        if len(records) == limit:
            raise ValueError("catalog exceeds candidate limit")
        seen.update(identity)
        records.append(dict(metadata, status="source_only"))
    return records


def _axis_path(base, name):
    """Resolve dotted object keys and zero-based list indices."""
    path = []
    node = base
    for part in name.split("."):
        if isinstance(node, dict) and part in node:
            key = part
        elif isinstance(node, list) and part in map(str, range(len(node))):
            key = int(part)
        else:
            raise ValueError(f"axis does not identify an existing field: {name}")
        path.append(key)
        node = node[key]
    return tuple(path)


def expand_grid(base, axes, *, limit=MAX_CANDIDATES):
    """Return validated specifications from a bounded Cartesian product."""
    integer(limit, 1, MAX_CANDIDATES)
    validate_spec(base)
    if not isinstance(axes, Mapping) or any(not isinstance(name, str) for name in axes):
        raise ValueError("axes must map dotted field names to value lists")

    paths = []
    options = []
    size = 1
    for name in sorted(axes):
        path = _axis_path(base, name)
        if any(path[:len(other)] == other for other in paths):
            raise ValueError(f"overlapping grid axis: {name}")
        values = axes[name]
        if not isinstance(values, (list, tuple)) or not values:
            raise ValueError(f"axis requires a nonempty value list: {name}")
        unique = {}
        for value in values:
            unique.setdefault(canonical(value), value)
            if size * len(unique) > limit:
                raise ValueError("grid exceeds candidate limit")
        size *= len(unique)
        paths.append(path)
        options.append(unique.values())

    specifications = []
    seen = set()
    for combination in product(*options):
        candidate = deepcopy(base)
        for path, value in zip(paths, combination):
            target = candidate
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = deepcopy(value)
        normalized = validate_spec(candidate)
        fingerprint = digest(normalized)
        if fingerprint not in seen:
            seen.add(fingerprint)
            specifications.append(normalized)
    return specifications
