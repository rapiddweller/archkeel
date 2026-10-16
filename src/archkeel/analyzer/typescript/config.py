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
from enum import Enum
from typing import Final, Literal


class ModuleKind(Enum):
    """TypeScript's accepted emit modes, owned by configuration."""

    NONE = "none"
    COMMONJS = "commonjs"
    AMD = "amd"
    SYSTEM = "system"
    UMD = "umd"
    ES6 = "es6"
    ES2015 = "es2015"
    ES2020 = "es2020"
    ES2022 = "es2022"
    ESNEXT = "esnext"
    NODE16 = "node16"
    NODE18 = "node18"
    NODE20 = "node20"
    NODENEXT = "nodenext"
    PRESERVE = "preserve"


class ModuleResolution(Enum):
    """Accepted resolver modes; NODE is normalized to NODE10 at the input boundary."""

    NODE10 = "node10"
    CLASSIC = "classic"
    NODE16 = "node16"
    NODENEXT = "nodenext"
    BUNDLER = "bundler"


class ScriptTarget(Enum):
    """Accepted compilation targets; defaults retain the explicit original value."""

    ES3 = "es3"
    ES5 = "es5"
    ES6 = "es6"
    ES2015 = "es2015"
    ES2016 = "es2016"
    ES2017 = "es2017"
    ES2018 = "es2018"
    ES2019 = "es2019"
    ES2020 = "es2020"
    ES2021 = "es2021"
    ES2022 = "es2022"
    ES2023 = "es2023"
    ES2024 = "es2024"
    ESNEXT = "esnext"


class PathToken(Enum):
    """Closed path/glob grammar, distinct from user-supplied path names."""

    CURRENT = "."
    PARENT = ".."
    ROOT = "/"
    RELATIVE = "./"
    STAR = "*"
    DEEP_STAR = "**"
    QUESTION = "?"
    NODE_MODULES = "node_modules"

    @staticmethod
    def parse(value: str) -> PathToken | None:
        return _PATH_TOKENS.get(value)


class _WildcardUsage(Enum):
    FILES = "files"
    DIRECTORIES = "directories"
    EXCLUDE = "exclude"


class _ShadowKind(Enum):
    DECLARATION = ".d.ts"
    JAVASCRIPT = ".js"
    JSX = ".jsx"


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
_PATH_TOKENS: Final[dict[str, PathToken]] = {member.value: member for member in PathToken}
_MODULE_VALUES: Final[dict[str, ModuleKind]] = {member.value: member for member in ModuleKind}
_RESOLUTION_VALUES: Final[dict[str, ModuleResolution]] = {
    **{member.value: member for member in ModuleResolution},
    "node": ModuleResolution.NODE10,
}
_TARGET_VALUES: Final[dict[str, ScriptTarget]] = {member.value: member for member in ScriptTarget}
_SHADOW_KINDS: Final[dict[str, _ShadowKind]] = {member.value: member for member in _ShadowKind}
_ENUMS: Final[dict[str, dict[str, Enum]]] = {
    "module": dict(_MODULE_VALUES),
    "moduleResolution": dict(_RESOLUTION_VALUES),
    "target": dict(_TARGET_VALUES),
}
_BOOLEAN_OPTIONS: Final = frozenset("allowJs checkJs resolveJsonModule".split())
_STRING_OPTIONS: Final = frozenset("baseUrl declarationDir outDir".split())
_STRING_LIST_OPTIONS: Final = frozenset("customConditions moduleSuffixes rootDirs".split())
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
_ESM_MODULES: Final = frozenset(
    {ModuleKind.ES6, ModuleKind.ES2015, ModuleKind.ES2020, ModuleKind.ES2022, ModuleKind.ESNEXT}
)
_NODE16_MODULES: Final = frozenset({ModuleKind.NODE16, ModuleKind.NODE18, ModuleKind.NODE20})
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
    _WildcardUsage.FILES: (r"(?:[^./]|(?:\.(?!min\.js\Z))?)*", _DEEP),
    _WildcardUsage.DIRECTORIES: (r"[^/]*", _DEEP),
    _WildcardUsage.EXCLUDE: (r"[^/]*", r"(?:/.+?)?"),
}


@dataclass(frozen=True, slots=True)
class Options:
    """The compiler settings a resolver reads; explicit values only, as the compiler keeps them."""

    module: ModuleKind | None = None
    module_resolution: ModuleResolution | None = None
    target: ScriptTarget | None = None
    allow_js: bool = False
    # Snapshot-relative directory of `baseUrl`, the `paths` patterns with their targets, and the
    # directory those targets are relative to: `baseUrl`, else the TSConfig that sets them.
    base_url: str | None = None
    paths: tuple[tuple[str, tuple[str, ...]], ...] = ()
    paths_base: str = "."
    unmodeled: tuple[str, ...] = ()
    json_modules: bool | None = None

    def __post_init__(self) -> None:
        for name, value, kind in (
            ("module", self.module, ModuleKind),
            ("module_resolution", self.module_resolution, ModuleResolution),
            ("target", self.target, ScriptTarget),
        ):
            if value is not None and not isinstance(value, kind):
                raise TypeError(f"{name} must be {kind.__name__} or None")

    @property
    def resolve_json(self) -> bool:
        """Whether JSON resolves: explicit setting, else Node20/Next or Bundler."""
        if self.json_modules is not None:
            return self.json_modules
        return self.emit_module in (ModuleKind.NODE20, ModuleKind.NODENEXT) or (
            self.resolution is ModuleResolution.BUNDLER
        )

    @property
    def emit_module(self) -> ModuleKind:
        """The emit mode after applying the compiler's target-dependent default."""
        if self.module is not None:
            return self.module
        return (
            ModuleKind.COMMONJS
            if self.target in (None, ScriptTarget.ES3, ScriptTarget.ES5)
            else ModuleKind.ES2015
        )

    @property
    def resolution(self) -> ModuleResolution:
        """The effective resolution mode, normalized once before resolver dispatch."""
        if self.module_resolution is not None:
            return self.module_resolution
        implied = {
            ModuleKind.COMMONJS: ModuleResolution.NODE10,
            ModuleKind.NODENEXT: ModuleResolution.NODENEXT,
            ModuleKind.PRESERVE: ModuleResolution.BUNDLER,
        }
        return (
            ModuleResolution.NODE16
            if self.emit_module in _NODE16_MODULES
            else implied.get(self.emit_module, ModuleResolution.CLASSIC)
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
    return PathToken.parse(rel) is PathToken.PARENT or rel.startswith("../")


def within(scope: str, path: str) -> bool:
    return (
        PathToken.parse(scope) is PathToken.CURRENT or path == scope or path.startswith(f"{scope}/")
    )


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
    outputs: dict[str, str | None]
    partial: bool


def _overlay(low: _Layer, high: _Layer) -> _Layer:
    """`high` wins key by key; `paths` carries the directory of the config that set it."""
    return _Layer(
        {**low.compiler, **high.compiler},
        high.base_url if "baseUrl" in high.compiler else low.base_url,
        high.paths_directory if "paths" in high.compiler else low.paths_directory,
        {**low.specs, **high.specs},
        {**low.outputs, **high.outputs},
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
        return _Layer({}, None, directory, {}, {}, True)
    declared = raw.get("compilerOptions")
    compiler = dict(declared) if isinstance(declared, dict) else {}
    partial = declared is not None and not isinstance(declared, dict)
    if partial:
        problems.append("Compiler option 5024: 'compilerOptions' must be an object.")
    invalid = _invalid(compiler)
    problems.extend(invalid)
    partial = partial or bool(invalid)
    before_paths = len(problems)
    _paths(compiler, problems)
    partial = partial or len(problems) > before_paths
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
            partial = True
    base_url = compiler.get("baseUrl")
    outputs: dict[str, str | None] = {}
    for name in ("outDir", "declarationDir"):
        if name in compiler:
            value = compiler[name]
            outputs[name] = _under(value, directory, final) if isinstance(value, str) else None
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
    inherited = _Layer({}, None, directory, {}, {}, False)
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
            inherited = _overlay(inherited, _Layer({}, None, directory, {}, {}, True))
        else:
            inherited = _overlay(inherited, _layer(snapshot, path, final, problems, [rel, *stack]))
    return _overlay(inherited, own)


def _invalid(options: dict[str, object]) -> list[str]:
    """Name unknown options and refuse malformed values used by selection or resolution."""
    unknown = [
        f"Unknown compiler option '{name}'." for name in options if name not in _KNOWN_OPTIONS
    ]
    refused = [
        f"Compiler option 6046: argument for '{name}' is not valid."
        for name, choices in _ENUMS.items()
        if options.get(name) is not None and choices.get(_normalized(options, name)) is None
    ]
    malformed: list[str] = []
    booleans = _BOOLEAN_OPTIONS | (frozenset(_UNMODELED) - _STRING_LIST_OPTIONS)
    for name, value in options.items():
        if value is None:
            continue
        if name in booleans and not isinstance(value, bool):
            malformed.append(f"Compiler option 5024: '{name}' must be a boolean.")
        elif name in _STRING_OPTIONS and not isinstance(value, str):
            malformed.append(f"Compiler option 5024: '{name}' must be a string.")
        elif name in _STRING_LIST_OPTIONS and not (
            isinstance(value, list) and all(isinstance(item, str) for item in value)
        ):
            malformed.append(f"Compiler option 5024: '{name}' must be a list of strings.")
    return [*unknown, *refused, *malformed]


def _normalized(options: Json, key: str) -> str:
    """Normalize one raw option; the owned lookup decides whether it is accepted."""
    value = options.get(key)
    return value.lower() if isinstance(value, str) else ""


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
    resolution = _RESOLUTION_VALUES.get(_normalized(raw, "moduleResolution"))
    paths = _paths(raw, problems)
    unmodeled = [name for name in _UNMODELED if raw.get(name) not in (None, False, [])]
    if any("${configDir}" in target for _, targets in paths for target in targets):
        unmodeled.append("paths with ${configDir}")
    json_flag = raw.get("resolveJsonModule")
    options = Options(
        _MODULE_VALUES.get(_normalized(raw, "module")),
        resolution,
        _TARGET_VALUES.get(_normalized(raw, "target")),
        (raw.get("allowJs") if raw.get("allowJs") is not None else raw.get("checkJs")) is True,
        layer.base_url,
        paths,
        layer.base_url if layer.base_url is not None else layer.paths_directory,
        tuple(unmodeled),
        json_flag if isinstance(json_flag, bool) else None,
    )
    emit, kind = options.emit_module, options.resolution
    # TS5110 and TS5095: the compiler refuses these pairs, so it observes no resolution.
    if kind is ModuleResolution.NODE16 and emit not in _NODE16_MODULES:
        problems.append("Compiler option 5110: 'module' must be node16 with this moduleResolution.")
    elif kind is ModuleResolution.NODENEXT and emit is not ModuleKind.NODENEXT:
        problems.append(
            "Compiler option 5110: 'module' must be nodenext with this moduleResolution."
        )
    elif kind is ModuleResolution.BUNDLER and emit not in _ESM_MODULES | {ModuleKind.PRESERVE}:
        problems.append(
            "Compiler option 5095: 'bundler' needs 'module' preserve or es2015 or later."
        )
    elif emit in _NODE16_MODULES | {ModuleKind.NODENEXT} and kind != (
        ModuleResolution.NODENEXT if emit is ModuleKind.NODENEXT else ModuleResolution.NODE16
    ):
        problems.append(
            f"Compiler option 5110: 'moduleResolution' must follow 'module' {emit.value}."
        )
    return options


def _wildcard_text(single: str) -> Callable[[re.Match[str]], str]:
    def replace(found: re.Match[str]) -> str:
        token = PathToken.parse(found[0])
        if token is PathToken.STAR:
            return single
        return "[^/]" if token is PathToken.QUESTION else re.escape(found[0])

    return replace


def _wildcard(spec: str, base: str, usage: _WildcardUsage) -> str | None:
    """The compiler's regular expression for one file spec, over absolute-looking paths."""
    single, deep = _WILDCARDS[usage]
    path: str = posixpath.normpath(posixpath.join("/", base, spec))
    components = [""] if PathToken.parse(path) is PathToken.ROOT else path.split("/")
    if (
        usage is not _WildcardUsage.EXCLUDE
        and PathToken.parse(components[-1]) is PathToken.DEEP_STAR
    ):
        return None
    if usage is not _WildcardUsage.EXCLUDE and not re.search(r"[.*?]", components[-1]):
        components += ["**", "*"]
    out, written, optional = "", False, 0
    for component in components:
        if PathToken.parse(component) is PathToken.DEEP_STAR:
            out += deep
        else:
            if usage is _WildcardUsage.DIRECTORIES:
                out, optional = out + "(?:", optional + 1
            out += "/" if written else ""
            part = ""
            if (
                usage is not _WildcardUsage.EXCLUDE
                and PathToken.parse(component[:1]) is PathToken.STAR
            ):
                part, component = f"(?:[^./]{single})?", component[1:]
            elif (
                usage is not _WildcardUsage.EXCLUDE
                and PathToken.parse(component[:1]) is PathToken.QUESTION
            ):
                part, component = "[^./]", component[1:]
            part += re.sub(r"[^\w\s/]", _wildcard_text(single), component, flags=re.ASCII)
            out += (
                _NOT_EXCLUDED if usage is not _WildcardUsage.EXCLUDE and part != component else ""
            ) + part
        written = True
    return out + ")?" * optional


def _matching(specs: list[str], base: str, usage: _WildcardUsage) -> list[str]:
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
        [spec for spec in layer.outputs.values() if spec and not is_outside(spec)]
        if exclude is None
        else exclude
    )
    exclude = [spec for spec in exclude if not is_outside(spec)]
    for spec in include or []:
        if spec.rstrip("/").endswith("**"):
            problems.append(f"Compiler option 5010: '{spec}' cannot end in a recursive wildcard.")
    # A pattern that climbs out of the snapshot can select nothing the collector may read.
    inside = [spec for spec in include or [] if not is_outside(spec)]
    files = _matching(inside, ".", _WildcardUsage.FILES)
    directories = _matching(inside, ".", _WildcardUsage.DIRECTORIES)
    excluded = _matching(exclude, ".", _WildcardUsage.EXCLUDE)
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
            f"{stem}{ext}" in known
            and not (
                _SHADOW_KINDS.get(ext) is _ShadowKind.DECLARATION
                and _SHADOW_KINDS.get(own) in (_ShadowKind.JAVASCRIPT, _ShadowKind.JSX)
            )
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
    options_before = len(problems)
    options = _options(layer, problems)
    options_partial = len(problems) > options_before
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
    return Config(options, tuple(sorted(chosen)), layer.partial or options_partial)
