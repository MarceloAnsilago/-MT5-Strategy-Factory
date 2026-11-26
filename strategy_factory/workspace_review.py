"""Offline review of the H5J-D workspace contract observed under MCP 2025-06-18.

The definition fingerprint covers every description, including Community metadata.
Descriptions are annotations. The result schema version is a separate string field
whose value was not observed.
"""

import hashlib
import json
from pathlib import PurePath, PurePosixPath, PureWindowsPath


_DEFINITION_SHA256 = "e7261a54334778f38f7f0caa56c3fc8d3a2cd7fa327ee8c9f28198bd755ddfa2"

# Validation rules from the pinned outputSchema. All objects reject extra keys.
# Only the top-level properties are required by the observed schema.
_OUTPUT_SHAPE = {
    "schema_version": "string",
    "workspace": {
        "mql5_folder": "string",
        "include_folder": "string",
        "current_folder": "string",
        "shared_projects_folder": "string",
        "temp_folder": "string",
        "backup_folder": "string",
        "common_folder": "string",
    },
    "permissions": {
        "read_roots": ("string",),
        "write_roots": ("string",),
        "execute_roots": ("string",),
        "can_create_files": "boolean",
        "can_modify_files": "boolean",
        "can_delete_files": "boolean",
    },
    "compiler": {
        "compiler_mql5": "boolean",
        "compiler_mql5_build": "integer",
        "compiler_mql5_target": "string",
        "compiler_python": "boolean",
        "compiler_python_folder": "string",
        "compiler_visual_studio": "boolean",
        "compiler_visual_studio_folder": "string",
        "compiler_visual_studio_msbuild": "string",
        "compiler_windows_sdk_folder": "string",
    },
    "community": {
        "community_website": "string",
        "community_login": "string",
    },
    "ide": {
        "gui_language": "string",
        "dark_theme": "boolean",
        "default_encoding": "string",
        "path_separator": "string",
        "newline": "string",
        "tab_size": "integer",
        "insert_spaces": "boolean",
        "spaces_per_indentation": "integer",
        "convert_tabs_to_spaces": "boolean",
        "code_style": "string",
    },
    "capabilities": {
        "can_compile_file": "boolean",
        "can_compile_project": "boolean",
        "can_run_backtest": "boolean",
        "can_read_terminal_journal": "boolean",
        "can_read_expert_journal": "boolean",
    },
    "limits": {
        "max_read_file_bytes": "integer",
        "max_search_results": "integer",
        "max_directory_tree_depth": "integer",
    },
}

_TYPES = {"boolean": bool, "integer": int, "string": str}


def review_definition(tool: object) -> dict[str, object]:
    """Review the exact observed definition without granting tool access."""
    error = "Workspace tool definition differs from the observed contract."
    try:
        canonical = json.dumps(
            tool, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError):
        pass
    else:
        if hashlib.sha256(canonical).hexdigest() == _DEFINITION_SHA256:
            return {
                "status": "reviewed_offline_only",
                "mcp_calls_authorized": False,
                "definition_sha256": _DEFINITION_SHA256,
            }
    raise ValueError(error)


def _validate(value: object, shape: object, *, required: bool = False) -> None:
    if isinstance(shape, dict):
        if type(value) is dict and value.keys() <= shape.keys():
            if not required or value.keys() == shape.keys():
                for key, child in value.items():
                    _validate(child, shape[key])
                return
    elif isinstance(shape, tuple):
        if type(value) is list:
            for item in value:
                _validate(item, shape[0])
            return
    elif type(value) is _TYPES[shape]:
        return
    raise ValueError("Workspace result violates the observed output schema.")


def _workspace_path(value: str) -> PurePath:
    error = "Invalid workspace path."
    if not value.strip() or "\x00" in value:
        raise ValueError(error)

    # Keep drive, UNC and repository-relative paths independent of the host OS.
    if value.startswith("/") and not value.startswith("//"):
        if "\\" in value:
            raise ValueError(error)
        path = PurePosixPath(value)
    else:
        path = PureWindowsPath(value)
        if (path.anchor and not path.is_absolute()) or path.drive.startswith(
            ("\\\\?\\", "\\\\.\\")
        ):
            raise ValueError(error)
        parts = path.parts[1:] if path.anchor else path.parts
        if path.is_reserved() or any(
            part.endswith((".", " ")) or any(char in part for char in ':*?"<>|')
            for part in parts
        ):
            raise ValueError(error)

    if not path.parts or ".." in path.parts:
        raise ValueError(error)
    return path


def validate_workspace_result(
    result: dict[str, object], *, expected_mql5: str | PurePath
) -> dict[str, bool]:
    """Validate structured content and project only the offline review outcome."""
    _validate(result, _OUTPUT_SHAPE, required=True)

    if not isinstance(expected_mql5, (str, PurePath)):
        raise ValueError("Invalid expected MQL5 path.")
    expected = _workspace_path(str(expected_mql5))
    actual = result["workspace"].get("mql5_folder")
    if actual is None or _workspace_path(actual) != expected:
        raise ValueError("Workspace MQL5 folder differs from the expected installation.")

    permissions = result["permissions"]
    for field in ("read_roots", "write_roots", "execute_roots"):
        for value in permissions.get(field, ()):
            root = _workspace_path(value)
            if field == "write_roots" and not root.is_relative_to(expected):
                raise ValueError("Workspace write root is outside the expected MQL5 folder.")

    return {"identity_confirmed": True, "mcp_calls_authorized": False}
