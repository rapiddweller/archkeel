# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Turn the Dart files of the scan roots into libraries, import records and failures (AD-97).

Own imports are exactly `package:<namespace>/...` and relative URIs; every other `package:` URI
is external and `dart:` is the SDK. `.dart_tool/package_config.json` is deliberately not read:
it is ignored by Git, so the snapshots `check` materializes would resolve differently from the
working tree. A URI that cannot be resolved is a coverage failure for its file, whose edges are
then withheld entirely rather than published in part.
"""

from __future__ import annotations

import hashlib
import posixpath
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Final

from archkeel.ir.model import EvidenceClass, stable_id

from .dart_directives import Directive, Header, read_header
from .dart_lexer import DirectiveError
from .records import RawEvidence, RawRecord, classified
from .source import file_evidence, package_for, record_evidence

_SEGMENT: Final = r"[A-Za-z_][A-Za-z0-9_]*"
_SCHEME: Final = r"[A-Za-z][A-Za-z0-9+.-]*:.*"
# The top-level `name:` scalar of a pubspec: the one line a package's own imports hang on.
_PUBSPEC_NAME: Final = r"""name:\s*["']?([A-Za-z_][A-Za-z0-9_]*)["']?\s*(#.*)?"""


@dataclass(frozen=True, slots=True)
class DartLibrary:
    """A Dart library as the shared module and package records read it (`ScannedModule`)."""

    rel_path: str
    module: str
    package: str
    all_exports: frozenset[str] = frozenset()
    # AD-99: Dart has no `__all__`, so no export list is ever proven whole.
    all_literal: bool = False
    compatibility_logic_free: bool = False


@dataclass(frozen=True, slots=True)
class DartSources:
    """Everything one pass over the Dart files proves, and what it could not."""

    paths: tuple[Path, ...]
    libraries: tuple[DartLibrary, ...]
    imports: list[RawRecord]
    failures: list[RawRecord]
    evidence: list[RawEvidence]
    module_evidence: dict[str, str]
    blank_modules: frozenset[str]
    files_read: int
    files_parsed: int
    source_digest: str


@dataclass(frozen=True, slots=True)
class _File:
    rel_path: str
    module: str
    lines: tuple[str, ...]
    header: Header


def _failure(rel_path: str, line: int, kind: str, message: str) -> RawRecord:
    return classified(
        item_id=stable_id("COVERAGE", rel_path, line, kind, message),
        evidence_class=EvidenceClass.UNKNOWN,
        area="analysis_coverage",
        kind=kind,
        title=f"{rel_path}:{line} could not be analyzed: {message}",
        subjects=[f"{rel_path}:{line}"],
        data={"file": rel_path, "line": line, "message": message},
    )


def _identifier(segment: str, *, last: bool) -> str | None:
    """One URI path segment as an identifier: strip `.dart`, then `.` and `-` become `_`."""
    stem: str = segment.removesuffix(".dart") if last else segment
    name: str = re.sub(r"[.-]", "_", stem)
    return name if re.fullmatch(_SEGMENT, name) else None


def dotted(path: str) -> str | None:
    """Map a `/`-separated URI path to a dotted module id, or None if a segment cannot be one."""
    segments: list[str] = path.split("/")
    names = [
        _identifier(segment, last=index == len(segments) - 1)
        for index, segment in enumerate(segments)
    ]
    return ".".join(name for name in names if name) if all(names) else None


def _below(path: str, root: str) -> str | None:
    """`path` relative to the scan root `root`, or None when it lies outside it."""
    if root in (".", ""):
        return None if path == ".." or path.startswith("../") else path
    return path.removeprefix(f"{root}/") if path.startswith(f"{root}/") else None


def _excerpt(lines: tuple[str, ...], line: int) -> str:
    text: str = lines[line - 1] if 0 < line <= len(lines) else ""
    return text.rstrip()


def pubspec_failures(root: Path, namespace: str) -> list[RawRecord]:
    """Refuse a scan whose namespace is not the package's own pubspec name (A4).

    A wrong namespace would turn every own `package:` import into an external one and hide
    every edge. A snapshot without the file (`check` materializes only the scan roots) has
    nothing to compare, so it is not checked.
    """
    path: Path = root / "pubspec.yaml"
    if not path.is_file():
        return []
    try:
        text: str = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        return [_failure("pubspec.yaml", 1, "PubspecError", str(error))]
    for number, line in enumerate(text.splitlines(), start=1):
        found = re.fullmatch(_PUBSPEC_NAME, line)
        if found is not None and found[1] != namespace:
            message = (
                f"pubspec.yaml names the package {found[1]!r} but scan.namespace is "
                f"{namespace!r}; set scan.namespace to the pubspec name"
            )
            return [_failure("pubspec.yaml", number, "PubspecError", message)]
        if found is not None:
            return []
    return []


def dart_source_paths(root: Path, roots: tuple[str, ...]) -> tuple[Path, ...]:
    """Every `.dart` file under the scan roots; generated ones carry real imports too."""
    found: list[Path] = []
    for source in roots:
        directory: Path = root / source
        if directory.is_dir():
            found.extend(directory.rglob("*.dart"))
    # Every path shares `root`, so its full POSIX form orders exactly as its relative one.
    return tuple(sorted(found, key=PurePath.as_posix))


class _Reader:
    """One pass over the Dart files: read, map, resolve, and record what it proves."""

    def __init__(self, root: Path, roots: tuple[str, ...], namespace: str) -> None:
        self.root = root
        self.roots = roots
        self.namespace = namespace
        self.failures: list[RawRecord] = pubspec_failures(root, namespace)
        self.imports: list[RawRecord] = []
        self.evidence: dict[str, RawEvidence] = {}
        self.files: dict[str, _File] = {}
        self.blank: set[str] = set()
        self.digest = hashlib.sha256()
        self.read = 0
        self.parsed = 0

    def read_file(self, path: Path) -> _File | None:
        """Read, digest and parse one file; a failure names its file and line."""
        rel: str = path.relative_to(self.root).as_posix()
        try:
            raw = path.read_bytes()
            self.read += 1
            self.digest.update(rel.encode("utf-8") + b"\0" + raw + b"\0")
            text: str = str(raw, "utf-8")
            header = read_header(text)
        except (OSError, UnicodeDecodeError) as error:
            self.failures.append(_failure(rel, 1, error.__class__.__name__, str(error)))
            return None
        except DirectiveError as error:
            self.failures.append(_failure(rel, error.line, "DirectiveError", str(error)))
            return None
        self.parsed += 1
        below = next(found for root in self.roots if (found := _below(rel, root)) is not None)
        module = dotted(below)
        if module is None:
            message = "a path segment is not a Dart identifier"
            self.failures.append(_failure(rel, 1, "ModuleIdError", message))
            return None
        if not text.strip():
            self.blank.add(f"{self.namespace}.{module}")
        return _File(rel, f"{self.namespace}.{module}", tuple(text.splitlines()), header)

    def keep_unique(self, files: list[_File]) -> None:
        """Keep every file whose module id no other file maps to; each collision fails."""
        counts = Counter(item.module for item in files)
        for item in files:
            if counts[item.module] == 1:
                self.files[item.rel_path] = item
                continue
            names = ", ".join(other.rel_path for other in files if other.module == item.module)
            message = f"{item.module} is also {names}"
            self.failures.append(_failure(item.rel_path, 1, "ModuleIdCollision", message))

    def target_of(self, uri: str, importer: str) -> tuple[str, str | None]:
        """Return (module id, internal path or None), or raise `ValueError` naming why not."""
        if uri.startswith("dart:"):
            return _external("dart", uri.removeprefix("dart:"), uri)
        if uri.startswith("package:"):
            spec: str = uri.removeprefix("package:")
            name, _, rest = spec.partition("/")
            if name != self.namespace:
                return _external(name, rest, uri)
            candidates = [posixpath.normpath(f"{root}/{rest}") for root in self.roots]
            return self._internal(candidates, f"unresolved own import {uri!r}")
        if re.fullmatch(_SCHEME, uri) or uri.startswith("/"):
            raise ValueError(f"unsupported URI {uri!r}")
        target = posixpath.normpath(posixpath.join(posixpath.dirname(importer), uri))
        if all(_below(target, root) is None for root in self.roots):
            raise ValueError(f"relative URI {uri!r} leaves the scan roots")
        return self._internal([target], f"relative URI {uri!r} names no scanned file")

    def _internal(self, candidates: list[str], reason: str) -> tuple[str, str]:
        found = [self.files[path] for path in candidates if path in self.files]
        if len(found) != 1:
            raise ValueError(reason)
        return found[0].module, found[0].rel_path

    def owners(self) -> dict[str, str]:
        """Map every part file to the library that lists it; a part nobody lists fails."""
        owners: dict[str, str] = {}
        for library in [item for item in self.files.values() if item.header.part_of is None]:
            pending = [library]
            while pending:
                current = pending.pop()
                for part in current.header.parts:
                    path = self._part(part.uri, part.line, current, owners)
                    if path is not None:
                        owners[path] = library.module
                        pending.append(self.files[path])
        for item in self.files.values():
            if item.header.part_of is not None and item.rel_path not in owners:
                self.failures.append(_failure(item.rel_path, 1, "PartError", "no library lists it"))
        return owners

    def _part(self, uri: str, line: int, current: _File, owners: dict[str, str]) -> str | None:
        try:
            _, path = self.target_of(uri, current.rel_path)
        except ValueError as error:
            self.failures.append(_failure(current.rel_path, line, "PartError", str(error)))
            return None
        if path is None or self.files[path].header.part_of is None or path in owners:
            message = f"part {uri!r} is not a part file of exactly one library"
            self.failures.append(_failure(current.rel_path, line, "PartError", message))
            return None
        return path

    def record_imports(self, item: _File, source_module: str) -> None:
        """Every edge one file's directives prove, or its failures and none of its edges."""
        resolved: list[tuple[Directive, tuple[str, str | None]]] = []
        failures: list[RawRecord] = []
        for directive in item.header.directives:
            for uri in directive.uris:
                try:
                    target = self._library_target(uri, item.rel_path)
                except ValueError as error:
                    failures.append(
                        _failure(item.rel_path, directive.line, "ImportError", str(error))
                    )
                    continue
                # Two alternatives naming one library are one edge, not two records.
                if (directive, target) not in resolved:
                    resolved.append((directive, target))
        self.failures.extend(failures)
        for directive, target in resolved if not failures else ():
            position = (directive.line, directive.end_line, directive.column)
            excerpt = _excerpt(item.lines, directive.line)
            evidence_id = record_evidence(self.evidence, item.rel_path, position, excerpt)
            self.imports.extend(
                _import_record(item, source_module, directive, target, symbol, evidence_id)
                for symbol in (directive.shown or (None,))
            )

    def sources(self, paths: tuple[Path, ...]) -> DartSources:
        """Every library, and every edge its own file and its parts prove."""
        owners = self.owners()
        libraries: list[DartLibrary] = []
        module_evidence: dict[str, str] = {}
        for item in self.files.values():
            owner = item.module if item.header.part_of is None else owners.get(item.rel_path)
            if owner is None:
                continue
            if item.header.part_of is None:
                libraries.append(DartLibrary(item.rel_path, item.module, package_for(item.module)))
                module_evidence[item.module] = file_evidence(
                    self.evidence, item.rel_path, item.lines
                )
            # A part's own directives are dependencies of the library it belongs to.
            self.record_imports(item, owner)
        return DartSources(
            paths=paths,
            libraries=tuple(libraries),
            imports=sorted(self.imports, key=lambda record: record["id"]),
            failures=self.failures,
            evidence=sorted(self.evidence.values(), key=lambda item: item["id"]),
            module_evidence=module_evidence,
            blank_modules=frozenset(self.blank),
            files_read=self.read,
            files_parsed=self.parsed,
            source_digest=self.digest.hexdigest(),
        )

    def _library_target(self, uri: str, importer: str) -> tuple[str, str | None]:
        module, path = self.target_of(uri, importer)
        if path is not None and self.files[path].header.part_of is not None:
            raise ValueError(f"{uri!r} names a part file, not a library")
        return module, path


def _external(package: str, path: str, uri: str) -> tuple[str, None]:
    """`package:<package>/<path>` or `dart:<path>` as an external dotted module id."""
    module = dotted(f"{package}/{path}") if path else None
    if module is None:
        raise ValueError(f"unreadable URI {uri!r}")
    return module, None


def _top_level(module: str) -> str:
    return module.partition(".")[0]


def _import_record(
    item: _File,
    source_module: str,
    directive: Directive,
    target: tuple[str, str | None],
    symbol: str | None,
    evidence_id: str,
) -> RawRecord:
    module, internal = target
    binding = symbol or directive.prefix or module
    return classified(
        item_id=stable_id(
            "IMP", item.rel_path, directive.line, directive.column, module, symbol, binding
        ),
        evidence_class=EvidenceClass.FACT,
        area="dependencies",
        kind="import",
        title=f"Import {module}{'.' + symbol if symbol else ''}",
        subjects=[source_module, module],
        evidence_ids=[evidence_id],
        data={
            "source_module": source_module,
            "source_package": package_for(source_module),
            "target_module": module,
            "target_package": package_for(module) if internal else _top_level(module),
            "symbol": symbol,
            "binding": binding,
            "relative_level": 0,
            "under_type_checking": False,
            "reexport": directive.kind == "export",
            "symbols_known": symbol is not None,
        },
    )


def read_dart_sources(root: Path, *, roots: tuple[str, ...], namespace: str) -> DartSources:
    """Read every Dart file of the scan roots into libraries, imports and coverage failures."""
    paths = dart_source_paths(root, roots)
    reader = _Reader(root, roots, namespace)
    reader.keep_unique([item for path in paths if (item := reader.read_file(path)) is not None])
    return reader.sources(paths)
