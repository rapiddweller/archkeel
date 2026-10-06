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

from .config import Config, Snapshot, join

Format = Literal["esm", "cjs"]
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


@dataclass(frozen=True, slots=True)
class Unknown:
    reason: str


def is_builtin(specifier: str) -> bool:
    name = specifier.removeprefix("node:")
    if specifier.startswith("node:"):
        return name in _BUILTINS or name in _SCHEME_ONLY
    return name in _BUILTINS


def is_relative(specifier: str) -> bool:
    return _RELATIVE.match(specifier) is not None


@dataclass(frozen=True, slots=True)
class Resolver:
    snapshot: Snapshot
    config: Config

    def blocked(self) -> Unknown | None:
        """A reason nothing can be resolved, when the settings in force are not all understood."""
        options = self.config.options
        if self.config.partial:
            return Unknown("TSConfig settings are not fully observed")
        if options.unmodeled:
            return Unknown(f"Compiler option is not observed: {', '.join(options.unmodeled)}")
        if options.resolution not in ("node10", "node16", "nodenext", "bundler"):
            return Unknown(f"moduleResolution {options.resolution} is not observed")
        return None

    def format_of(self, rel: str) -> Format | Unknown | None:
        """Whether Node loads a file as ESM or CommonJS; None where no format is defined."""
        if self.config.options.resolution not in ("node16", "nodenext"):
            return None
        if rel.endswith(_ESM_EXTENSIONS):
            return "esm"
        if rel.endswith(_CJS_EXTENSIONS):
            return "cjs"
        if not rel.endswith(_SCOPE_FORMATS):
            return None
        return self._scope_type(posixpath.dirname(rel) or ".")

    def _scope_type(self, directory: str) -> Format | Unknown:
        """The `type` of the nearest package.json, searched up to the filesystem root."""
        chain = [directory]
        while chain[-1] != ".":
            chain.append(posixpath.dirname(chain[-1]) or ".")
        chain.extend("/".join([".."] * level) for level in range(1, self.snapshot.depth + 1))
        for current in chain:
            if posixpath.basename(current) == "node_modules":
                continue
            manifest = join(current, "package.json")
            raw = self.snapshot.read(manifest)
            if raw is not None:
                return _package_type(raw, manifest)
        return "cjs"

    def resolve(self, specifier: str, importer: str, mode: Format | None) -> str | Unknown | None:
        """The snapshot file `specifier` names, None when it names none, else why not known."""
        if not is_relative(specifier):
            return Unknown(f"Package and alias specifiers are not observed: {specifier}")
        esm = mode == "esm"
        candidate = join(posixpath.dirname(importer) or ".", specifier)
        passes = (
            (("ts", "dts"), ("js",))
            if self.config.options.resolution == "node10"
            else (("ts", "dts", "js"),)
        )
        for kinds in passes:
            found = self._load(candidate, specifier.endswith("/"), esm, kinds)
            if found is not None:
                return found
        return None

    def _load(
        self, candidate: str, directory_only: bool, esm: bool, kinds: tuple[str, ...]
    ) -> str | Unknown | None:
        if not directory_only:
            for path in _file_paths(candidate, esm, kinds):
                if self.snapshot.is_file(path):
                    return self._real(path)
        if esm or not self.snapshot.is_dir(candidate):
            return None
        if self.snapshot.read(join(candidate, "package.json")) is not None:
            return Unknown(f"Package metadata of a local directory is not observed: {candidate}")
        for path in _file_paths(join(candidate, "index"), esm, kinds):
            if self.snapshot.is_file(path):
                return self._real(path)
        return None

    def _real(self, path: str) -> str:
        return self.snapshot.real(path) or path


def _package_type(raw: bytes, manifest: str) -> Format | Unknown:
    try:
        value = json.loads(str(raw, "utf-8", "replace").lstrip("﻿"))
    except ValueError:
        return Unknown(f"Package metadata is not valid JSON: {manifest}")
    return "esm" if isinstance(value, dict) and value.get("type") == "module" else "cjs"


def _strip_extension(candidate: str) -> tuple[str, str] | None:
    """Split a name into stem and extension the way the compiler does; None without a dot."""
    name = posixpath.basename(candidate)
    if "." not in name:
        return None
    known = next((ext for ext in _KNOWN_EXTENSIONS if candidate.endswith(ext)), None)
    stem = candidate[: -len(known)] if known else candidate[: candidate.rindex(".")]
    return stem, candidate[len(stem) :]


def _extensions(original: str, kinds: tuple[str, ...]) -> list[str]:
    """The extensions tried after `original`, in the compiler's order, for the enabled kinds."""
    ts, dts, js = "ts" in kinds, "dts" in kinds, "js" in kinds
    if original in (".mjs", ".mts", ".d.mts"):
        groups = [(ts, ".mts"), (dts, ".d.mts"), (js, ".mjs")]
    elif original in (".cjs", ".cts", ".d.cts"):
        groups = [(ts, ".cts"), (dts, ".d.cts"), (js, ".cjs")]
    elif original in (".tsx", ".jsx"):
        groups = [(ts, ".tsx"), (ts, ".ts"), (dts, ".d.ts"), (js, ".jsx"), (js, ".js")]
    elif original in (".ts", ".d.ts", ".js", ""):
        groups = [(ts, ".ts"), (ts, ".tsx"), (dts, ".d.ts"), (js, ".js"), (js, ".jsx")]
    else:
        groups = []
    return [extension for enabled, extension in groups if enabled]


def _file_paths(candidate: str, esm: bool, kinds: tuple[str, ...]) -> list[str]:
    """Files a name may stand for: its extension swapped (`./a.js` for `a.ts`), then appended."""
    paths: list[str] = []
    split = _strip_extension(candidate)
    if split is not None:
        paths.extend(f"{split[0]}{extension}" for extension in _extensions(split[1], kinds))
    # ECMAScript modules never infer an extension.
    if not esm:
        paths.extend(f"{candidate}{extension}" for extension in _extensions("", kinds))
    return paths
