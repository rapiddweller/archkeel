# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find the Python source root of a project that has no scan scope yet (AD-47)."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Final

from archkeel.ir.model import Diagnostic, DiagnosticError
from archkeel.ir.model import DiagnosticKind as _DiagnosticKind
from archkeel.ir.profiles import Language, is_test_source

_SOURCE_DISCOVERY_EXCLUDED_DIRS: Final = frozenset(
    {".git", ".venv", "venv", "env", "docs", "build", "dist", "node_modules", "vendor"}
)


def _project_import_name(root: Path) -> str | None:
    """Return pyproject.toml's `[project] name` in wheel file-name form, if one is declared."""
    try:
        pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None
    project = pyproject.get("project")
    name = project.get("name") if isinstance(project, dict) else None
    return re.sub(r"[-_.]+", "_", name).lower() if isinstance(name, str) else None


def detect_source(root: Path) -> tuple[str, str]:
    """Return the scan root and namespace of the only top-level package, or of the one
    package named after the project when there are several (AD-47)."""
    src = root / "src"
    base = src if src.is_dir() else root
    packages = _python_source_roots(base)
    searched = [base.relative_to(root).as_posix()]
    if base == src and not packages:
        base = root
        packages = _python_source_roots(base)
        searched.append(base.relative_to(root).as_posix())
    name = _project_import_name(root)
    chosen = packages if len(packages) == 1 else [p for p in packages if p.name.lower() == name]
    if len(chosen) != 1:
        found = ", ".join(path.relative_to(root).as_posix() for path in packages) or "none"
        searched_directories = ", ".join(f"`{directory}`" for directory in searched)
        raise DiagnosticError(
            Diagnostic(
                _DiagnosticKind.SCOPE_EMPTY,
                str(base),
                "Expected one top-level Python package, or one matching pyproject.toml's "
                f"[project] name ({name or 'missing'}); found {found}. Searched directories "
                f"{searched_directories}.",
                "Pass --source <directory> and --namespace <package>.",
            )
        )
    return chosen[0].relative_to(root).as_posix(), chosen[0].name


def _python_source_roots(base: Path) -> list[Path]:
    """Find immediate package roots, including production namespace packages."""
    directories = sorted(
        path
        for path in base.iterdir()
        if path.is_dir()
        and not path.is_symlink()
        and path.name.isidentifier()
        and path.name not in _SOURCE_DISCOVERY_EXCLUDED_DIRS
        and not is_test_source(path.name + "/__init__.py", Language.PYTHON)
    )
    roots = [
        path
        for path in directories
        if (path / "__init__.py").is_file() and not (path / "__init__.py").is_symlink()
    ]
    for path in directories:
        if (path / "__init__.py").is_file() and not (path / "__init__.py").is_symlink():
            continue
        if _contains_production_python(path, base):
            roots.append(path)
    return sorted(roots)


def _contains_production_python(root: Path, base: Path) -> bool:
    """Stop at a source file and prune tests, generated trees, dependencies and symlinks."""
    for current, directories, files in os.walk(root, followlinks=False, onerror=_raise_walk_error):
        current_path = Path(current)
        relative = current_path.relative_to(base).as_posix()
        directories[:] = [
            name
            for name in directories
            if name not in _SOURCE_DISCOVERY_EXCLUDED_DIRS
            and not name.startswith(".")
            and not is_test_source(f"{relative}/{name}/__init__.py", Language.PYTHON)
            and not (current_path / name).is_symlink()
        ]
        if any(
            name.endswith(".py")
            and not (current_path / name).is_symlink()
            and not is_test_source(f"{relative}/{name}", Language.PYTHON)
            for name in files
        ):
            return True
    return False


def _raise_walk_error(error: OSError) -> None:
    raise error
