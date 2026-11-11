# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Leave test sources out of an Explore scan and mark each import into one as UNKNOWN."""

from __future__ import annotations

from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final

from archkeel.ir.facts import SOURCE_RESOLUTION_GAP_KIND, EvidenceClass, Language, Record, stable_id
from archkeel.ir.facts_codec import RawRecord, classified, parse_record
from archkeel.ir.profiles import is_test_source
from archkeel.ir.protocol import CollectionRequest, ProtocolVersion

from .imports import collect_package_bindings
from .source import ParsedModule, ParsedSources, module_for, parse_sources

_SHADOWED_KIND: Final = "ShadowedModule"
NO_PRODUCTION_SOURCE = "No production source files in scope after the test exclusion"


def wire_protocol(request: CollectionRequest, ordinary: ProtocolVersion) -> ProtocolVersion:
    """Return protocol 9, the first version with the scope flag, when the scan excludes tests."""
    return ProtocolVersion.V9 if request.scope.exclude_test_sources else ordinary


def _inside(repository: Path, path: Path) -> bool:
    return path.resolve().is_relative_to(repository)


def _is_test(repository: Path, path: Path, suffix: str = "") -> bool:
    """Judge the path as written and as resolved, so a link cannot hide a test source."""
    return any(
        is_test_source(f"{item.relative_to(repository).as_posix()}{suffix}", Language.PYTHON)
        for item in (path, path.resolve())
    )


def selected_paths(
    root: Path, roots: tuple[str, ...], *, exclude_test_sources: bool
) -> tuple[Path, ...]:
    repository = root.resolve()
    selected: list[Path] = []
    for source in roots:
        source_root = repository / source
        if not source_root.is_dir():
            continue
        for path in source_root.rglob("*.py"):
            if "__pycache__" in path.parts or not _inside(repository, path):
                continue
            if not (exclude_test_sources and _is_test(repository, path)):
                selected.append(path)
    return tuple(sorted(selected))


@dataclass(frozen=True, slots=True)
class ExcludedTests:
    """The modules and the packages that the scan leaves out because they are tests."""

    modules: frozenset[str]
    prefixes: frozenset[str]
    files: int

    @classmethod
    def find(cls, root: Path, roots: tuple[str, ...], namespace: str) -> ExcludedTests:
        repository = root.resolve()
        modules: set[str] = set()
        prefixes: set[str] = set()
        files = 0
        for source in roots:
            source_root = repository / source
            if not source_root.is_dir():
                continue
            for directory in source_root.rglob("*"):
                if (
                    directory.is_dir()
                    and _inside(repository, directory)
                    and _is_test(repository, directory, "/__init__.py")
                ):
                    with suppress(ValueError):
                        prefixes.add(
                            module_for(
                                directory / "__init__.py", root=repository, namespace=namespace
                            )
                        )
            for path in source_root.rglob("*.py"):
                if _inside(repository, path) and _is_test(repository, path):
                    files += 1
                    modules.update(_module_names(repository, source_root, path, namespace))
        return cls(frozenset(modules), frozenset(prefixes), files)

    def match(self, names: Sequence[str]) -> str | None:
        return next(
            (
                name
                for name in names
                if name in self.modules
                or any(name == prefix or name.startswith(f"{prefix}.") for prefix in self.prefixes)
            ),
            None,
        )

    def gaps(
        self,
        imports: Sequence[RawRecord],
        modules: Sequence[ParsedModule],
        selected: Sequence[Path],
    ) -> list[Record]:
        """Return the gaps of the static imports, and one when the exclusion left no source."""
        found = self._gaps(imports, collect_package_bindings(modules))
        return [*found, _empty_scope_gap()] if self.files and not selected else found

    def dynamic_import_gaps(self, imports: Sequence[RawRecord]) -> list[Record]:
        return self._gaps(imports, None)

    def _gaps(
        self, imports: Sequence[RawRecord], package_bindings: dict[str, frozenset[str]] | None
    ) -> list[Record]:
        gaps: list[Record] = []
        for record in imports:
            data = record.get("data")
            target = data.get("target_module") if isinstance(data, dict) else None
            symbol = data.get("symbol") if isinstance(data, dict) else None
            source_module = data.get("source_module") if isinstance(data, dict) else None
            if not isinstance(target, str) or not isinstance(source_module, str):
                continue
            names = [target]
            if (
                package_bindings is not None
                and isinstance(symbol, str)
                and symbol.isidentifier()
                and symbol not in package_bindings.get(target, frozenset())
            ):
                names.append(f"{target}.{symbol}")
            excluded = self.match(names)
            if excluded is not None:
                gaps.append(_import_gap(record, source_module, excluded))
        return gaps


def _module_names(repository: Path, source_root: Path, path: Path, namespace: str) -> set[str]:
    names: set[str] = set()
    for source_path in {path, path.resolve()}:
        try:
            names.add(module_for(source_path, root=repository, namespace=namespace))
        except ValueError:
            if not source_path.is_relative_to(source_root):
                continue
            parts = list(source_path.relative_to(source_root).with_suffix("").parts)
            if parts and parts[-1] == "__init__":
                parts.pop()
            if parts:
                names.add(".".join(parts))
    return names


def _import_gap(record: RawRecord, source_module: str, excluded: str) -> Record:
    return parse_record(
        classified(
            item_id=stable_id("UNKNOWN", "excluded test import", record["id"], excluded),
            evidence_class=EvidenceClass.UNKNOWN,
            area="source",
            kind=SOURCE_RESOLUTION_GAP_KIND,
            title=f"Production import targets excluded test source {excluded}",
            subjects=[source_module],
            evidence_ids=record["evidence_ids"],
            fact_ids=[record["id"]],
            data={
                "reason": "Import target is an excluded test source",
                "module": source_module,
                "source_module": source_module,
                "resolution_dimension": "imports",
            },
        )
    )


def _empty_scope_gap() -> Record:
    return parse_record(
        classified(
            item_id=stable_id("UNKNOWN", NO_PRODUCTION_SOURCE, ""),
            evidence_class=EvidenceClass.UNKNOWN,
            area="source",
            kind="collection_gap",
            title=NO_PRODUCTION_SOURCE,
            subjects=[""],
            data={"reason": NO_PRODUCTION_SOURCE, "module": ""},
        )
    )


def parse_unshadowed(paths: Sequence[Path], *, root: Path, namespace: str) -> ParsedSources:
    """Parse the sources the import system can reach; a shadowed module is a named gap (#797)."""
    names: dict[Path, str] = {}
    for path in paths:
        with suppress(ValueError):
            names[path] = module_for(path, root=root, namespace=namespace)
    packages = {names[path] for path in names if path.name == "__init__.py"}
    shadowed = [path for path in names if path.name != "__init__.py" and names[path] in packages]
    parsed = parse_sources(
        [path for path in paths if path not in shadowed], root=root, namespace=namespace
    )
    gaps = [_shadowed_gap(root, path, names[path]) for path in shadowed]
    return replace(parsed, failures=[*parsed.failures, *gaps])


def _shadowed_gap(root: Path, path: Path, name: str) -> RawRecord:
    rel = path.relative_to(root).as_posix()
    message = f"module {name!r} is shadowed by the package of the same name and is never imported"
    return classified(
        item_id=stable_id("COVERAGE", rel, 1, _SHADOWED_KIND, message),
        evidence_class=EvidenceClass.UNKNOWN,
        area="analysis_coverage",
        kind=_SHADOWED_KIND,
        title=f"{rel}: module is shadowed by a package of the same name",
        subjects=[rel],
        data={"file": rel, "line": 1, "message": message},
    )
