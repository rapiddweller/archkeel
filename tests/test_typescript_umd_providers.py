# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Vendored UMD publications bind their source, provenance, and declared host."""

import hashlib
import json
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.config import ScriptHost, ScriptProvider, Snapshot, load_config
from archkeel.analyzer.typescript.parse import umd_publication
from archkeel.analyzer.typescript.resolve import Resolver

ROOT = Path(__file__).parents[1]
BUNDLE = "src/archkeel/render/assets/elkjs-0.12.0.bundled.js"
LICENSE = "src/archkeel/render/assets/ELKJS-LICENSE.md"
UMD = (
    '(function(f){if(typeof exports==="object"&&typeof module!=="undefined"){module.exports=f()}'
    'else if(typeof define==="function"&&define.amd){define([],f)}else{var g;'
    'if(typeof window!=="undefined"){g=window}else if(typeof global!=="undefined"){g=global}'
    'else if(typeof self!=="undefined"){g=self}else{g=this}g.Widget=f()}})'
    "(function(){return function Widget(){};});"
)


def _repository(tmp_path, *, source=UMD, host="classic-browser", metadata=None, compiler=None):
    (tmp_path / "main.js").write_text("new Widget();")
    (tmp_path / "vendor.js").write_text(source)
    digest = hashlib.sha256(source.encode()).hexdigest()
    (tmp_path / "LICENSE.md").write_text(
        metadata
        if metadata is not None
        else "# Widget 1.2.3 browser bundle\n\nVendored from `vendor-widget@1.2.3` "
        "(`lib/widget.js`), https://example.test/vendor-widget.\n"
        f"Bundle SHA-256: `{digest}`.\nSPDX license: `MIT`.\n"
    )
    section = {"scriptProviders": [{"source": "vendor.js", "provenance": "LICENSE.md"}]}
    if host is not None:
        section["scriptHost"] = host
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {"allowJs": True, **(compiler or {})},
                "files": ["main.js"],
                "archkeel": section,
            }
        )
    )
    snapshot = Snapshot(str(tmp_path))
    config = load_config(snapshot, "tsconfig.json", ("main.js",))
    return config, snapshot, Resolver(snapshot, config)


def test_actual_vendor_binds_its_existing_package_provenance_and_native_publication():
    source = (ROOT / BUNDLE).read_bytes()
    publication = umd_publication(BUNDLE, source)
    assert publication is not None and publication[0] == "ELK"
    assert publication[2] is None
    snapshot = Snapshot(str(ROOT))
    from archkeel.analyzer.typescript.config import Config, Options

    provider = ScriptProvider(BUNDLE, LICENSE)
    resolver = Resolver(
        snapshot, Config(Options(), (), False, ScriptHost.CLASSIC_BROWSER, (provider,))
    )
    assert resolver.script_provider(ScriptProvider(BUNDLE, LICENSE)) == ("elkjs", source)
    assert {BUNDLE, LICENSE} <= snapshot.inputs.keys()


def test_a_provider_not_declared_in_the_bound_config_is_not_authenticated(tmp_path):
    _, snapshot, _ = _repository(tmp_path)
    from archkeel.analyzer.typescript.config import Config, Options

    resolver = Resolver(snapshot, Config(Options(), (), False, ScriptHost.CLASSIC_BROWSER))
    assert resolver.script_provider(ScriptProvider("vendor.js", "LICENSE.md")) is None


def test_renamed_native_envelope_uses_actual_package_not_publication_name(tmp_path):
    config, snapshot, resolver = _repository(tmp_path)
    assert config.script_host is ScriptHost.CLASSIC_BROWSER
    assert config.script_providers == (ScriptProvider("vendor.js", "LICENSE.md"),)
    assert config.files == ("main.js",)
    package, content = resolver.script_provider(config.script_providers[0])
    assert package == "vendor-widget"
    assert umd_publication("vendor.js", content)[0] == "Widget"
    assert {"tsconfig.json", "vendor.js", "LICENSE.md"} <= snapshot.inputs.keys()


@pytest.mark.parametrize(
    ("compiler", "authenticated"),
    [
        ({"types": ["node"]}, True),
        ({"typeRoots": ["./ambient"]}, True),
        ({"libReplacement": True}, False),
        ({"lib": ["es2022", "unobserved.library"]}, False),
    ],
)
def test_types_do_not_block_a_vendor_but_a_replacement_lib_does(tmp_path, compiler, authenticated):
    config, _, resolver = _repository(tmp_path, compiler=compiler)
    assert (resolver.script_provider(config.script_providers[0]) is not None) is authenticated


@pytest.mark.parametrize("host", [None, "commonjs", "amd"])
def test_undeclared_or_incompatible_host_never_authenticates_vendor(tmp_path, host):
    config, _, resolver = _repository(tmp_path, host=host)
    assert resolver.script_provider(config.script_providers[0]) is None


@pytest.mark.parametrize("change", ["source", "digest", "package", "version", "missing", "extra"])
def test_missing_or_changed_bound_provenance_never_authenticates_vendor(tmp_path, change):
    config, _, resolver = _repository(tmp_path)
    license_path = tmp_path / "LICENSE.md"
    if change == "source":
        (tmp_path / "vendor.js").write_text(UMD + "\n")
    elif change == "missing":
        license_path.unlink()
    else:
        text = license_path.read_text()
        if change == "digest":
            text = text.replace(hashlib.sha256(UMD.encode()).hexdigest(), "0" * 64)
        elif change == "package":
            text = text.replace("vendor-widget@", "bad package@")
        elif change == "version":
            text = text.replace("vendor-widget@1.2.3", "vendor-widget@9.8.7")
        else:
            text += "\nBundle SHA-256: `" + "0" * 64 + "`.\n"
        license_path.write_text(text)
    assert resolver.script_provider(config.script_providers[0]) is None


@pytest.mark.parametrize(
    ("before", "after"),
    [
        ("g.Widget=f()", "g[computed]=f()"),
        ("g=window", "g=other"),
        ('typeof window!=="undefined"', 'typeof other!=="undefined"'),
        ("module.exports=f()", "module.other=f()"),
        ("define([],f)", "define([dependency],f)"),
        ("g.Widget=f()", "g.Widget=other()"),
        ("function(){return function Widget(){};}", "42"),
        ("function(){return function Widget(){};}", "async function(){}"),
        ("function(f)", "function(window)"),
        ("g.Widget=f()", "g.Widget=f(); g.Other=f()"),
    ],
)
def test_changed_or_ambiguous_outer_envelope_stays_unproved(before, after):
    assert before in UMD
    assert umd_publication("vendor.js", UMD.replace(before, after).encode()) is None


def test_publication_match_accepts_alpha_renaming_but_rejects_extra_top_level_effects():
    renamed = (
        UMD.replace("(f)", "(factory)").replace("f()", "factory()").replace("[],f)", "[],factory)")
    )
    renamed = renamed.replace("var g;", "var root;").replace("g=", "root=").replace("g.", "root.")
    assert umd_publication("vendor.js", renamed.encode())[0] == "Widget"
    assert umd_publication("vendor.js", (UMD + "other();").encode()) is None
    assert umd_publication("vendor.ts", UMD.encode()) is None


@pytest.mark.parametrize(
    "environment",
    [
        [],
        {"scriptHost": "classic-browser", "unexpected": True},
        {"scriptHost": []},
        {"scriptHost": "classic-browser", "scriptProviders": {}},
        {"scriptHost": "classic-browser", "scriptProviders": [{"source": 1, "provenance": "a"}]},
        {
            "scriptHost": "classic-browser",
            "scriptProviders": [{"source": "../a", "provenance": "a"}],
        },
        {"scriptHost": "classic-browser", "scriptProviders": [{"source": "/a", "provenance": "a"}]},
        {
            "scriptHost": "classic-browser",
            "scriptProviders": [{"source": "a", "provenance": "a", "extra": 1}],
        },
        {
            "scriptHost": "classic-browser",
            "scriptProviders": [{"source": "a", "provenance": "a"}] * 2,
        },
    ],
)
def test_script_environment_is_closed_and_rejects_unsafe_or_malformed_inputs(tmp_path, environment):
    _repository(tmp_path)
    path = tmp_path / "tsconfig.json"
    value = json.loads(path.read_text())
    value["archkeel"] = environment
    path.write_text(json.dumps(value))
    snapshot = Snapshot(str(tmp_path))
    config = load_config(snapshot, "tsconfig.json", ("main.js",))
    assert config.partial and snapshot.problems
    assert (
        Resolver(snapshot, config).script_provider(ScriptProvider("vendor.js", "LICENSE.md"))
        is None
    )


def test_vendor_symlink_cannot_authenticate_source_outside_snapshot(tmp_path):
    config, snapshot, resolver = _repository(tmp_path)
    outside = tmp_path.parent / (tmp_path.name + "-outside.js")
    outside.write_text(UMD)
    source = tmp_path / "vendor.js"
    source.unlink()
    source.symlink_to(outside)
    assert resolver.script_provider(config.script_providers[0]) is None
    assert snapshot.problems and "vendor.js" not in snapshot.inputs


def _native(tmp_path, *, v4=False):
    from archkeel.analyzer.typescript.collect import collect
    from archkeel.ir.facts_codec import decode_response, encode_response
    from archkeel.ir.protocol import (
        CollectionRequest,
        CollectionResponse,
        ProtocolVersion,
        SnapshotInput,
        SourceScope,
        TypeScriptSettings,
    )

    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("main.js",), "browser"),
        TypeScriptSettings(),
    )
    version = ProtocolVersion.V4 if v4 else ProtocolVersion.V3
    return decode_response(encode_response(CollectionResponse(collect(request), version))).facts


def test_actual_vendor_collects_through_v4_without_selecting_or_executing_it(tmp_path):
    from archkeel.ir.facts import UnresolvedTarget

    _repository(tmp_path)
    (tmp_path / "vendor.js").write_bytes((ROOT / BUNDLE).read_bytes())
    (tmp_path / "LICENSE.md").write_bytes((ROOT / LICENSE).read_bytes())
    (tmp_path / "main.js").write_text("new ELK();")
    facts = _native(tmp_path, v4=True)
    assert facts.coverage.selected_files == ("main.js",) and len(facts.files) == 1
    assert len(facts.imports) == 1 and isinstance(facts.imports[0], UnresolvedTarget)
    assert facts.imports[0].specifier == "ELK"
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)
    assert (
        next(item.digest for item in facts.inputs if item.path == "vendor.js")
        == hashlib.sha256((ROOT / BUNDLE).read_bytes()).hexdigest()
    )
    calls = [
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
    ]
    assert calls and all(record.data.get("status") != "resolved" for record in calls)


def test_native_wire_external_package_keeps_provider_outside_scope_and_call_unproved(tmp_path):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    facts = _native(tmp_path)
    assert facts.coverage.selected_files == ("main.js",)
    assert len(facts.files) == 1
    assert len(facts.imports) == 1 and isinstance(facts.imports[0], ExternalPackageTarget)
    assert facts.imports[0].package == "vendor-widget"
    assert {item.path for item in facts.inputs} >= {"vendor.js", "LICENSE.md"}
    calls = [
        record
        for section in facts.sections
        if section.name == "calls"
        for record in section.records
    ]
    assert calls and all(record.data.get("status") != "resolved" for record in calls)
    assert not [
        gap for gap in facts.coverage.gaps if gap.data.get("resolution_dimension") == "imports"
    ]


@pytest.mark.parametrize("host", [None, "commonjs", "amd"])
def test_native_wire_does_not_promote_a_vendor_without_its_declared_host(tmp_path, host):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path, host=host)
    facts = _native(tmp_path)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "source",
    [
        "var exports = {};",
        "var module = {};",
        "var define = function() {};",
        "var window = {};",
        "var global = {};",
        "var self = {};",
        "exports.extra = 1;",
        "module.exports = {};",
        "define.amd = true;",
        "window.exports = {};",
        "var Widget = {};",
        "window.Widget = {};",
        "globalThis.Widget = {};",
        "Widget = other;",
    ],
)
def test_native_selected_loader_or_publication_collisions_never_become_external(tmp_path, source):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    (tmp_path / "main.js").write_text(source + "\nnew Widget();")
    facts = _native(tmp_path)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)


@pytest.mark.parametrize("changed", ["source", "provenance", "missing", "duplicate"])
def test_native_missing_changed_or_competing_provider_never_becomes_external(tmp_path, changed):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    if changed == "source":
        (tmp_path / "vendor.js").write_text(UMD + "\n")
    elif changed == "provenance":
        (tmp_path / "LICENSE.md").write_text("unproved")
    elif changed == "missing":
        (tmp_path / "vendor.js").unlink()
    else:
        path = tmp_path / "tsconfig.json"
        value = json.loads(path.read_text())
        value["archkeel"]["scriptProviders"] *= 2
        path.write_text(json.dumps(value))
    facts = _native(tmp_path)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize("capture", ["factory", "root", "publication"])
def test_escaped_umd_identifiers_never_create_a_native_external_binding(tmp_path, capture):
    from archkeel.ir.facts import ExternalPackageTarget

    if capture == "factory":
        source = (
            UMD.replace("(f)", "(w\\u0069ndow)")
            .replace("f()", "w\\u0069ndow()")
            .replace("[],f)", "[],w\\u0069ndow)")
        )
    elif capture == "root":
        source = (
            UMD.replace("var g;", "var w\\u0069ndow;")
            .replace("g=", "w\\u0069ndow=")
            .replace("g.", "w\\u0069ndow.")
        )
    else:
        source = UMD.replace("g.Widget", "g.W\\u0069dget")
    _repository(tmp_path, source=source)
    assert umd_publication("vendor.js", source.encode()) is None
    assert not any(
        isinstance(target, ExternalPackageTarget) for target in _native(tmp_path).imports
    )


def _second_provider(tmp_path, source):
    (tmp_path / "second.js").write_text(source)
    provenance = (tmp_path / "LICENSE.md").read_text().replace("vendor-widget@", "second-widget@")
    provenance = provenance.replace(
        hashlib.sha256(UMD.encode()).hexdigest(), hashlib.sha256(source.encode()).hexdigest()
    )
    (tmp_path / "SECOND-LICENSE.md").write_text(provenance)
    path = tmp_path / "tsconfig.json"
    value = json.loads(path.read_text())
    value["archkeel"]["scriptProviders"].append(
        {"source": "second.js", "provenance": "SECOND-LICENSE.md"}
    )
    path.write_text(json.dumps(value))


@pytest.mark.parametrize("unproved", ["hash", "metadata", "source", "provenance", "envelope"])
def test_an_unproved_declared_provider_cannot_disappear_from_the_namespace_inventory(
    tmp_path, unproved
):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    _second_provider(tmp_path, "window.Widget = replacement;" if unproved == "envelope" else UMD)
    if unproved == "hash":
        path = tmp_path / "SECOND-LICENSE.md"
        path.write_text(
            path.read_text().replace(hashlib.sha256(UMD.encode()).hexdigest(), "0" * 64)
        )
    elif unproved == "metadata":
        (tmp_path / "SECOND-LICENSE.md").write_text("unproved")
    elif unproved == "source":
        (tmp_path / "second.js").unlink()
    elif unproved == "provenance":
        (tmp_path / "SECOND-LICENSE.md").unlink()
    facts = _native(tmp_path, v4=True)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize("publication", ["module", "exports", "define"])
def test_a_provider_publication_cannot_contradict_the_declared_no_loader_host(
    tmp_path, publication
):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    _second_provider(tmp_path, UMD.replace("g.Widget", "g." + publication))
    facts = _native(tmp_path, v4=True)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


def test_a_closed_unrelated_provider_does_not_hide_a_valid_vendor(tmp_path):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path)
    _second_provider(tmp_path, UMD.replace("g.Widget", "g.Helper"))
    facts = _native(tmp_path, v4=True)
    assert len(facts.imports) == 1 and isinstance(facts.imports[0], ExternalPackageTarget)
    assert facts.imports[0].package == "vendor-widget"


def test_authenticated_vendor_publication_wins_over_a_standard_global_spelling(tmp_path):
    from archkeel.ir.facts import ExternalPackageTarget

    _repository(tmp_path, source=UMD.replace("g.Widget", "g.Math"))
    (tmp_path / "main.js").write_text("Math.abs(-1);")
    facts = _native(tmp_path, v4=True)
    assert len(facts.imports) == 1 and isinstance(facts.imports[0], ExternalPackageTarget)
    assert facts.imports[0].package == "vendor-widget"


@pytest.mark.parametrize("closed", [True, False])
def test_standard_global_proof_requires_a_closed_declared_provider_inventory(tmp_path, closed):
    from archkeel.ir.facts import BuiltinTarget, UnresolvedTarget

    _repository(tmp_path)
    _second_provider(tmp_path, UMD.replace("g.Widget", "g.Helper"))
    if not closed:
        (tmp_path / "SECOND-LICENSE.md").write_text("unproved")
    (tmp_path / "main.js").write_text("Math.abs(-1);")
    facts = _native(tmp_path, v4=True)
    assert len(facts.imports) == 1
    if closed:
        assert isinstance(facts.imports[0], BuiltinTarget)
        assert facts.imports[0].name == "Math"
    else:
        assert isinstance(facts.imports[0], UnresolvedTarget)
        assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


def test_provider_factory_global_write_cannot_prove_a_standard_binding(tmp_path):
    from archkeel.ir.facts import BuiltinTarget, ExternalPackageTarget, UnresolvedTarget

    source = UMD.replace(
        "return function Widget(){};",
        "window.Math = {abs: function(){return 7}}; return function Widget(){};",
    )
    _repository(tmp_path, source=source)
    (tmp_path / "main.js").write_text("Math.abs(-1); new Widget();")
    facts = _native(tmp_path, v4=True)
    assert not any(isinstance(target, BuiltinTarget) for target in facts.imports)
    assert any(isinstance(target, UnresolvedTarget) for target in facts.imports)
    assert any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize("written", ["Widget", "[key]"])
def test_other_provider_factory_cannot_replace_a_vendor_binding(tmp_path, written):
    from archkeel.ir.facts import ExternalPackageTarget, UnresolvedTarget

    _repository(tmp_path)
    target = "window" + (written if written.startswith("[") else "." + written)
    source = UMD.replace("g.Widget", "g.Helper").replace(
        "return function Widget(){};", target + " = replacement; return function Widget(){};"
    )
    _second_provider(tmp_path, source)
    facts = _native(tmp_path, v4=True)
    assert not any(isinstance(target, ExternalPackageTarget) for target in facts.imports)
    assert any(isinstance(target, UnresolvedTarget) for target in facts.imports)


def test_unrelated_provider_write_preserves_standard_global_identity(tmp_path):
    from archkeel.ir.facts import BuiltinTarget

    source = UMD.replace(
        "return function Widget(){};", "window.Other = {}; return function Widget(){};"
    )
    _repository(tmp_path, source=source)
    (tmp_path / "main.js").write_text("Math.abs(-1);")
    facts = _native(tmp_path, v4=True)
    assert len(facts.imports) == 1 and isinstance(facts.imports[0], BuiltinTarget)
    assert facts.imports[0].name == "Math"


@pytest.mark.parametrize(
    "body",
    [
        "window.Math = replacement;",
        r"window.M\u0061th = replacement;",
        r"Object.assign(window, {M\u0061th: replacement});",
        r"const Math = replacement; Object.assign(window, {M\u0061th});",
        r"const Math = {value: replacement}; Object.defineProperties(window, {M\u0061th});",
        "const Math = replacement; Object.assign(window, {Math});",
        r"Object.defin\u0065Property(window, 'Math', {value: replacement});",
        "Reflect[key](window, 'Math', replacement);",
        "Object?.defineProperty?.((window), 'Math', {value: replacement});",
        r"const ro\u006ft = window; root.Math = replacement;",
        r"w\u0069ndow.Math = replacement;",
        "(window).Math = replacement;",
        "const root = (window); root.Math = replacement;",
        "const root = ((window)); (root).Math = replacement;",
        "globalThis.Math = replacement;",
        "this.Math = replacement;",
        "const root = this; root.Math = replacement;",
        "Math = replacement;",
        "const root = window; root.Math = replacement;",
        "const root = window; const alias = root; alias.Math = replacement;",
        "var root = window; var root; root.Math = replacement;",
        "let root; root = window; root.Math = replacement;",
        "let root = {}; if (flag) root = window; root.Math = replacement;",
        "window['Math'] = replacement;",
        "window[key] = replacement;",
        "const root = window; root[key] = replacement;",
        "Object.defineProperty(window, 'Math', {value: replacement});",
        'Object["defineProperty"](window, "Math", {value: replacement});',
        '(Object["defineProperty"])((window), "Math", {value: replacement});',
        'Reflect["set"](window, "Math", replacement);',
        "Reflect.set(window, 'Math', replacement);",
        "Object.assign(window, {Math: replacement});",
    ],
)
def test_umd_factory_explicit_global_rebindings_are_recorded(body):
    source = UMD.replace("return function Widget(){};", body + "return function Widget(){};")
    publication = umd_publication("vendor.js", source.encode())
    assert publication is not None
    assert publication[2] is None or "Math" in publication[2]


@pytest.mark.parametrize(
    "body",
    [
        "let Math; Math = replacement;",
        "const window = {}; window.Math = replacement;",
        "const local = {}; local.Math = replacement;",
        "const local = ({}); (local).Math = replacement;",
        "const window = {}; (window).Math = replacement;",
        "const local = {}; local[key] = replacement;",
        "let root = window; root = {};",
        "window['namespace'][key] = replacement;",
    ],
)
def test_umd_factory_local_assignments_keep_bounded_writes(body):
    source = UMD.replace("return function Widget(){};", body + "return function Widget(){};")
    publication = umd_publication("vendor.js", source.encode())
    assert publication is not None and publication[0] == "Widget"
    assert publication[2] == frozenset()


@pytest.mark.parametrize(
    "body",
    [
        "touch();",
        "window.eval('Math = replacement');",
        "eval('Math = replacement');",
        "window['eval']('Math = replacement');",
        "window?.eval?.('Math = replacement');",
        "(window.eval)('Math = replacement');",
        "const run = window.eval; run('Math = replacement');",
        "const run = touch; (run)?.();",
        "new Function('Math = replacement');",
        "const Build = Function; new Build('Math = replacement');",
        "new window.Constructor();",
        "new (window.Constructor)();",
        "touch`Math = replacement`;",
        "function later(){ touch(); }",
        "const later = () => touch();",
        "(function(){ window.Math = replacement; })();",
        "Object.assign(window, {Other: replacement});",
        "Reflect['set']({}, 'Math', replacement);",
        "(Object['defineProperty'])({}, 'Math', {value: replacement});",
        "Object.assign({}, {Math: replacement});",
        "const Object = {assign: touch}; Object.assign(window, {Other: 1});",
        "Object.assign = touch; Object.assign(window, {Other: 1});",
        "const Reflect = {set: touch}; Reflect.set(window, 'Other', 1);",
        "Object.defineProperty({}, 'Other', descriptor);",
    ],
)
def test_umd_factory_unproved_calls_preserve_publication_but_not_namespace_proof(tmp_path, body):
    from archkeel.ir.facts import BuiltinTarget, ExternalPackageTarget, UnresolvedTarget

    source = UMD.replace("return function Widget(){};", body + "return function Widget(){};")
    publication = umd_publication("vendor.js", source.encode())
    assert publication is not None and publication[0] == "Widget"
    assert publication[2] is None
    _repository(tmp_path, source=source)
    (tmp_path / "main.js").write_text("Math.abs(-1); new Widget();")
    facts = _native(tmp_path, v4=True)
    assert facts.imports and all(isinstance(target, UnresolvedTarget) for target in facts.imports)
    assert not any(
        isinstance(target, BuiltinTarget | ExternalPackageTarget) for target in facts.imports
    )
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "body",
    [
        "window.Math = replacement;",
        "const root = window; root.Math = replacement;",
        "Math = replacement;",
        "delete window.Math;",
        "window.Math++;",
    ],
)
def test_umd_factory_direct_global_writes_keep_exact_names(body):
    source = UMD.replace("return function Widget(){};", body + "return function Widget(){};")
    publication = umd_publication("vendor.js", source.encode())
    assert publication is not None and publication[0] == "Widget"
    assert publication[2] == frozenset({"Math"})


def test_vendor_checkout_preserves_authenticated_bytes_with_autocrlf(tmp_path):
    import subprocess

    from archkeel.analyzer.typescript.config import Config, Options

    def git(*arguments):
        subprocess.run(
            ["git", "-c", "core.autocrlf=true", "-c", "core.safecrlf=false", *arguments],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    (tmp_path / ".gitattributes").write_bytes((ROOT / ".gitattributes").read_bytes())
    source = (ROOT / BUNDLE).read_bytes()
    for relative in (BUNDLE, LICENSE):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    git("add", "--", ".gitattributes", BUNDLE, LICENSE)
    (tmp_path / BUNDLE).unlink()
    (tmp_path / LICENSE).unlink()
    git("checkout-index", "--force", "--", BUNDLE, LICENSE)
    assert (tmp_path / BUNDLE).read_bytes() == source
    provider = ScriptProvider(BUNDLE, LICENSE)
    config = Config(Options(), (), False, ScriptHost.CLASSIC_BROWSER, (provider,))
    assert Resolver(Snapshot(str(tmp_path)), config).script_provider(provider) == ("elkjs", source)
    (tmp_path / BUNDLE).write_bytes(source.replace(b"\n", b"\r\n"))
    assert Resolver(Snapshot(str(tmp_path)), config).script_provider(provider) is None
