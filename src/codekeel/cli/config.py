# Codekeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Validated Codekeel repository configuration."""

from __future__ import annotations

import hashlib
import re
import tomllib
from pathlib import Path, PurePosixPath

from codekeel.check.git import read_blob
from codekeel.check.ports import ScanConfig


class ConfigError(ValueError):
    """Raised when codekeel.toml is invalid or unsafe for a repository."""


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


def parse_config(payload: bytes) -> ScanConfig:
    """Parse and validate config syntax without touching the filesystem."""
    try:
        raw = tomllib.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"invalid codekeel.toml: {exc}") from exc
    if set(raw) != {"scan"} or not isinstance(raw["scan"], dict):
        raise ConfigError("configuration must contain only [scan]")
    scan = raw["scan"]
    if set(scan) != _REQUIRED_SCAN:
        raise ConfigError("[scan] must contain exactly roots, namespace, and contract")
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
        raise ConfigError("scan.namespace must be an ASCII dotted Python namespace")
    contract = _path(scan["contract"], field="scan.contract", allow_dot=False)
    return ScanConfig(
        roots=canonical_roots,
        namespace=namespace,
        contract=PurePosixPath(contract).as_posix(),
        digest=hashlib.sha256(payload).hexdigest(),
    )


def _contained(root: Path, relative: str, *, field: str) -> Path:
    repository = root.resolve()
    target = (root / relative).resolve()
    try:
        target.relative_to(repository)
    except ValueError as exc:
        raise ConfigError(f"{field} escapes repository root") from exc
    return target


def load_config(root: Path) -> ScanConfig:
    """Load codekeel.toml and validate paths against the repository filesystem."""
    repository = root.resolve()
    config_path = repository / "codekeel.toml"
    try:
        config_path.resolve().relative_to(repository)
        payload = config_path.read_bytes()
    except ValueError as exc:
        raise ConfigError("codekeel.toml escapes repository root") from exc
    except OSError as exc:
        raise ConfigError(f"cannot read codekeel.toml: {exc}") from exc
    config = parse_config(payload)
    for relative in config.roots:
        target = _contained(repository, relative, field="scan.roots")
        if not target.is_dir():
            raise ConfigError(f"scan root is not a directory: {relative}")
    contract = _contained(repository, config.contract, field="scan.contract")
    if not contract.is_file():
        raise ConfigError(f"scan contract is not a file: {config.contract}")
    return config


def load_check_config(root: Path, baseline: str, head: str) -> ScanConfig:
    """Use the accepted Git blob and reject a candidate policy change."""
    payload = read_blob(root, baseline, "codekeel.toml")
    if payload != read_blob(root, head, "codekeel.toml"):
        raise ConfigError("candidate changed accepted policy input: codekeel.toml")
    return parse_config(payload)
