# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Read the snapshot and its TSConfig, and name every compiler setting this reader does not model.

A file read here is digested as a resolution input, so a verdict is bound to the bytes that
decided it. A path that leaves the snapshot, by name or by symlink, is never read.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal

Role = Literal["selected", "resolution"]
Json = dict[str, object]

OUTSIDE: Final = "Resolver input outside snapshot"
SYMLINK: Final = "Resolver symlink outside snapshot"
# Settings that change which file a specifier names and that no resolver here applies.
_UNMODELED: Final = (
    "rootDirs",
    "moduleSuffixes",
    "customConditions",
    "resolvePackageJsonExports",
    "resolvePackageJsonImports",
    "preserveSymlinks",
    "allowArbitraryExtensions",
    "noDtsResolution",
)
_ENUMS: Final = {
    "module": "none commonjs amd system umd es6 es2015 es2020 es2022 esnext node16 node18 "
    "node20 nodenext preserve".split(),
    "moduleResolution": "node10 node classic node16 nodenext bundler".split(),
    "target": "es3 es5 es6 es2015 es2016 es2017 es2018 es2019 es2020 es2021 es2022 es2023 "
    "es2024 esnext".split(),
}
# The compiler's option names (TypeScript 5.9.3); an unknown one is a configuration error.
_KNOWN_OPTIONS: Final = frozenset(
    "all allowArbitraryExtensions allowImportingTsExtensions allowJs allowSyntheticDefaultImports "
    "allowUmdGlobalAccess allowUnreachableCode allowUnusedLabels alwaysStrict "
    "assumeChangesOnlyAffectDirectDependencies baseUrl charset checkJs composite customConditions "
    "declaration declarationDir declarationMap diagnostics disableReferencedProjectLoad "
    "disableSizeLimit disableSolutionSearching disableSourceOfProjectReferenceRedirect "
    "downlevelIteration emitBOM emitDeclarationOnly emitDecoratorMetadata erasableSyntaxOnly "
    "esModuleInterop exactOptionalPropertyTypes experimentalDecorators explainFiles "
    "extendedDiagnostics forceConsistentCasingInFileNames generateCpuProfile generateTrace "
    "ignoreDeprecations importHelpers importsNotUsedAsValues incremental init inlineSourceMap "
    "inlineSources isolatedDeclarations isolatedModules jsx jsxFactory jsxFragmentFactory "
    "jsxImportSource keyofStringsOnly lib libReplacement listEmittedFiles listFiles mapRoot "
    "maxNodeModuleJsDepth module moduleDetection moduleResolution moduleSuffixes newLine noCheck "
    "noEmit noEmitHelpers noEmitOnError noErrorTruncation noFallthroughCasesInSwitch noImplicitAny "
    "noImplicitOverride noImplicitReturns noImplicitThis noImplicitUseStrict noLib "
    "noPropertyAccessFromIndexSignature noResolve noStrictGenericChecks noUncheckedIndexedAccess "
    "noUncheckedSideEffectImports noUnusedLocals noUnusedParameters out outDir outFile paths "
    "plugins preserveConstEnums preserveSymlinks preserveValueImports preserveWatchOutput pretty "
    "project reactNamespace removeComments resolveJsonModule resolvePackageJsonExports "
    "resolvePackageJsonImports rewriteRelativeImportExtensions rootDir rootDirs "
    "skipDefaultLibCheck "
    "skipLibCheck sourceMap sourceRoot strict strictBindCallApply strictBuiltinIteratorReturn "
    "strictFunctionTypes strictNullChecks strictPropertyInitialization stripInternal "
    "suppressExcessPropertyErrors suppressImplicitAnyIndexErrors target traceResolution "
    "tsBuildInfoFile typeRoots types useDefineForClassFields useUnknownInCatchVariables "
    "verbatimModuleSyntax version".split()
)
_ESM_MODULES: Final = frozenset({"es6", "es2015", "es2020", "es2022", "esnext"})
_NODE16_MODULES: Final = frozenset({"node16", "node18", "node20"})
_RESOLUTIONS: Final = {"node": "node10", "node10": "node10", "node16": "node16"}
_SUPPORTED: Final = (".ts", ".tsx", ".d.ts", ".cts", ".d.cts", ".mts", ".d.mts")
_SUPPORTED_JS: Final = (".js", ".jsx", ".cjs", ".mjs")
# Files of one group shadow each other: `a.ts` wins over `a.tsx`, `a.d.ts`, `a.js` and `a.jsx`.
_PRIORITY: Final = (
    (".ts", ".tsx", ".d.ts", ".js", ".jsx"),
    (".cts", ".d.cts", ".cjs"),
    (".mts", ".d.mts", ".mjs"),
)
# A string is captured so that a comment or a comma inside it survives.
_STRINGS: Final = r'("(?:[^"\\]|\\.)*")|//[^\n]*|/\*[\s\S]*?\*/'
_TRAILING_COMMA: Final = r'("(?:[^"\\]|\\.)*")|,(?=\s*[}\]])'
_NOT_EXCLUDED: Final = r"(?!(?:node_modules|bower_components|jspm_packages)(?:/|\Z))"
_DEEP: Final = rf"(?:/{_NOT_EXCLUDED}[^/.][^/]*)*?"
# Per usage: the text a lone `*` stands for and the text `**` stands for.
_WILDCARDS: Final = {
    "files": (r"(?:[^./]|(?:\.(?!min\.js\Z))?)*", _DEEP),
    "directories": (r"[^/]*", _DEEP),
    "exclude": (r"[^/]*", r"(?:/.+?)?"),
}


@dataclass(frozen=True, slots=True)
class Options:
    """The compiler settings a resolver reads; explicit values only, as the compiler keeps them."""

    module: str | None = None
    module_resolution: str | None = None
    target: str | None = None
    allow_js: bool = False
    # Snapshot-relative directory of `baseUrl`, the `paths` patterns with their targets, and the
    # directory those targets are relative to: `baseUrl`, else the TSConfig that sets them.
    base_url: str | None = None
    paths: tuple[tuple[str, tuple[str, ...]], ...] = ()
    paths_base: str = "."
    unmodeled: tuple[str, ...] = ()
    json_modules: bool | None = None

    @property
    def resolve_json(self) -> bool:
        """Whether `.json` files resolve: set explicitly, else on for NodeNext and Bundler."""
        if self.json_modules is not None:
            return self.json_modules
        return self.emit_module in ("node20", "nodenext") or self.resolution == "bundler"

    @property
    def emit_module(self) -> str:
        """`module` after the compiler's default, which follows `target`."""
        if self.module is not None:
            return self.module
        return "commonjs" if self.target in (None, "es3", "es5") else "es2015"

    @property
    def resolution(self) -> str:
        """The resolution kind in force: the explicit one, else the one `module` implies."""
        if self.module_resolution is not None:
            return self.module_resolution
        implied = {"commonjs": "node10", "nodenext": "nodenext", "preserve": "bundler"}
        return (
            "node16"
            if self.emit_module in _NODE16_MODULES
            else implied.get(self.emit_module, "classic")
        )


@dataclass(frozen=True, slots=True)
class Config:
    options: Options
    # Snapshot-relative files the TSConfig selects, filtered to the requested source roots.
    files: tuple[str, ...]
    # True when a setting that changes resolution could not be read, so no result is trusted.
    partial: bool


def join(base: str, path: str) -> str:
    return posixpath.normpath(posixpath.join(base, path))


def is_outside(rel: str) -> bool:
    return rel == ".." or rel.startswith("../")


def within(scope: str, path: str) -> bool:
    return scope == "." or path == scope or path.startswith(f"{scope}/")


class Snapshot:
    """Every read of the snapshot goes through here: contained, digested, never executed."""

    def __init__(self, root: str) -> None:
        self.root = os.path.realpath(root)
        # Directories above the root, which the format lookup must also cover.
        self.depth = len(self.root.split(os.sep)) - 1
        self.inputs: dict[str, tuple[str, Role]] = {}
        self.problems: set[str] = set()

    def _absolute(self, rel: str) -> str:
        return os.path.normpath(os.path.join(self.root, *rel.split("/")))

    def _contained(self, absolute: str) -> str | None:
        """The snapshot-relative POSIX path of `absolute`, or None when it is outside."""
        relative: str = os.path.relpath(absolute, self.root)
        rel: str = relative.replace(os.sep, "/")
        return None if is_outside(rel) or os.path.isabs(rel) else rel

    def real(self, rel: str) -> str | None:
        """The real relative path of an existing entry; None when absent or escaping."""
        if is_outside(rel):
            return None
        real = os.path.realpath(self._absolute(rel))
        if not os.path.lexists(real):
            return None
        inside = self._contained(real)
        if inside is None:
            self.problems.add(SYMLINK)
        return inside

    def is_file(self, rel: str) -> bool:
        if is_outside(rel):
            if os.path.exists(self._absolute(rel)):
                self.problems.add(OUTSIDE)
            return False
        real = self.real(rel)
        return real is not None and os.path.isfile(self._absolute(real))

    def is_dir(self, rel: str) -> bool:
        real = self.real(rel)
        return real is not None and os.path.isdir(self._absolute(real))

    def read(self, rel: str) -> bytes | None:
        if not self.is_file(rel):
            return None
        try:
            with open(self._absolute(rel), "rb") as handle:
                raw = handle.read()
        except OSError:
            self.problems.add(f"Unreadable resolver input: {rel}")
            return None
        role = self.inputs[rel][1] if rel in self.inputs else "resolution"
        self.inputs[rel] = (hashlib.sha256(raw).hexdigest(), role)
        return raw

    def select(self, rel: str) -> None:
        self.inputs[rel] = (self.inputs[rel][0], "selected")

    def entries(self, rel: str) -> tuple[list[str], list[str]]:
        """Sorted file and directory names; symlinks are followed only inside the snapshot."""
        files: list[str] = []
        directories: list[str] = []
        real = self.real(rel)
        if real is None:
            return files, directories
        for name in sorted(os.listdir(self._absolute(real))):
            child = join(rel, name)
            if self.is_dir(child):
                directories.append(name)
            elif self.is_file(child):
                files.append(name)
        return files, directories

    def installed(self, rel: str) -> bool:
        real: str = self.real(rel) or rel
        return "node_modules" in real.split("/")


def decode(raw: bytes) -> str:
    """A JSON file's text without its byte order mark, as the compiler reads it."""
    text: str = str(raw, "utf-8", "replace")
    return text.lstrip("\ufeff")


def _strip(text: str) -> str:
    """Remove JSONC comments and trailing commas, which the compiler's reader accepts."""
    plain = re.sub(_STRINGS, lambda found: found[1] or " ", text)
    return re.sub(_TRAILING_COMMA, lambda found: found[1] or "", plain)


def _read_json(snapshot: Snapshot, rel: str) -> tuple[Json | None, str | None]:
    raw = snapshot.read(rel)
    if raw is None:
        return None, f"Cannot read file '{rel}'."
    try:
        value = json.loads(_strip(decode(raw)))
    except ValueError:
        return None, f"Cannot parse '{rel}' as JSON."
    return (value, None) if isinstance(value, dict) else (None, f"'{rel}' is not an object.")


@dataclass(frozen=True, slots=True)
class _Layer:
    """One TSConfig with what it inherits, its paths made relative to the snapshot root."""

    compiler: dict[str, object]
    base_url: str | None
    paths_directory: str
    # `files`, `include` and `exclude` of the nearest config that sets each.
    specs: dict[str, list[str]]
    # The `outDir` and `declarationDir` of the config being read, which exclude by default.
    outputs: list[str]
    partial: bool


def _overlay(low: _Layer, high: _Layer) -> _Layer:
    """`high` wins key by key; `paths` carries the directory of the config that set it."""
    return _Layer(
        {**low.compiler, **high.compiler},
        high.base_url if high.base_url is not None else low.base_url,
        high.paths_directory if "paths" in high.compiler else low.paths_directory,
        {**low.specs, **high.specs},
        high.outputs,
        low.partial or high.partial,
    )


def _slashes(spec: str) -> str:
    """Config specs may use backslashes, which the compiler reads as separators."""
    return spec.replace("\\", "/")


def _under(value: str, directory: str, final: str) -> str:
    """A spec of a config in `directory`; `${configDir}` is the directory of the root config."""
    marker = "${configDir}"
    if value.startswith(marker):
        tail: str = value[len(marker) :]
        return join(final, tail.lstrip("/") or ".")
    return join(directory, value)


def _extended(snapshot: Snapshot, entry: str, directory: str, problems: list[str]) -> str | None:
    """The TSConfig file an `extends` entry names; a package is not looked up."""
    named = _slashes(entry)
    if not named.startswith(("./", "../")):
        problems.append(f"TSConfig extends through a package is not observed: {named}")
        return None
    path: str = join(directory, named)
    if not snapshot.is_file(path) and not path.endswith(".json"):
        path = f"{path}.json"
    if snapshot.is_file(path):
        return path
    problems.append(f"File '{named}' not found.")
    return None


def _layer(
    snapshot: Snapshot, rel: str, final: str, problems: list[str], stack: list[str]
) -> _Layer:
    raw, error = _read_json(snapshot, rel)
    directory = posixpath.dirname(rel) or "."
    if raw is None:
        problems.append(error or f"Cannot read file '{rel}'.")
        return _Layer({}, None, directory, {}, [], True)
    declared = raw.get("compilerOptions")
    compiler = dict(declared) if isinstance(declared, dict) else {}
    problems.extend(_invalid(compiler))
    partial = False
    specs: dict[str, list[str]] = {}
    for key in ("files", "include", "exclude"):
        value = raw.get(key)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            items = [_slashes(item) for item in value]
            partial = partial or any(posixpath.isabs(item) for item in items)
            specs[key] = [
                _under(item, directory, final) for item in items if not posixpath.isabs(item)
            ]
        elif value is not None:
            problems.append(f"Compiler option 5024: '{key}' must be a list of strings.")
    base_url = compiler.get("baseUrl")
    outputs = [
        _under(str(compiler[name]), directory, final)
        for name in ("outDir", "declarationDir")
        if isinstance(compiler.get(name), str) and compiler[name]
    ]
    own = _Layer(
        compiler,
        _under(base_url, directory, final) if isinstance(base_url, str) else None,
        directory,
        specs,
        outputs,
        partial,
    )
    parents = raw.get("extends")
    entries = parents if isinstance(parents, list) else [] if parents is None else [parents]
    inherited = _Layer({}, None, directory, {}, [], False)
    for entry in entries:
        path = _extended(snapshot, entry, directory, problems) if isinstance(entry, str) else None
        if not isinstance(entry, str):
            problems.append(
                "Compiler option 5024: 'extends' must be a string or a list of strings."
            )
        if path is not None and path in (rel, *stack):
            problems.append(f"Circularity detected while resolving configuration: {path}")
            path = None
        if path is None:
            inherited = _overlay(inherited, _Layer({}, None, directory, {}, [], True))
        else:
            inherited = _overlay(inherited, _layer(snapshot, path, final, problems, [rel, *stack]))
    return _overlay(inherited, own)


def _invalid(options: dict[str, object]) -> list[str]:
    """TS5023 for a name the compiler does not know, and TS6046 for a value it refuses."""
    unknown = [
        f"Unknown compiler option '{name}'." for name in options if name not in _KNOWN_OPTIONS
    ]
    refused = [
        f"Compiler option 6046: argument for '{name}' is not valid."
        for name in _ENUMS
        if options.get(name) is not None and _lowered(options, name) is None
    ]
    return [*unknown, *refused]


def _lowered(options: dict[str, object], key: str) -> str | None:
    """An enum option's value, which the compiler matches without regard to case."""
    value = options.get(key)
    return value.lower() if isinstance(value, str) and value.lower() in _ENUMS[key] else None


def _paths(raw: dict[str, object], problems: list[str]) -> tuple[tuple[str, tuple[str, ...]], ...]:
    value = raw.get("paths")
    if value is None:
        return ()
    if not isinstance(value, dict):
        problems.append("Compiler option 5024: 'paths' must be an object.")
        return ()
    patterns = []
    for pattern, targets in value.items():
        if pattern.count("*") > 1 or not (
            isinstance(targets, list) and all(isinstance(item, str) for item in targets)
        ):
            problems.append(f"Compiler option 5061: paths pattern '{pattern}' is not valid.")
        else:
            patterns.append((pattern, tuple(str(item) for item in targets)))
    return tuple(patterns)


def _options(layer: _Layer, problems: list[str]) -> Options:
    raw = layer.compiler
    resolution = _lowered(raw, "moduleResolution")
    paths = _paths(raw, problems)
    unmodeled = [name for name in _UNMODELED if raw.get(name) not in (None, False, [])]
    if any("${configDir}" in target for _, targets in paths for target in targets):
        unmodeled.append("paths with ${configDir}")
    json_flag = raw.get("resolveJsonModule")
    options = Options(
        _lowered(raw, "module"),
        _RESOLUTIONS.get(resolution, resolution) if resolution is not None else None,
        _lowered(raw, "target"),
        raw.get("allowJs", raw.get("checkJs")) is True,
        layer.base_url,
        paths,
        layer.base_url if layer.base_url is not None else layer.paths_directory,
        tuple(unmodeled),
        json_flag if isinstance(json_flag, bool) else None,
    )
    emit, kind = options.emit_module, options.resolution
    # TS5110 and TS5095: the compiler refuses these pairs, so it observes no resolution.
    if kind == "node16" and emit not in _NODE16_MODULES:
        problems.append("Compiler option 5110: 'module' must be node16 with this moduleResolution.")
    elif kind == "nodenext" and emit != "nodenext":
        problems.append(
            "Compiler option 5110: 'module' must be nodenext with this moduleResolution."
        )
    elif kind == "bundler" and emit not in _ESM_MODULES | {"preserve"}:
        problems.append(
            "Compiler option 5095: 'bundler' needs 'module' preserve or es2015 or later."
        )
    elif emit in _NODE16_MODULES | {"nodenext"} and kind != (
        "nodenext" if emit == "nodenext" else "node16"
    ):
        problems.append(f"Compiler option 5110: 'moduleResolution' must follow 'module' {emit}.")
    return options


def _wildcard_text(single: str) -> Callable[[re.Match[str]], str]:
    def replace(found: re.Match[str]) -> str:
        if found[0] == "*":
            return single
        return "[^/]" if found[0] == "?" else re.escape(found[0])

    return replace


def _wildcard(spec: str, base: str, usage: str) -> str | None:
    """The compiler's regular expression for one file spec, over absolute-looking paths."""
    single, deep = _WILDCARDS[usage]
    path: str = posixpath.normpath(posixpath.join("/", base, spec))
    components = [""] if path == "/" else path.split("/")
    if usage != "exclude" and components[-1] == "**":
        return None
    if usage != "exclude" and not re.search(r"[.*?]", components[-1]):
        components += ["**", "*"]
    out, written, optional = "", False, 0
    for component in components:
        if component == "**":
            out += deep
        else:
            if usage == "directories":
                out, optional = out + "(?:", optional + 1
            out += "/" if written else ""
            part = ""
            if usage != "exclude" and component[:1] == "*":
                part, component = f"(?:[^./]{single})?", component[1:]
            elif usage != "exclude" and component[:1] == "?":
                part, component = "[^./]", component[1:]
            part += re.sub(r"[^\w\s/]", _wildcard_text(single), component, flags=re.ASCII)
            out += (_NOT_EXCLUDED if usage != "exclude" and part != component else "") + part
        written = True
    return out + ")?" * optional


def _matching(specs: list[str], base: str, usage: str) -> list[str]:
    return [item for spec in specs if (item := _wildcard(spec, base, usage)) is not None]


def _supported(path: str, options: Options) -> bool:
    return path.endswith(_SUPPORTED + (_SUPPORTED_JS if options.allow_js else ()))


def _base_path(spec: str) -> str:
    """The directory a spec's walk starts from: everything before its first wildcard."""
    path: str = "/" + spec if not spec.startswith("/") else spec
    found = re.search(r"[*?]", path)
    if found is None:
        return path if "." not in posixpath.basename(path) else posixpath.dirname(path) or "/"
    return path[: path.rindex("/", 0, found.start())] or "/"


def _discover(
    snapshot: Snapshot, layer: _Layer, own: str, options: Options, problems: list[str]
) -> list[str]:
    """Files named by `files` and `include`, minus `exclude`, as the compiler lists them."""
    listed = layer.specs.get("files")
    include = layer.specs.get("include")
    exclude = layer.specs.get("exclude")
    if listed is None and include is None:
        include = [join(own, "**/*")]
    # An exclusion outside the snapshot excludes nothing in it.
    exclude = (
        [spec for spec in layer.outputs if not is_outside(spec)] if exclude is None else exclude
    )
    exclude = [spec for spec in exclude if not is_outside(spec)]
    for spec in include or []:
        if spec.rstrip("/").endswith("**"):
            problems.append(f"Compiler option 5010: '{spec}' cannot end in a recursive wildcard.")
    # A pattern that climbs out of the snapshot can select nothing the collector may read.
    inside = [spec for spec in include or [] if not is_outside(spec)]
    files = _matching(inside, ".", "files")
    directories = _matching(inside, ".", "directories")
    excluded = _matching(exclude, ".", "exclude")
    # The config's own directory is walked first; a spec elsewhere adds its own start.
    starts = [join("/", own)]
    for start in sorted(_base_path(spec) for spec in inside):
        if not any(within(known, start) for known in starts):
            starts.append(start)
    found: set[str] = set()
    seen: set[str] = set()
    pending = [(start.lstrip("/") or ".", start) for start in starts]
    while pending and files:
        rel, absolute = pending.pop()
        real = snapshot.real(rel)
        if real is None or real in seen:
            continue
        seen.add(real)
        names, children = snapshot.entries(rel)
        for name in names:
            path = posixpath.join(absolute, name)
            matched = any(re.fullmatch(pattern, path) for pattern in files)
            if matched and _supported(name, options) and not _is_excluded(excluded, path):
                found.add(join(rel, name))
        for name in children:
            path = posixpath.join(absolute, name)
            reachable = any(re.fullmatch(pattern, path) for pattern in directories)
            if reachable and not _is_excluded(excluded, path):
                pending.append((join(rel, name), path))
    literal = listed or []
    known = {*literal, *found}
    return [*literal, *sorted(rel for rel in found if not _shadowed(rel, known))]


def _is_excluded(patterns: list[str], path: str) -> bool:
    return any(re.match(f"(?:{pattern})(?:/|\\Z)", path) for pattern in patterns)


def _shadowed(rel: str, known: set[str]) -> bool:
    """A file loses to a sibling with the same stem and a higher-priority extension."""
    for group in _PRIORITY:
        own = next((ext for ext in sorted(group, key=len, reverse=True) if rel.endswith(ext)), None)
        if own is None:
            continue
        stem = rel[: -len(own)]
        # A JavaScript file is kept next to its declaration file.
        return any(
            f"{stem}{ext}" in known and not (ext == ".d.ts" and own in (".js", ".jsx"))
            for ext in group[: group.index(own)]
        )
    return False


def load_config(snapshot: Snapshot, tsconfig: str, roots: tuple[str, ...]) -> Config:
    problems: list[str] = []
    own = posixpath.dirname(tsconfig) or "."
    layer = _layer(snapshot, tsconfig, own, problems, [])
    raw, _ = _read_json(snapshot, tsconfig)
    references = raw is not None and "references" in raw
    if references:
        problems.append("Project references require separately observed projects")
    options = _options(layer, problems)
    listed = _discover(snapshot, layer, own, options, problems)
    if not listed and not references:
        problems.append("No inputs were found in config file.")
    scopes = [join(".", root) for root in roots]
    for scope in scopes:
        if snapshot.real(scope) is None:
            problems.append("Missing or unsafe source root")
        elif snapshot.installed(scope):
            problems.append("Installed dependency cannot be a selected source root")
    chosen = {
        *(
            rel
            for rel in (*listed, *(scope for scope in scopes if snapshot.is_file(scope)))
            if not is_outside(rel)
            and not snapshot.installed(rel)
            and any(within(scope, rel) for scope in scopes)
        )
    }
    if not chosen:
        problems.append("No selected source files")
    snapshot.problems.update(problems)
    return Config(options, tuple(sorted(chosen)), layer.partial)
