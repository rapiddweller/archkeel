# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python extension module that a Cargo crate builds, and the Python projects that use it
(AD-784).

A system draft states an interface from a Python part to a Rust part only when the manifests state
both ends: the crate folder holds a `pyproject.toml` that maturin builds with PyO3 into a named
extension module, and the Python project names that distribution in `[project].dependencies` with
a uv source that is this folder (a workspace member or a path). A module name that the Python code
imports, or a crate name that looks like a module, is never a binding. No source file is read.

Only the binding part of the shell parses TOML (`SHELL-ONLY-BINDING-READS-CONFIGURATION`), so the
draft reads each key in its plain form: `key = "text"`, `key = [..]` or `key = { .. }` on the lines
of its `[table]`. Another form of a key reads as absent, so it can miss an interface and never
make one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class _Binding:
    """The extension module of one crate: its dotted name, the normalized name of the Python
    distribution that holds it, and the repository path of the file that states what crosses (the
    type stub of the module, else the `pyproject.toml` that states the binding)."""

    module: str
    distribution: str
    schema: str


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _table(text: str, name: str) -> str | None:
    """The lines of the table `[name]`, up to the next table header; `None` without the header."""
    header = re.search(rf"^\[{re.escape(name)}\][ \t]*(#.*)?$", text, re.M)
    if header is None:
        return None
    end = re.compile(r"^\[", re.M).search(text, header.end())
    return text[header.end() : end.start() if end else len(text)]


def _value(table: str | None, key: str) -> str | None:
    """The text of `key = "text"` (or `'text'`) in the lines of a table."""
    found = re.search(rf"^{re.escape(key)}\s*=\s*([\"'])([^\"'\n]*)\1", table or "", re.M)
    return found[2] if found else None


def _strings(table: str | None, key: str) -> list[str] | None:
    """The texts of `key = [..]` in the lines of a table, or `None` without the key."""
    found = re.search(rf"^{re.escape(key)}\s*=\s*\[(.*?)\]", table or "", re.M | re.S)
    return re.findall(r"[\"']([^\"'\n]+)[\"']", found[1]) if found else None


def _has(table: str | None, key: str) -> bool:
    return re.search(rf"^{re.escape(key)}\s*=", table or "", re.M) is not None


def _normal(name: str) -> str:
    """The PEP 503 name of a distribution."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _binding(repo: Path, crate: Path) -> _Binding | None:
    """The PyO3 extension module that maturin builds from the crate in `crate`, or `None`.

    The module is `[tool.maturin] module-name`, else the `[lib] name` of `Cargo.toml`, else the
    package name with `_` for `-`: the rule of maturin. PyO3 is `bindings = "pyo3"`, or no
    `bindings` key and a `pyo3` dependency (maturin finds it so)."""
    project = _text(crate / "pyproject.toml")
    if _value(_table(project, "build-system"), "build-backend") != "maturin":
        return None
    maturin = _table(project, "tool.maturin")
    cargo = _text(crate / "Cargo.toml")
    bindings = _value(maturin, "bindings")
    pyo3 = _has(_table(cargo, "dependencies"), "pyo3") or _table(cargo, "dependencies.pyo3")
    if not (bindings == "pyo3" or (bindings is None and pyo3)):
        return None
    package = _value(_table(cargo, "package"), "name")
    default = package.replace("-", "_") if package else None
    module = _value(maturin, "module-name") or _value(_table(cargo, "lib"), "name") or default
    distribution = _value(_table(project, "project"), "name")
    if module is None or distribution is None:
        return None
    if not re.fullmatch(r"[A-Za-z_]\w*(\.[A-Za-z_]\w*)*", module):
        return None
    source = _value(maturin, "python-source")
    path = (crate / source if source else crate).joinpath(*module.split("."))
    stubs = [path.with_name(f"{path.name}.pyi"), path / "__init__.pyi"]
    schema = next((stub for stub in stubs if stub.is_file()), crate / "pyproject.toml")
    return _Binding(module, _normal(distribution), schema.relative_to(repo).as_posix())


def _uses(project: Path, crate: Path, found: _Binding) -> bool:
    """Whether the Python project in `project` uses the binding of the crate in `crate`: its own
    `pyproject.toml` is the binding, or it names the distribution as a dependency whose uv source
    is that folder."""
    if project.resolve() == crate.resolve():
        return True
    text = _text(project / "pyproject.toml")
    dependencies = _strings(_table(text, "project"), "dependencies") or []
    named = {
        _normal(match[0]) for item in dependencies if (match := re.match(r"[A-Za-z0-9._-]+", item))
    }
    if found.distribution not in named:
        return False
    sources = _table(text, "tool.uv.sources") or ""
    entries = re.finditer(r"^([A-Za-z0-9._-]+)\s*=\s*\{([^}\n]*)\}", sources, re.M)
    entry = next((m[2] for m in entries if _normal(m[1]) == found.distribution), None)
    if entry is None:
        return False
    if re.search(r"(^|,)\s*workspace\s*=\s*true\s*(,|$)", entry):
        space = _table(text, "tool.uv.workspace")
        members, excluded = _strings(space, "members"), _strings(space, "exclude")
        return _globbed(project, members, crate) and not _globbed(project, excluded, crate)
    path = re.search(r"(^|,)\s*path\s*=\s*\"([^\"]+)\"", entry)
    return path is not None and (project / path[2]).resolve() == crate.resolve()


def _globbed(project: Path, patterns: list[str] | None, folder: Path) -> bool:
    target = folder.resolve()
    return any(
        hit.resolve() == target for pattern in patterns or [] for hit in project.glob(pattern)
    )
