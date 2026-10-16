# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real guarded source sites and compiler input grammar compatibility."""

import importlib.util
from pathlib import Path

import pytest
from test_typescript_control_target import _repository
from test_uml_evaluation import _model

from archkeel.analyzer.typescript.config import Options, _base_path, _shadowed, _supported, is_outside
from archkeel.analyzer.typescript.resolve import SourceKind, _file_paths, is_builtin, is_relative, package_name
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
SITES = [
    [
        "archkeel.analyzer.typescript.collect._Collection._observe",
        "if content is not None and self._selected(rel) and rel.endswith(_SOURCE):"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._references",
        "rel.endswith((\".cjs\", \".cts\"))"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._target",
        "if not reference.type_only and specifier.startswith(\"node:\") and is_builtin(specifier):"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "if specifier.startswith(\"#\"):"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "relative = specifier.startswith((\"./\", \"../\"))"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "declaration = path if path.endswith(_DECLARATION) else None"
    ],
    [
        "archkeel.analyzer.typescript.collect._Collection._local",
        "explicit = relative and specifier.endswith(_EXPLICIT_RUNTIME)"
    ],
    [
        "archkeel.analyzer.typescript.config.is_outside",
        "return PathToken.parse(rel) is PathToken.PARENT or rel.startswith(\"../\")"
    ],
    [
        "archkeel.analyzer.typescript.config._extended",
        "if not named.startswith((\"./\", \"../\")):"
    ],
    [
        "archkeel.analyzer.typescript.config._extended",
        "if not snapshot.is_file(path) and not path.endswith(\".json\"):"
    ],
    [
        "archkeel.analyzer.typescript.config._base_path",
        "path: str = \"/\" + spec if not spec.startswith(\"/\") else spec"
    ],
    [
        "archkeel.analyzer.typescript.config._discover",
        "if spec.rstrip(\"/\").endswith(\"**\"):"
    ],
    [
        "archkeel.analyzer.typescript.resolve.is_builtin",
        "if specifier.startswith(\"node:\"):"
    ],
    [
        "archkeel.analyzer.typescript.resolve.package_name",
        "return \"/\".join(parts[:2]) if specifier.startswith(\"@\") else parts[0]"
    ],
    [
        "archkeel.analyzer.typescript.resolve._typed_name",
        "if specifier.startswith(\"@\") and len(parts) > 1:"
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if rel.endswith(_ESM_EXTENSIONS):"
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if rel.endswith(_CJS_EXTENSIONS):"
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.format_of",
        "if not rel.endswith(_SCOPE_FORMATS):"
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.resolve",
        "found = self._by_name(candidate, specifier.endswith(\"/\"), esm, kinds, True)"
    ],
    [
        "archkeel.analyzer.typescript.resolve.Resolver.resolve",
        "if self._exports_aware and specifier.startswith(\"#\"):"
    ]
]


@pytest.fixture(scope="module")
def native_source(tmp_path_factory):
    root, config = _repository(tmp_path_factory.mktemp("source-input-native"))
    return _model(root, config)


@pytest.mark.parametrize(("owner", "excerpt"), SITES)
def test_actual_guarded_input_site_uses_nominal_grammar(native_source, owner, excerpt):
    evidence = {row.id: row for row in native_source.evidence}
    constructs = {row.id: row for row in native_source.records("constructs")}
    selected = [
        (record.id, violation.id)
        for violation in trace_valid_violations(native_source)
        for identity in violation.fact_ids
        if (record := constructs.get(identity)) is not None
        and record.data.get("owner") == owner
        and any(evidence[item].excerpt.strip() == excerpt for item in record.evidence_ids)
    ]
    assert not selected, (owner, excerpt, selected)


@pytest.mark.parametrize(
    ("path", "plain", "allow_js"),
    [
        (".ts", True, True), ("src/a.d.mts", True, True),
        ("src/a.TS", False, False), ("src/a.tsx", True, True),
        ("src/a.js", False, True), ("src/a.jsx", False, True),
        ("src/a.cjs", False, True), ("src/a", False, False),
        ("src/a.json", False, False), ("src/a.unknown", False, False),
    ],
)
def test_computed_supported_suffixes_remain_compiler_compatible(path, plain, allow_js):
    assert _supported(path, Options()) is plain
    assert _supported(path, Options(allow_js=True)) is allow_js


@pytest.mark.parametrize(
    ("path", "known", "shadowed"),
    [
        ("a.tsx", {"a.ts"}, True), ("a.d.ts", {"a.ts"}, True),
        ("a.js", {"a.d.ts"}, False), ("a.jsx", {"a.d.ts"}, False),
        ("a.d.cts", {"a.cts"}, True), ("a.cjs", {"a.d.cts"}, True),
        ("a.d.mts", {"a.mts"}, True), ("a.unknown", {"a.ts"}, False),
    ],
)
def test_compound_shadowing_and_javascript_declaration_exception(path, known, shadowed):
    assert _shadowed(path, known) is shadowed


@pytest.mark.parametrize(
    ("candidate", "esm", "expected"),
    [
        ("a.foo", True, []), ("a", True, []), (".ts", True, [".ts", ".tsx", ".d.ts", ".js", ".jsx"]),
        ("a.d.mts", True, ["a.mts", "a.d.mts", "a.mjs"]),
        ("a.d.json.ts", True, ["a.d.json.ts", "a.d.json.tsx", "a.d.json.d.ts", "a.d.json.js", "a.d.json.jsx"]),
        ("a.json", True, ["a.d.json.ts", "a.json"]),
        ("a.foo", False, ["a.foo.ts", "a.foo.tsx", "a.foo.d.ts", "a.foo.js", "a.foo.jsx"]),
    ],
)
def test_dynamic_extension_rewrite_preserves_unknown_and_compound_cases(candidate, esm, expected):
    assert _file_paths(candidate, esm, tuple(SourceKind)) == expected


@pytest.mark.parametrize(
    ("specifier", "relative", "builtin", "package"),
    [
        (".", True, False, "."), ("..", True, False, ".."),
        ("./a", True, False, "."), ("../a/", True, False, ".."),
        (".a", False, False, ".a"), ("node:test", False, True, "node:test"),
        ("test", False, False, "test"), ("node:fs", False, True, "node:fs"),
        ("node:unknown", False, False, "node:unknown"),
        ("@s/a/sub", False, False, "@s/a"), ("@s", False, False, "@s"),
        ("#alias", False, False, "#alias"), ("/absolute", False, False, ""),
    ],
)
def test_specifier_grammar_keeps_open_names_and_node_scheme_only_set(specifier, relative, builtin, package):
    assert is_relative(specifier) is relative
    assert is_builtin(specifier) is builtin
    assert package_name(specifier) == package


@pytest.mark.parametrize(
    ("path", "outside", "base"),
    [("../a", True, "/../a"), ("..", True, "/"), (".a", False, "/"),
     ("src/**/a.ts", False, "/src"), ("/src/*.ts", False, "/src")],
)
def test_path_and_config_walk_boundaries(path, outside, base):
    assert is_outside(path) is outside
    assert _base_path(path) == base


def test_shared_source_input_port_exists():
    assert importlib.util.find_spec("archkeel.analyzer.typescript.source_input") is not None
