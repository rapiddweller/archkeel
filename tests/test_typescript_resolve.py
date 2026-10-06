# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The resolver is at least as strict as the compiler: what it cannot prove is UNKNOWN."""

import json
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.config import Snapshot, load_config
from archkeel.analyzer.typescript.resolve import (
    Format,
    Found,
    Resolver,
    Unknown,
    is_builtin,
    is_relative,
    package_name,
)

NODE10 = {"module": "CommonJS", "moduleResolution": "Node"}
NODENEXT = {"module": "NodeNext", "moduleResolution": "NodeNext"}
BUNDLER = {"module": "ESNext", "moduleResolution": "Bundler"}


def _resolver(
    root: Path, files: dict[str, str], options: dict[str, object] | None = None
) -> Resolver:
    config = {"compilerOptions": options or NODE10, "include": ["src"]}
    for rel, text in {"tsconfig.json": json.dumps(config), **files}.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    snapshot = Snapshot(str(root))
    return Resolver(snapshot, load_config(snapshot, "tsconfig.json", ("src",)))


def _path(result: Found | Unknown | None) -> str | None:
    assert not isinstance(result, Unknown), result
    return None if result is None else result.path


_EMPTY = "export {};\n"


@pytest.mark.parametrize("nested_manifest", [None, {}, {"types": "local.d.ts"}])
def test_package_subdirectory_uses_only_its_own_manifest(
    tmp_path: Path, nested_manifest: dict[str, str] | None
) -> None:
    files = {
        "src/main.ts": "export {};",
        "node_modules/example/package.json": '{"types":"types.d.ts"}',
        "node_modules/example/sub/types.d.ts": "export interface Wrong {}",
        "node_modules/example/sub/local.d.ts": "export interface Local {}",
        "node_modules/example/sub/index.ts": "export interface Index {}",
    }
    if nested_manifest is not None:
        files["node_modules/example/sub/package.json"] = json.dumps(nested_manifest)
    resolver = _resolver(tmp_path, files)
    assert _path(resolver.resolve("example/sub", "src/main.ts", None)) == (
        "node_modules/example/sub/local.d.ts"
        if nested_manifest
        else "node_modules/example/sub/index.ts"
    )


@pytest.mark.parametrize(
    ("specifier", "files", "expected"),
    [
        ("./x", ["src/x.ts"], "src/x.ts"),
        ("./x", ["src/x.tsx"], "src/x.tsx"),
        ("./x", ["src/x.d.ts"], "src/x.d.ts"),
        ("./x", ["src/x.js"], "src/x.js"),
        ("./x", ["src/x.ts", "src/x.d.ts", "src/x.js"], "src/x.ts"),
        ("./x.js", ["src/x.ts"], "src/x.ts"),
        ("./x.js", ["src/x.tsx"], "src/x.tsx"),
        ("./x.js", ["src/x.d.ts"], "src/x.d.ts"),
        ("./x.js", ["src/x.js"], "src/x.js"),
        ("./x.jsx", ["src/x.tsx"], "src/x.tsx"),
        ("./x.mjs", ["src/x.mts"], "src/x.mts"),
        ("./x.mjs", ["src/x.d.mts"], "src/x.d.mts"),
        ("./x.cjs", ["src/x.cts"], "src/x.cts"),
        ("./x.ts", ["src/x.ts"], "src/x.ts"),
        ("./x.y", ["src/x.y.ts"], "src/x.y.ts"),
        ("./x", ["src/x/index.ts"], "src/x/index.ts"),
        ("./x/", ["src/x/index.ts"], "src/x/index.ts"),
        ("./x", ["src/x.ts", "src/x/index.ts"], "src/x.ts"),
        ("./x/index.js", ["src/x/index.ts"], "src/x/index.ts"),
        (".", ["src/index.ts"], "src/index.ts"),
        ("./x", ["src/x.json"], None),
        ("./x", [], None),
    ],
)
def test_relative_specifiers_follow_the_compiler_in_commonjs_resolution(
    tmp_path: Path, specifier: str, files: list[str], expected: str | None
) -> None:
    resolver = _resolver(tmp_path, dict.fromkeys(files, _EMPTY))
    assert _path(resolver.resolve(specifier, "src/main.ts", None)) == expected


def test_parent_directories_are_followed_from_the_importing_file(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, {"src/y.ts": _EMPTY, "src/a/z.ts": _EMPTY})
    assert _path(resolver.resolve("../y", "src/a/main.ts", None)) == "src/y.ts"
    assert _path(resolver.resolve("../z", "src/a/main.ts", None)) is None
    assert _path(resolver.resolve("./z", "src/a/main.ts", None)) == "src/a/z.ts"


@pytest.mark.parametrize(
    ("specifier", "files", "mode", "expected"),
    [
        # An ECMAScript importer never gets an extension or a directory index inferred.
        ("./x", ["src/x.ts"], "esm", None),
        ("./x", ["src/x/index.ts"], "esm", None),
        ("./x/", ["src/x/index.ts"], "esm", None),
        ("./x.js", ["src/x.ts"], "esm", "src/x.ts"),
        ("./x/index.js", ["src/x/index.ts"], "esm", "src/x/index.ts"),
        ("./x", ["src/x.ts"], "cjs", "src/x.ts"),
        ("./x", ["src/x/index.ts"], "cjs", "src/x/index.ts"),
        ("./x.js", ["src/x.js"], "esm", "src/x.js"),
    ],
)
def test_the_importing_files_module_format_decides_extension_and_index_rules(
    tmp_path: Path, specifier: str, files: list[str], mode: Format, expected: str | None
) -> None:
    resolver = _resolver(tmp_path, dict.fromkeys(files, _EMPTY), NODENEXT)
    assert _path(resolver.resolve(specifier, "src/main.ts", mode)) == expected


@pytest.mark.parametrize("options", [NODENEXT, BUNDLER])
def test_paths_targets_obey_the_same_rules_as_relative_specifiers(
    tmp_path: Path, options: dict[str, object]
) -> None:
    compiler = {**options, "baseUrl": ".", "paths": {"@x/*": ["src/lib/*"]}}
    resolver = _resolver(
        tmp_path,
        {"src/lib/a/index.ts": _EMPTY, "src/lib/b.ts": _EMPTY, "src/lib/c.js": _EMPTY},
        compiler,
    )
    esm = "esm" if options is NODENEXT else None
    assert _path(resolver.resolve("@x/c.js", "src/main.ts", esm)) == "src/lib/c.js"
    if esm:
        # The measured hazard: `paths` do not lift the ECMAScript restrictions.
        assert _path(resolver.resolve("@x/b", "src/main.ts", esm)) is None
        assert _path(resolver.resolve("@x/a", "src/main.ts", esm)) is None
    else:
        assert _path(resolver.resolve("@x/b", "src/main.ts", esm)) == "src/lib/b.ts"
        assert _path(resolver.resolve("@x/a", "src/main.ts", esm)) == "src/lib/a/index.ts"


def test_paths_prefer_the_longest_prefix_then_fall_back_to_base_url_and_packages(
    tmp_path: Path,
) -> None:
    compiler = {
        **NODE10,
        "baseUrl": "src",
        "paths": {"@a/*": ["one/*"], "@a/deep/*": ["two/*"], "exact": ["three.ts"]},
    }
    resolver = _resolver(
        tmp_path,
        {
            "src/one/x.ts": _EMPTY,
            "src/two/x.ts": _EMPTY,
            "src/three.ts": _EMPTY,
            "src/plain/y.ts": _EMPTY,
            "node_modules/pkg/index.d.ts": _EMPTY,
        },
        compiler,
    )
    assert _path(resolver.resolve("@a/x", "src/main.ts", None)) == "src/one/x.ts"
    assert _path(resolver.resolve("@a/deep/x", "src/main.ts", None)) == "src/two/x.ts"
    assert _path(resolver.resolve("exact", "src/main.ts", None)) == "src/three.ts"
    assert _path(resolver.resolve("plain/y", "src/main.ts", None)) == "src/plain/y.ts"
    found = resolver.resolve("pkg", "src/main.ts", None)
    assert isinstance(found, Found)
    assert (found.path, found.external) == ("node_modules/pkg/index.d.ts", True)


@pytest.mark.parametrize(
    ("package", "files", "specifier", "expected"),
    [
        ({"types": "t.d.ts"}, ["t.d.ts"], "pkg", "node_modules/pkg/t.d.ts"),
        (
            {"typings": "t.d.ts", "types": "u.d.ts"},
            ["t.d.ts", "u.d.ts"],
            "pkg",
            "node_modules/pkg/t.d.ts",
        ),
        ({"main": "lib/m.js"}, ["lib/m.js"], "pkg", "node_modules/pkg/lib/m.js"),
        ({"main": "lib/m.js"}, ["lib/m.js", "lib/m.d.ts"], "pkg", "node_modules/pkg/lib/m.d.ts"),
        ({"main": "lib/m"}, ["lib/m.ts"], "pkg", "node_modules/pkg/lib/m.ts"),
        ({}, ["index.d.ts"], "pkg", "node_modules/pkg/index.d.ts"),
        ({}, ["sub.d.ts"], "pkg/sub", "node_modules/pkg/sub.d.ts"),
        ({}, ["sub/index.d.ts"], "pkg/sub", "node_modules/pkg/sub/index.d.ts"),
        ({}, [], "pkg", None),
    ],
)
def test_installed_packages_resolve_through_types_main_and_index(
    tmp_path: Path,
    package: dict[str, object],
    files: list[str],
    specifier: str,
    expected: str | None,
) -> None:
    contents = {f"node_modules/pkg/{name}": _EMPTY for name in files}
    resolver = _resolver(
        tmp_path, {"node_modules/pkg/package.json": json.dumps(package), **contents}
    )
    result = resolver.resolve(specifier, "src/main.ts", None)
    assert _path(result) == expected
    assert result is None or (isinstance(result, Found) and result.external)


def test_a_typings_package_stands_in_for_an_untyped_one(tmp_path: Path) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "node_modules/@types/vendor__host/index.d.ts": _EMPTY,
            "node_modules/@types/vendor__host/feature.d.ts": _EMPTY,
            "node_modules/@types/vscode/index.d.ts": _EMPTY,
        },
    )
    assert _path(resolver.resolve("@vendor/host/feature", "src/main.ts", None)) == (
        "node_modules/@types/vendor__host/feature.d.ts"
    )
    assert _path(resolver.resolve("vscode", "src/main.ts", None)) == (
        "node_modules/@types/vscode/index.d.ts"
    )


def test_a_nearer_node_modules_directory_wins(tmp_path: Path) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "node_modules/pkg/index.d.ts": _EMPTY,
            "src/node_modules/pkg/index.d.ts": _EMPTY,
        },
    )
    assert _path(resolver.resolve("pkg", "src/main.ts", None)) == "src/node_modules/pkg/index.d.ts"


@pytest.mark.parametrize(
    ("options", "manifest", "specifier", "unknown"),
    [
        (NODENEXT, {"exports": {".": "./i.js"}}, "pkg", "exports"),
        (BUNDLER, {"exports": "./i.js"}, "pkg", "exports"),
        (NODENEXT, {"exports": {}}, "pkg", "exports"),
        (NODE10, {"exports": {".": "./i.js"}}, "pkg", None),
        (NODE10, {"typesVersions": {"*": {"*": ["t/*"]}}}, "pkg", "typesVersions"),
        (NODENEXT, {"typesVersions": {"*": {"*": ["t/*"]}}}, "pkg", "typesVersions"),
    ],
)
def test_package_exports_and_typesversions_are_unknown_where_the_compiler_reads_them(
    tmp_path: Path,
    options: dict[str, object],
    manifest: dict[str, object],
    specifier: str,
    unknown: str | None,
) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "node_modules/pkg/package.json": json.dumps(manifest),
            "node_modules/pkg/index.d.ts": _EMPTY,
        },
        options,
    )
    result = resolver.resolve(specifier, "src/main.ts", "cjs" if options is NODENEXT else None)
    if unknown is None:
        assert _path(result) == "node_modules/pkg/index.d.ts"
    else:
        assert isinstance(result, Unknown)
        assert unknown in result.reason


@pytest.mark.parametrize("options", [NODENEXT, BUNDLER])
def test_package_imports_and_self_references_are_unknown(
    tmp_path: Path, options: dict[str, object]
) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "package.json": json.dumps(
                {"name": "app", "exports": "./src/index.ts", "imports": {"#a": "./src/a.ts"}}
            ),
            "node_modules/other/index.d.ts": _EMPTY,
        },
        options,
    )
    for specifier in ("#a", "app", "app/sub"):
        assert isinstance(resolver.resolve(specifier, "src/main.ts", None), Unknown)
    assert _path(resolver.resolve("other", "src/main.ts", None)) == "node_modules/other/index.d.ts"


def test_package_imports_are_ordinary_names_where_the_compiler_ignores_them(
    tmp_path: Path,
) -> None:
    resolver = _resolver(tmp_path, {"package.json": json.dumps({"imports": {"#a": "./src/a.ts"}})})
    assert resolver.resolve("#a", "src/main.ts", None) is None


def test_a_paths_name_beats_a_self_reference(tmp_path: Path) -> None:
    compiler = {**BUNDLER, "baseUrl": ".", "paths": {"app": ["src/lib.ts"]}}
    resolver = _resolver(
        tmp_path,
        {"package.json": json.dumps({"name": "app", "exports": "./x.js"}), "src/lib.ts": _EMPTY},
        compiler,
    )
    assert _path(resolver.resolve("app", "src/main.ts", None)) == "src/lib.ts"


def test_a_local_directory_with_package_metadata_resolves_through_it(tmp_path: Path) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "src/pkg/package.json": json.dumps({"types": "types.ts", "main": "runtime.cjs"}),
            "src/pkg/types.ts": _EMPTY,
        },
    )
    found = resolver.resolve("./pkg", "src/main.ts", None)
    assert isinstance(found, Found)
    assert (found.path, found.directory_package) == ("src/pkg/types.ts", True)
    plain = _resolver(tmp_path, {"src/other/index.ts": _EMPTY})
    other = plain.resolve("./other", "src/main.ts", None)
    assert isinstance(other, Found)
    assert other.directory_package is False


@pytest.mark.parametrize(
    ("specifier", "reason"),
    [("/abs/x", "Absolute"), ("C:/x", None)],
)
def test_absolute_specifiers_are_unknown(
    tmp_path: Path, specifier: str, reason: str | None
) -> None:
    resolver = _resolver(tmp_path, {})
    result = resolver.resolve(specifier, "src/main.ts", None)
    if reason is not None:
        assert isinstance(result, Unknown)
        assert reason in result.reason


@pytest.mark.parametrize(
    ("options", "reason"),
    [
        ({"module": "ESNext"}, "moduleResolution classic"),
        ({**NODE10, "rootDirs": ["src", "gen"]}, "rootDirs"),
        ({**NODE10, "moduleSuffixes": [".ios", ""]}, "moduleSuffixes"),
        ({**BUNDLER, "customConditions": ["x"]}, "customConditions"),
        ({**NODE10, "preserveSymlinks": True}, "preserveSymlinks"),
        ({**NODENEXT, "resolvePackageJsonExports": True}, "resolvePackageJsonExports"),
        ({**NODE10, "noDtsResolution": True}, "noDtsResolution"),
        ({**NODE10, "allowArbitraryExtensions": True}, "allowArbitraryExtensions"),
    ],
)
def test_settings_the_resolver_does_not_apply_block_every_resolution(
    tmp_path: Path, options: dict[str, object], reason: str
) -> None:
    blocked = _resolver(tmp_path, {"src/x.ts": _EMPTY}, options).blocked
    assert blocked is not None
    assert reason in blocked.reason


def test_json_modules_resolve_where_the_compiler_enables_them(tmp_path: Path) -> None:
    files = {"src/x.json": "{}"}
    assert (
        _path(_resolver(tmp_path / "a", files, NODE10).resolve("./x.json", "src/m.ts", None))
        is None
    )
    enabled = {**NODE10, "resolveJsonModule": True}
    assert (
        _path(_resolver(tmp_path / "b", files, enabled).resolve("./x.json", "src/m.ts", None))
        == "src/x.json"
    )
    assert (
        _path(_resolver(tmp_path / "c", files, BUNDLER).resolve("./x.json", "src/m.ts", None))
        == "src/x.json"
    )
    # An extensionless name never reaches a JSON file.
    assert _path(_resolver(tmp_path / "d", files, enabled).resolve("./x", "src/m.ts", None)) is None


@pytest.mark.parametrize(
    ("path", "manifest", "expected"),
    [
        ("src/a.mts", None, "esm"),
        ("src/a.mjs", {"type": "commonjs"}, "esm"),
        ("src/a.cts", {"type": "module"}, "cjs"),
        ("src/a.d.cts", {"type": "module"}, "cjs"),
        ("src/a.ts", {"type": "module"}, "esm"),
        ("src/a.tsx", {"type": "module"}, "esm"),
        ("src/a.js", {"type": "commonjs"}, "cjs"),
        ("src/a.ts", {}, "cjs"),
        ("src/a.ts", None, "cjs"),
        ("src/sub/a.ts", {"type": "module"}, "esm"),
    ],
)
def test_module_format_comes_from_the_extension_then_the_nearest_package_type(
    tmp_path: Path, path: str, manifest: dict[str, object] | None, expected: str
) -> None:
    files = {} if manifest is None else {"package.json": json.dumps(manifest)}
    assert _resolver(tmp_path, files, NODENEXT).format_of(path) == expected


def test_the_nearest_package_json_decides_and_an_unreadable_one_is_unknown(tmp_path: Path) -> None:
    resolver = _resolver(
        tmp_path,
        {
            "package.json": json.dumps({"type": "module"}),
            "src/cjs/package.json": "{}",
            "src/broken/package.json": "{not json",
        },
        NODENEXT,
    )
    assert resolver.format_of("src/a.ts") == "esm"
    assert resolver.format_of("src/cjs/a.ts") == "cjs"
    assert isinstance(resolver.format_of("src/broken/a.ts"), Unknown)


def test_no_format_is_defined_where_the_compiler_defines_none(tmp_path: Path) -> None:
    resolver = _resolver(tmp_path, {"package.json": json.dumps({"type": "module"})})
    assert resolver.format_of("src/a.ts") is None


@pytest.mark.parametrize(
    ("specifier", "builtin"),
    [
        ("fs", True),
        ("fs/promises", True),
        ("node:fs", True),
        ("node:test", True),
        ("node:sqlite", True),
        ("test", False),
        ("sqlite", False),
        ("node:nothing", False),
        ("fs/", False),
        ("lodash", False),
    ],
)
def test_builtin_names_follow_node(specifier: str, builtin: bool) -> None:
    assert is_builtin(specifier) is builtin


def test_specifier_shapes() -> None:
    assert [
        is_relative(item) for item in (".", "..", "./a", "../a", ".a", "..a", "a/./b", "/a")
    ] == [
        True,
        True,
        True,
        True,
        False,
        False,
        False,
        False,
    ]
    assert [package_name(item) for item in ("a", "a/b", "@s/a", "@s/a/b", "@s")] == [
        "a",
        "a",
        "@s/a",
        "@s/a",
        "@s",
    ]
