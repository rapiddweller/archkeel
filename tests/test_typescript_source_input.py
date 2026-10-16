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


@pytest.mark.parametrize(
    ("name", "member"),
    [("a", "NONE"), ("", "NONE"), (".ts", "TS"), ("a.d.ts", "DTS"),
     ("a.d.cts", "DCTS"), ("a.d.mts", "DMTS"), ("a.d.json.ts", "TS"),
     ("a.TS", None), ("a.unknown", None), ("a.ts\\n", None)],
)
def test_nominal_suffix_boundary_distinguishes_absence_and_unsupported(name, member):
    from archkeel.analyzer.typescript.source_input import FileSuffix, classify_file, split_file

    suffix = classify_file(name)
    assert suffix is (None if member is None else FileSuffix[member])
    parts = split_file(name)
    if suffix is None or suffix is FileSuffix.NONE:
        assert parts is None
    else:
        assert parts is not None and parts.suffix is suffix
        assert parts.stem + parts.suffix == name


def test_moved_vocabulary_reexports_retain_identity():
    from archkeel.analyzer.typescript import config, resolve, source_input
    from archkeel.ir.facts import ResolutionRole

    assert config.PathToken is source_input.PathToken
    assert resolve.SourceKind is source_input.SourceKind
    assert resolve.ModuleFormat is resolve.Format is source_input.ModuleFormat
    assert config.Role is ResolutionRole


@pytest.mark.parametrize("role", ["selected", "resolution"])
def test_snapshot_normalizes_valid_legacy_roles_once_at_read_boundary(tmp_path, role):
    from archkeel.analyzer.typescript.config import Snapshot
    from archkeel.ir.facts import ResolutionRole

    (tmp_path / "a.ts").write_text("export const a = 1;")
    snapshot = Snapshot(str(tmp_path))
    snapshot.inputs["a.ts"] = ("old-digest", role)
    assert snapshot.read("a.ts") is not None
    assert snapshot.inputs["a.ts"][1] is ResolutionRole(role)
    snapshot.select("a.ts")
    assert snapshot.inputs["a.ts"][1] is ResolutionRole.SELECTED

@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("class FileSuffix(StrEnum):", "class FileSuffix:"),
        ("suffix: FileSuffix", "suffix: str"),
        ("kind: SpecifierKind", "kind: str"),
        ("def classify_file(name: str) -> FileSuffix | None:", "def classify_file(name: str) -> str | None:"),
        ("def split_file(name: str) -> FileParts | None:", "def split_file(name: str) -> str | None:"),
        ("def classify_specifier(text: str) -> SpecifierInfo:", "def classify_specifier(text: str) -> str:"),
    ],
)
def test_actual_input_api_type_mutation_fails_fixed_native_intent(tmp_path, old, new):
    from archkeel.ir.report_graph import architecture_report

    path = "archkeel/analyzer/typescript/source_input.py"
    source = (ROOT / "src" / path).read_text()
    assert old in source
    root, config = _repository(tmp_path, changed={path: source.replace(old, new, 1)})
    intent = (root / "contract.json").read_bytes()
    model = _model(root, config)
    comparison = architecture_report(model).comparison
    assert comparison is not None and comparison.status == "FAIL", comparison
    assert any(row.kind == "uml_target" for row in trace_valid_violations(model))
    assert (root / "contract.json").read_bytes() == intent


@pytest.mark.parametrize("spec", ["src/**", "src/**/", "src/foo**", "src/foo**/"])
def test_recursive_tail_diagnostic_keeps_existing_non_component_star_rule(tmp_path, spec):
    import json

    from test_typescript_config import _config

    _, snapshot = _config(
        tmp_path, {"src/main.ts": "export {};"},
        json.dumps({"include": [spec]}),
    )
    assert f"Compiler option 5010: '{spec}' cannot end in a recursive wildcard." in snapshot.problems


@pytest.mark.parametrize("target", ["types.unknown", "types"])
def test_package_worker_does_not_turn_unsupported_suffix_into_plain_family(tmp_path, target):
    import json

    from test_typescript_resolve import _path, _resolver

    resolver = _resolver(
        tmp_path,
        {"src/main.ts": "export {};",
         "node_modules/pkg/package.json": json.dumps({"types": target}),
         f"node_modules/pkg/{target}.ts": "export {};",
         "node_modules/pkg/types.ts": "export {};"},
    )
    assert _path(resolver.resolve("pkg", "src/main.ts", None)) == f"node_modules/pkg/{target}.ts"


@pytest.mark.parametrize("target", ["a.ts", "a.unknown"])
def test_paths_exact_known_target_and_unknown_suffix_inference_stay_distinct(tmp_path, target):
    from test_typescript_resolve import NODE10, _path, _resolver

    resolver = _resolver(
        tmp_path,
        {"src/main.ts": "export {};", f"src/{target}": "export {};",
         f"src/{target}.ts": "export {};"},
        {**NODE10, "baseUrl": ".", "paths": {"alias": [f"src/{target}"]}},
    )
    expected = target if target == "a.ts" else f"{target}.ts"
    assert _path(resolver.resolve("alias", "src/main.ts", None)) == f"src/{expected}"


@pytest.mark.parametrize("name", ["a.ts", "a.ts\\n", "a.ts\\n\\n", "a.unknown", "a"])
def test_parser_filename_compatibility_preserves_unknown_fallback_and_newline(name):
    from archkeel.analyzer.typescript.parse import parse

    # The TS grammar accepts angle-bracket assertions; TSX keeps its previous syntax concern.
    syntax = parse(name, b"const answer = <number>1;")
    expected_error = name not in ("a.ts", "a.ts\\n")
    assert (syntax.first_error is not None) is expected_error


def test_declaration_cts_keeps_written_commonjs_loader_semantics(tmp_path):
    import json

    from archkeel.analyzer.typescript.collect import collect
    from archkeel.ir.facts import BuiltinTarget
    from fixtures.typescript_differential import request_for

    (tmp_path / "src").mkdir()
    (tmp_path / "src/main.d.cts").write_text('const fs = require("node:fs");')
    (tmp_path / "tsconfig.json").write_text(json.dumps(
        {"compilerOptions": {"moduleResolution": "node"}, "files": ["src/main.d.cts"]}
    ))
    facts = collect(request_for(tmp_path, ("src",), "app"))
    assert any(isinstance(target, BuiltinTarget) for target in facts.imports)
    assert not any(
        "Unproven or shadowed require" in row.data.get("reason", "")
        for row in facts.coverage.gaps
    )
