# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one owner of the two coverage questions: is the observation complete, and do the scan
roots contain the source.

Evidence can only prove a rule inside what the scan read. `observation_complete` answers the
first question for the whole observation. The `scan_*` functions answer the second for one source
scope: they map each module to its physical directory or file and ask whether a scan root contains
it. `decisions` (saved observations) and `check.evaluation.rules` (live scans) both call them.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import PurePosixPath

from .facts import in_scope
from .model import Coverage, Observation, Record, Verdict
from .profiles import Profile, profile_for

# One observed module: its qualified name and its repository-relative file.
ModuleFile = tuple[str, str]


def observation_complete(coverage: Coverage) -> bool:
    """An observation is complete when its status is PASS and it records no failure."""
    return coverage.status == Verdict.PASS and not coverage.failures


def _relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    return PurePosixPath(*(part for part in path.parts if part not in {".", ""}))


def _contains(root: PurePosixPath, path: PurePosixPath) -> bool:
    return not root.is_absolute() and path.is_relative_to(root)


def _under(path: PurePosixPath, roots: Iterable[str]) -> bool:
    return any(_contains(_relative_path(root), path) for root in roots)


def under_roots(path: str, roots: Iterable[str]) -> bool:
    """Tell whether a repository-relative path lies under one relative scan root."""
    return _under(_relative_path(path), roots)


def _package_paths(
    package: str, modules: Iterable[ModuleFile], profile: Profile
) -> frozenset[PurePosixPath]:
    """Map the modules of a package to their physical domains. An unplaceable module gives none."""
    package_parts = tuple(package.split("."))
    paths: set[PurePosixPath] = set()
    for name, file in modules:
        if not in_scope(name, package):
            continue
        if profile.source_suffix != ".py":
            extra_modules = len(name.split(".")) - len(package_parts)
            path = _relative_path(file).parent
            extra_parent_steps = max(extra_modules - 1, 0)
            for _ in range(extra_parent_steps):
                path = path.parent
            paths.add(path)
            continue
        file_path = _relative_path(file)
        directories = file_path.parent.parts
        module_parts = (
            directories if file_path.name == "__init__.py" else (*directories, file_path.stem)
        )
        anchor = next(
            (start for start in range(len(module_parts)) if ".".join(module_parts[start:]) == name),
            None,
        )
        if anchor is None:
            return frozenset()
        package_path = next(
            (
                PurePosixPath(*directories[:end])
                for end in range(anchor + 1, len(directories) + 1)
                if in_scope(".".join(module_parts[anchor:end]), package)
                and in_scope(name, ".".join(module_parts[anchor:end]))
            ),
            None,
        )
        if package_path is not None:
            paths.add(package_path)
        elif name == package and file_path.name != "__init__.py":
            paths.add(file_path.parent)
        else:
            return frozenset()
    return frozenset(paths)


def scan_covers_packages(
    packages: Sequence[str],
    modules: Iterable[ModuleFile],
    profile: Profile,
    roots: Sequence[str],
) -> bool:
    """Prove that every observed physical domain of each package lies under a scan root."""
    if not packages or not roots:
        return False
    observed = tuple(modules)
    return all(
        (paths := _package_paths(package, observed, profile))
        and all(_under(path, roots) for path in paths)
        for package in packages
    )


def scan_covers_exact_modules(
    exact_modules: Sequence[str], modules: Iterable[ModuleFile], roots: Sequence[str]
) -> bool:
    """Prove that each exact module was observed in a file under a scan root."""
    observed = tuple(modules)
    return bool(roots) and all(
        any(name == exact and under_roots(file, roots) for name, file in observed)
        for exact in exact_modules
    )


def scan_domains_complete(
    modules: Iterable[ModuleFile],
    profile: Profile,
    package_scopes: Sequence[str],
    exact_module_scopes: Sequence[str],
    roots: Sequence[str],
) -> bool:
    """Prove that the selected package and exact-module domains were fully scanned."""
    observed = tuple(modules)
    return (
        not package_scopes or scan_covers_packages(package_scopes, observed, profile, roots)
    ) and scan_covers_exact_modules(exact_module_scopes, observed, roots)


def observation_covers_rule(observation: Observation, declaration: Record) -> bool:
    """Prove that the scan roots which an observation recorded contain the source of a rule.

    The Python collector records each root as `root/**/*.py`. The roots are the directories.
    A declaration without a source name has no domain to cover.
    """
    source = declaration.data.get("source")
    if not isinstance(source, str):
        return False
    roots: list[str] = []
    for raw_scope in observation.source.scope:
        scope: str = raw_scope
        roots.append(scope.removesuffix("/**/*.py"))
    modules = tuple(
        (name, file)
        for item in observation.records("modules") or ()
        if isinstance(name := item.data.get("qualified_name"), str)
        and isinstance(file := item.data.get("file"), str)
    )
    return scan_covers_packages((source,), modules, profile_for(observation.analyzer.name), roots)
