# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validated Archkeel repository configuration."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path, PurePosixPath
from typing import Final

from archkeel.check.git import read_blob
from archkeel.check.ports import Language, ScanConfig

CONFIG_PATH: Final = "archkeel.toml"


class ConfigError(ValueError):
    """Raised when a scan configuration is invalid or unsafe for a repository."""


_NAMESPACE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*")
_REQUIRED_SCAN = {"roots", "namespace", "contract"}
_GLOB_SYNTAX = frozenset("*?[]{}!")


def _path(value: object, *, field: str, allow_dot: bool = True) -> str:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{field} must be a non-empty string")
    if (
        "\x00" in value
        or "\\" in value
        or ":" in value
        or any(char in value for char in _GLOB_SYNTAX)
    ):
        raise ConfigError(f"{field} must be a safe POSIX relative path")
    parsed = PurePosixPath(value)
    if parsed.is_absolute() or ".." in parsed.parts or (not allow_dot and value == "."):
        raise ConfigError(f"{field} must be a safe POSIX relative path")
    return value


def project_name(root: Path, config: ScanConfig) -> str:
    """Use valid Python project metadata for display, otherwise the configured namespace."""
    if config.language == "python":
        try:
            path = _contained(root, "pyproject.toml", field="project metadata")
            with open(path, "rb") as stream:
                metadata = tomllib.load(stream)
        except (ConfigError, OSError, RuntimeError, UnicodeDecodeError, tomllib.TOMLDecodeError):
            return config.namespace
        project = metadata.get("project")
        name = project.get("name") if isinstance(project, dict) else None
        if isinstance(name, str) and re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", name
        ):
            return name
    return config.namespace


def parse_config(payload: bytes, name: str = CONFIG_PATH) -> ScanConfig:
    """Parse and validate config syntax without touching the filesystem; `name` is the file."""
    try:
        raw = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid {name}: {exc}") from exc
    if set(raw) != {"scan"} or not isinstance(raw["scan"], dict):
        raise ConfigError("configuration must contain only [scan]")
    scan = raw["scan"]
    optional = {"language", "tsconfig", "collector_argv"}
    if set(scan) - optional != _REQUIRED_SCAN:
        raise ConfigError(
            "[scan] requires roots, namespace, and contract; language, tsconfig, and "
            "collector_argv are optional"
        )
    # AD-97: absent means Python, so an existing archkeel.toml keeps its bytes and its digest.
    language_value = scan.get("language", "python")
    if language_value == "python":
        language: Language = "python"
    elif language_value == "dart":
        language = "dart"
    elif language_value == "typescript":
        language = "typescript"
    else:
        raise ConfigError('scan.language must be "python", "dart", or "typescript"')
    tsconfig_raw = scan.get("tsconfig")
    if tsconfig_raw is not None and language != "typescript":
        raise ConfigError("scan.tsconfig is only valid when scan.language is typescript")
    tsconfig = (
        _path(tsconfig_raw, field="scan.tsconfig", allow_dot=False)
        if tsconfig_raw is not None
        else "tsconfig.json"
        if language == "typescript"
        else None
    )
    argv_raw = scan.get("collector_argv")
    if argv_raw is not None:
        if (
            not isinstance(argv_raw, list)
            or not argv_raw
            or not all(
                isinstance(value, str) and value and "\x00" not in value for value in argv_raw
            )
        ):
            raise ConfigError("scan.collector_argv must be a non-empty array of non-empty strings")
        collector_argv = tuple(argv_raw)
    else:
        collector_argv = None
    roots_raw = scan["roots"]
    if not isinstance(roots_raw, list) or not roots_raw:
        raise ConfigError("scan.roots must be a non-empty list")
    roots = tuple(_path(value, field="scan.roots item") for value in roots_raw)
    canonical_roots = tuple(PurePosixPath(value).as_posix() for value in roots)
    if len(set(canonical_roots)) != len(roots):
        raise ConfigError("scan.roots must not contain duplicates")
    for index, current in enumerate(canonical_roots):
        for other in canonical_roots[index + 1 :]:
            if (
                PurePosixPath(current) in PurePosixPath(other).parents
                or PurePosixPath(other) in PurePosixPath(current).parents
            ):
                raise ConfigError("scan.roots must not overlap")
    namespace = scan["namespace"]
    if not isinstance(namespace, str) or _NAMESPACE.fullmatch(namespace) is None:
        raise ConfigError("scan.namespace must be an ASCII dotted namespace")
    contract = _path(scan["contract"], field="scan.contract", allow_dot=False)
    return ScanConfig(
        roots=canonical_roots,
        namespace=namespace,
        contract=PurePosixPath(contract).as_posix(),
        digest=hashlib.sha256(payload).hexdigest(),
        language=language,
        tsconfig=tsconfig,
        collector_argv=collector_argv,
    )


def _contained(root: Path, relative: str, *, field: str) -> Path:
    repository = root.resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(repository)
    except ValueError as exc:
        raise ConfigError(f"{field} escapes repository root") from exc
    return target


def load_config(root: Path, path: str = CONFIG_PATH) -> ScanConfig:
    """Load a scan configuration and validate paths against the repository filesystem.

    `path` names a second file for a second scope at the same root, such as a test tree with
    its own namespace and contract; one [scan] still holds one namespace (AD-101).
    """
    repository = root.resolve()
    config_path = repository / _path(path, field="--config", allow_dot=False)
    try:
        config_path.resolve().relative_to(repository)
        payload = config_path.read_bytes()
    except ValueError as exc:
        raise ConfigError(f"{path} escapes repository root") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read {path}: {exc}") from exc
    config = parse_config(payload, path)
    for relative in config.roots:
        target = _contained(repository, relative, field="scan.roots")
        if not target.is_dir() and not (config.language == "typescript" and target.is_file()):
            expected = "directory or file" if config.language == "typescript" else "directory"
            raise ConfigError(f"scan root is not a {expected}: {relative}")
    contract = _contained(repository, config.contract, field="scan.contract")
    if not contract.is_file():
        raise ConfigError(f"scan contract is not a file: {config.contract}")
    if config.tsconfig is not None:
        tsconfig = _contained(repository, config.tsconfig, field="scan.tsconfig")
        if not tsconfig.is_file():
            raise ConfigError(f"scan TypeScript config is not a file: {config.tsconfig}")
    return config


def load_check_config(root: Path, baseline: str, head: str) -> ScanConfig:
    """Use the accepted Git blob and reject a candidate policy change."""
    payload = read_blob(root, baseline, CONFIG_PATH)
    if payload != read_blob(root, head, CONFIG_PATH):
        raise ConfigError(f"candidate changed accepted policy input: {CONFIG_PATH}")
    return parse_config(payload)
