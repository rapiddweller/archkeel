# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Resolve module specifiers to snapshot files, never to a guess.

Each rule below is a transcription of what the TypeScript compiler does for the case it covers.
A specifier or setting outside those rules is `Unknown` with its reason: a resolver that is more
permissive than the compiler would turn an unresolvable import into a proven dependency.
"""

from __future__ import annotations

import json
import posixpath
import re
from dataclasses import dataclass
from typing import Final, Literal

from .config import Config, Json, Snapshot, decode, join

Format = Literal["esm", "cjs"]
Kinds = tuple[str, ...]
# `module.builtinModules` of Node 22, plus the names that exist only with the `node:` prefix.
_BUILTINS: Final = frozenset(
    "_http_agent _http_client _http_common _http_incoming _http_outgoing _http_server "
    "_stream_duplex _stream_passthrough _stream_readable _stream_transform _stream_wrap "
    "_stream_writable _tls_common _tls_wrap assert assert/strict async_hooks buffer "
    "child_process cluster console constants crypto dgram diagnostics_channel dns "
    "dns/promises domain events fs fs/promises http http2 https inspector inspector/promises "
    "module net os path path/posix path/win32 perf_hooks process punycode querystring readline "
    "readline/promises repl stream stream/consumers stream/promises stream/web string_decoder "
    "sys timers timers/promises tls trace_events tty url util util/types v8 vm wasi "
    "worker_threads zlib".split()
)
_SCHEME_ONLY: Final = frozenset({"sea", "sqlite", "test", "test/reporters"})
# The compiler removes the first of these that ends a path before it adds its own extension.
_KNOWN_EXTENSIONS: Final = (
    ".d.ts",
    ".d.mts",
    ".d.cts",
    ".mjs",
    ".mts",
    ".cjs",
    ".cts",
    ".ts",
    ".js",
    ".tsx",
    ".jsx",
    ".json",
)
_ESM_EXTENSIONS: Final = (".mts", ".mjs", ".d.mts")
_CJS_EXTENSIONS: Final = (".cts", ".cjs", ".d.cts")
_SCOPE_FORMATS: Final = (".ts", ".tsx", ".js", ".jsx", ".d.ts")
_RELATIVE: Final = re.compile(r"\.\.?(?:/|\Z)")
_KIND_OF: Final = {
    ".d.ts": "dts",
    ".d.mts": "dts",
    ".d.cts": "dts",
    ".ts": "ts",
    ".tsx": "ts",
    ".mts": "ts",
    ".cts": "ts",
    ".js": "js",
    ".jsx": "js",
    ".mjs": "js",
    ".cjs": "js",
}


@dataclass(frozen=True, slots=True)
class Unknown:
    reason: str


@dataclass(frozen=True, slots=True)
class Found:
    path: str
    # Reached through a `node_modules` search, so it is a dependency wherever the file lives.
    external: bool
    # A directory's package.json decided the file; Node may load another one than the compiler.
    directory_package: bool


def is_builtin(specifier: str) -> bool:
    name = specifier.removeprefix("node:")
    if specifier.startswith("node:"):
        return name in _BUILTINS or name in _SCHEME_ONLY
    return name in _BUILTINS


def is_relative(specifier: str) -> bool:
    return _RELATIVE.match(specifier) is not None


def package_name(specifier: str) -> str:
    parts = specifier.split("/")
    return "/".join(parts[:2]) if specifier.startswith("@") else parts[0]


def _declares_exports(manifest: Json) -> bool:
    """Whether `exports` is truthy in JavaScript, where an empty object still counts."""
    return manifest.get("exports") not in (None, False, 0, "")


def _best_pattern(
    patterns: tuple[tuple[str, tuple[str, ...]], ...], specifier: str
) -> tuple[str, tuple[str, ...]] | None:
    """The exact `paths` key, else the pattern with the longest prefix; its star match."""
    best: tuple[int, str, tuple[str, ...]] | None = None
    for pattern, targets in patterns:
        if pattern == specifier:
            return "", targets
        prefix, star, suffix = pattern.partition("*")
        fits = star and len(specifier) >= len(prefix) + len(suffix)
        if fits and specifier.startswith(prefix) and specifier.endswith(suffix):
            if best is None or len(prefix) > best[0]:
                best = (len(prefix), specifier[len(prefix) : len(specifier) - len(suffix)], targets)
    return None if best is None else (best[1], best[2])


def _typed_name(specifier: str) -> str:
    """The DefinitelyTyped directory of a package: `@scope/name` is stored as `scope__name`."""
    if specifier.startswith("@") and "/" in specifier:
        return specifier.replace("/", "__", 1)[1:]
    return specifier


def _strip_extension(candidate: str) -> tuple[str, str] | None:
    """Split a name into stem and extension the way the compiler does; None without a dot."""
    if "." not in posixpath.basename(candidate):
        return None
    known = next((ext for ext in _KNOWN_EXTENSIONS if candidate.endswith(ext)), None)
    stem = candidate[: -len(known)] if known else candidate[: candidate.rindex(".")]
    return stem, candidate[len(stem) :]


def _extensions(original: str, kinds: Kinds) -> list[str]:
    """The extensions tried after `original`, in the compiler's order, for the enabled kinds."""
    ts, dts, js = "ts" in kinds, "dts" in kinds, "js" in kinds
    if original in (".mjs", ".mts", ".d.mts"):
        groups = [(ts, ".mts"), (dts, ".d.mts"), (js, ".mjs")]
    elif original in (".cjs", ".cts", ".d.cts"):
        groups = [(ts, ".cts"), (dts, ".d.cts"), (js, ".cjs")]
    elif original in (".tsx", ".jsx"):
        groups = [(ts, ".tsx"), (ts, ".ts"), (dts, ".d.ts"), (js, ".jsx"), (js, ".js")]
    elif original == ".json":
        groups = [(dts, ".d.json.ts"), ("json" in kinds, ".json")]
    elif original in (".ts", ".d.ts", ".js", ""):
        groups = [(ts, ".ts"), (ts, ".tsx"), (dts, ".d.ts"), (js, ".js"), (js, ".jsx")]
    else:
        groups = []
    return [extension for enabled, extension in groups if enabled]


def _file_paths(candidate: str, esm: bool, kinds: Kinds) -> list[str]:
    """Files a name may stand for: its extension swapped (`./a.js` for `a.ts`), then appended."""
    paths: list[str] = []
    split = _strip_extension(candidate)
    if split is not None:
        paths.extend(f"{split[0]}{extension}" for extension in _extensions(split[1], kinds))
    # ECMAScript modules never infer an extension.
    if not esm:
        paths.extend(f"{candidate}{extension}" for extension in _extensions("", kinds))
    return paths


def _ancestors(rel: str) -> list[str]:
    """Directories from the one holding `rel` up to the snapshot root."""
    chain = [posixpath.dirname(rel) or "."]
    while chain[-1] != ".":
        chain.append(posixpath.dirname(chain[-1]) or ".")
    return chain


class Resolver:
    def __init__(self, snapshot: Snapshot, config: Config) -> None:
        self.snapshot = snapshot
        self.options = config.options
        self.partial = config.partial
        self._reads: set[str] = set()

    @property
    def _exports_aware(self) -> bool:
        return self.options.resolution in ("node16", "nodenext", "bundler")

    def blocked(self) -> Unknown | None:
        """A reason nothing can be resolved, when the settings in force are not all understood."""
        if self.partial:
            return Unknown("TSConfig settings are not fully observed")
        if self.options.unmodeled:
            return Unknown(f"Compiler option is not observed: {', '.join(self.options.unmodeled)}")
        if self.options.resolution not in ("node10", "node16", "nodenext", "bundler"):
            return Unknown(f"moduleResolution {self.options.resolution} is not observed")
        return None

    def _manifest(self, directory: str) -> Json | Unknown | None:
        manifest = join(directory, "package.json")
        raw = self.snapshot.read(manifest)
        if raw is None:
            return None
        self._reads.add(manifest)
        try:
            value = json.loads(decode(raw))
        except ValueError:
            return Unknown(f"Package metadata is not valid JSON: {manifest}")
        return (
            value
            if isinstance(value, dict)
            else Unknown(f"Package metadata is not an object: {manifest}")
        )

    def scope(self, rel: str) -> Json | Unknown | None:
        """The nearest package.json above a file, searched up to the filesystem root."""
        chain = [
            *_ancestors(rel),
            *("/".join([".."] * level) for level in range(1, self.snapshot.depth + 1)),
        ]
        for current in chain:
            if posixpath.basename(current) != "node_modules":
                manifest = self._manifest(current)
                if manifest is not None:
                    return manifest
        return None

    def format_of(self, rel: str) -> Format | Unknown | None:
        """Whether Node loads a file as ESM or CommonJS; None where no format is defined."""
        if self.options.resolution not in ("node16", "nodenext"):
            return None
        if rel.endswith(_ESM_EXTENSIONS):
            return "esm"
        if rel.endswith(_CJS_EXTENSIONS):
            return "cjs"
        if not rel.endswith(_SCOPE_FORMATS):
            return None
        manifest = self.scope(rel)
        if isinstance(manifest, Unknown):
            return manifest
        return "esm" if manifest is not None and manifest.get("type") == "module" else "cjs"

    def resolve(self, specifier: str, importer: str, mode: Format | None) -> Found | Unknown | None:
        """The snapshot file `specifier` names, None when it names none, else why not known."""
        self._reads = set()
        esm = mode == "esm"
        node10 = self.options.resolution == "node10"
        # Under Node10 the compiler looks for TypeScript everywhere before it looks for JavaScript.
        # JSON modules are tried with the JavaScript files, which come last.
        last = ("js", "json") if self.options.resolve_json else ("js",)
        passes: tuple[Kinds, ...] = (("ts", "dts"), last) if node10 else (("ts", "dts", *last),)
        if is_relative(specifier):
            candidate = join(posixpath.dirname(importer) or ".", specifier)
            for kinds in passes:
                found = self._by_name(candidate, specifier.endswith("/"), esm, kinds, True)
                if found is not None:
                    return self._found(found, False, candidate)
            return None
        if posixpath.isabs(specifier):
            return Unknown(f"Absolute specifiers are not observed: {specifier}")
        for kinds in passes:
            mapped = self._mapped(specifier, esm, kinds)
            if mapped is not None:
                return self._found(mapped, False, None)
            # The project's own names come first, then `imports`, then the package itself.
            if self._exports_aware and specifier.startswith("#"):
                return Unknown(f"Package imports are not observed: {specifier}")
            if self._exports_aware and self._self_reference(importer, package_name(specifier)):
                return Unknown(f"Package self-reference is not observed: {specifier}")
            for directory in _ancestors(importer):
                found = self._modules(directory, specifier, esm, kinds)
                if found is not None:
                    return self._found(found, True, None)
        return None

    def _mapped(self, specifier: str, esm: bool, kinds: Kinds) -> str | Unknown | None:
        """`paths`, then `baseUrl`: the project's own names for modules, tried before packages."""
        match = _best_pattern(self.options.paths, specifier)
        if match is not None:
            star, targets = match
            for target in targets:
                if posixpath.isabs(target):
                    return Unknown(f"Absolute paths targets are not observed: {specifier}")
                # The compiler substitutes only a non-empty match and keeps the text otherwise.
                candidate = join(
                    self.options.paths_base, target.replace("*", star, 1) if star else target
                )
                # A target that names its extension is a file, not a name to complete.
                if target.endswith(_KNOWN_EXTENSIONS) and self.snapshot.is_file(candidate):
                    return candidate
                found = self._by_name(candidate, False, esm, kinds, True)
                if found is not None:
                    return found
        if self.options.base_url is not None:
            return self._by_name(join(self.options.base_url, specifier), False, esm, kinds, True)
        return None

    def _found(self, found: str | Unknown, external: bool, lookup: str | None) -> Found | Unknown:
        if isinstance(found, Unknown):
            return found
        read = lookup is not None and join(lookup, "package.json") in self._reads
        directory = read and lookup is not None and self.snapshot.is_dir(lookup)
        return Found(self.snapshot.real(found) or found, external, directory)

    def _self_reference(self, importer: str, name: str) -> bool:
        manifest = self.scope(importer)
        return (
            isinstance(manifest, dict)
            and manifest.get("name") == name
            and _declares_exports(manifest)
        )

    def _modules(
        self, directory: str, specifier: str, esm: bool, kinds: Kinds
    ) -> str | Unknown | None:
        modules = join(directory, "node_modules")
        if not self.snapshot.is_dir(modules):
            return None
        found = self._package(modules, specifier, esm, kinds)
        types = join(modules, "@types")
        if found is not None or "dts" not in kinds or not self.snapshot.is_dir(types):
            return found
        return self._package(types, _typed_name(specifier), esm, ("dts",))

    def _package(
        self, modules: str, specifier: str, esm: bool, kinds: Kinds
    ) -> str | Unknown | None:
        name = package_name(specifier)
        rest = specifier[len(name) + 1 :]
        root = self._manifest(join(modules, name))
        if isinstance(root, Unknown):
            return root
        if root is not None and "typesVersions" in root:
            return Unknown(f"Package typesVersions are not observed: {name}")
        if root is not None and self._exports_aware and _declares_exports(root):
            return Unknown(f"Package exports are not observed: {specifier}")
        candidate = join(modules, specifier)
        # An ECMAScript import of the package root never infers an extension.
        file = self._file(candidate, esm, kinds) if rest or not esm else None
        if file is not None or not self.snapshot.is_dir(candidate):
            return file
        nested = self._manifest(candidate) if rest else None
        if isinstance(nested, Unknown):
            return nested
        found = self._worker(candidate, nested or root, esm, kinds)
        defaulted = esm and not rest and root is not None and not _declares_exports(root)
        if found is None and defaulted:
            return self._file(join(candidate, "index.js"), esm, kinds)
        return found

    def _by_name(
        self, candidate: str, directory_only: bool, esm: bool, kinds: Kinds, package: bool
    ) -> str | Unknown | None:
        found = None if directory_only else self._file(candidate, esm, kinds)
        # ECMAScript modules never import a directory.
        if found is not None or esm or not self.snapshot.is_dir(candidate):
            return found
        manifest = self._manifest(candidate) if package else None
        if isinstance(manifest, Unknown):
            return manifest
        return self._worker(candidate, manifest, esm, kinds)

    def _file(self, candidate: str, esm: bool, kinds: Kinds) -> str | None:
        paths = _file_paths(candidate, esm, kinds)
        return next((path for path in paths if self.snapshot.is_file(path)), None)

    def _worker(
        self, directory: str, manifest: Json | None, esm: bool, kinds: Kinds
    ) -> str | Unknown | None:
        """A package directory: the file `types` or `main` names, else its `index`."""
        fields = {} if manifest is None else manifest
        if "typesVersions" in fields:
            return Unknown(f"Package typesVersions are not observed: {directory}")
        keys = [*(("typings", "types") if "dts" in kinds else ()), "main"]
        named = next(
            (value for key in keys if isinstance(value := fields.get(key), str) and value), None
        )
        if named is not None:
            target = join(directory, named)
            extension = next((ext for ext in _KNOWN_EXTENSIONS if target.endswith(ext)), "")
            if _KIND_OF.get(extension) in kinds and self.snapshot.is_file(target):
                return target
            # A package that is not itself ECMAScript may name a file without its extension.
            strict = esm and fields.get("type") == "module"
            expanded = ("ts", "dts") if kinds == ("dts",) else kinds
            found = self._by_name(target, False, strict, expanded, False)
            if found is not None:
                return found
        return self._file(join(directory, "index"), esm, kinds)
