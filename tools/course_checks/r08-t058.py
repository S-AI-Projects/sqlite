#!/usr/bin/env python3
"""Validate the declared grade-school exercise paths and test-table wiring."""

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


class MetadataError(ValueError):
    """A config path or exercise file-role declaration is invalid."""


def validate(config_path, exercise_dir=None):
    config_path = Path(config_path)
    root = Path(exercise_dir) if exercise_dir is not None else config_path.parent.parent
    root = root.resolve()
    try:
        config_real = config_path.resolve(strict=True)
        config_real.relative_to(root)
    except (FileNotFoundError, ValueError) as error:
        raise MetadataError("config.json must exist inside the exercise directory") from error

    try:
        config = json.loads(config_real.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as error:
        raise MetadataError(f"cannot parse config.json: {error}") from error
    files = config.get("files")
    if not isinstance(files, dict):
        raise MetadataError("config.json must contain a files object")

    resolved = {}
    for required_role in ("solution", "test", "example"):
        if not isinstance(files.get(required_role), list) or not files[required_role]:
            raise MetadataError(f"files.{required_role} must contain at least one path")

    for role, paths in files.items():
        if not isinstance(paths, list) or not paths:
            raise MetadataError(f"files.{role} must be a non-empty list of paths")
        resolved[role] = []
        for index, raw_path in enumerate(paths):
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise MetadataError(f"files.{role}[{index}] must be a non-empty string")
            portable = raw_path.replace("\\", "/")
            posix_path = PurePosixPath(portable)
            windows_path = PureWindowsPath(raw_path)
            if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive or ".." in posix_path.parts:
                raise MetadataError(
                    f"files.{role}[{index}] must be a relative path within the exercise: {raw_path}"
                )
            candidate = root.joinpath(*posix_path.parts)
            try:
                candidate = candidate.resolve(strict=True)
                candidate.relative_to(root)
            except (FileNotFoundError, ValueError) as error:
                raise MetadataError(
                    f"files.{role}[{index}] does not resolve to an existing file inside the exercise: {raw_path}"
                ) from error
            if not candidate.is_file():
                raise MetadataError(f"files.{role}[{index}] is not a file: {raw_path}")
            resolved[role].append(candidate)

    test_sql = resolved["test"][0].read_text(encoding="utf-8")
    if not re.search(r"(?m)^\.read\s+['\"]?\./create_test_table\.sql['\"]?\s*$", test_sql):
        raise MetadataError("the configured test file must read ./create_test_table.sql")
    if not (root / "create_test_table.sql").is_file():
        raise MetadataError("create_test_table.sql is missing from the exercise")

    return {
        "exercise": root,
        "roles": {role: [path.relative_to(root).as_posix() for path in paths]
                  for role, paths in resolved.items()},
        "test_reads_create_test_table": True,
    }


def main():
    repo = Path(__file__).resolve().parents[2]
    exercise = repo / "exercises/practice/grade-school"
    result = validate(exercise / ".meta/config.json", exercise)
    for role, paths in result["roles"].items():
        print(f"{role}: {', '.join(paths)}")
    print("grade-school metadata paths and test-table reference are valid")


if __name__ == "__main__":
    main()
