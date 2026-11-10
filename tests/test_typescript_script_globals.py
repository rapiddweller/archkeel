# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Browser-global dependencies use native evidence and keep unproved dispatch UNKNOWN."""

import json
from importlib import import_module

import pytest
from collector_pin import assembled, trusted
from test_architecture_demo import _prepare_repo
from test_source_graph import _graph_from_source_facts
from test_typescript_partial_uml import _TypeScriptCollector

from archkeel.analyzer.typescript.collect import collect
from archkeel.analyzer.typescript.parse import parse
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.check.uml_compare import compare_graphs
from archkeel.ir.architecture_graph import ArchitectureGraph, Entity, Relationship
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.facts import SOURCE_SCRIPT_GLOBAL_KIND, Language
from archkeel.ir.facts_validation import validate_source_facts
from archkeel.ir.protocol import CollectionRequest, SnapshotInput, SourceScope, TypeScriptSettings
from archkeel.ir.source_graph import observed_graph

SCENE = "var Scene = (function () { function create() {} return { create }; })();\n"
LAYOUT = "(function (global) { function layout() {} global.Layout = { layout }; })(window);\n"


def test_scope_names_are_reused_only_inside_one_parse(monkeypatch):
    parser = import_module("archkeel.analyzer.typescript.parse")
    original = parser._scope_names
    reads = {}

    def tracked(node):
        reads[node.id] = reads.get(node.id, 0) + 1
        return original(node)

    monkeypatch.setattr(parser, "_scope_names", tracked)
    outputs = []
    for binding in ("Scene", "Other", "Scene"):
        reads.clear()
        syntax = parser.parse(
            "source.js",
            (
                f"(function () {{ const {binding} = {{}}; function render() {{"
                "Scene.create(); Scene.create(); } render(); })();"
            ).encode(),
        )
        calls = [site for site in syntax.sites if site.expression == "Scene.create"]
        assert len(calls) == 2
        assert all(site.script_free is (binding != "Scene") for site in calls)
        assert reads and max(reads.values()) == 1
        outputs.append(syntax)
    assert outputs[0] == outputs[2]


def _collect(tmp_path, source=SCENE, consumer="Scene.create();", extra=""):
    (tmp_path / "src").mkdir(exist_ok=True)
    files = {"scene.js": source, "layout.js": LAYOUT, "consumer.js": consumer + extra}
    for name, text in files.items():
        (tmp_path / "src" / name).write_text(text)
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"allowJs": True}, "include": ["src"]})
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "browser"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    return facts


def _records(facts, name):
    return next(section.records for section in facts.sections if section.name == name)


def _native_graph(tmp_path, facts):
    contract = tmp_path / "contract.json"
    contract.write_text(
        json.dumps(
            {
                "schema_version": "2.2.0",
                "components": [
                    {
                        "id": "browser",
                        "label": "browser",
                        "role": "component",
                        "packages": ["browser.src"],
                        "responsibilities": ["Own the browser sources."],
                        "forbidden_responsibilities": [],
                        "provenance": ["target"],
                    }
                ],
                "rules": [],
            }
        )
    )
    model, _ = assembled(
        facts,
        contract_root=tmp_path,
        contract_path=contract,
        namespace="browser",
        language=Language.TYPESCRIPT,
    )
    return observed_graph(model)


@pytest.mark.parametrize(
    "consumer",
    [
        "Scene.create();",
        "window.Scene.create();",
        "globalThis.Scene.create();",
        "(function () { Scene.create(); })();",
    ],
)
def test_unique_actual_publication_resolves_call_and_truthful_dependency(tmp_path, consumer):
    facts = _collect(tmp_path, consumer=consumer)
    dependencies = _records(facts, "imports")
    assert len(facts.files) == 3 and facts.coverage.full_scope
    assert dependencies and all(row.kind == SOURCE_SCRIPT_GLOBAL_KIND for row in dependencies)
    dependency = next(
        row for row in dependencies if row.data.get("source_module").endswith("consumer_x2e_js")
    )
    assert dependency.data.get("target_module") == "browser.src.scene_x2e_js"
    assert dependency.data.get("symbols_known") is True
    assert dependency.data.get("symbol") == "create"
    call = next(
        row
        for row in _records(facts, "calls")
        if row.data.get("expression").endswith("Scene.create")
    )
    assert call.data.get("status") == "resolved"
    assert call.data.get("targets") == ("browser.src.scene_x2e_js.create",)
    graph = _graph_from_source_facts(facts, ("src",))
    relation = next(row for row in graph.relationships if row.id == dependency.id)
    assert relation.kind == "references"


@pytest.mark.parametrize(
    ("published", "member", "alias", "root"),
    [("Scene", "create", "port", "window"), ("Orbit", "build", "view", "globalThis")],
)
def test_read_only_alias_keeps_initializer_and_member_provenance(
    tmp_path, published, member, alias, root
):
    source = SCENE.replace("Scene", published).replace("create", member)
    consumer = (
        f"(function () {{\n  const {alias} = {root}.{published};\n"
        f"  function render() {{ {alias}.{member}(); }}\n  render();\n}})();"
    )
    facts = _collect(tmp_path, source=source, consumer=consumer)
    assert len(facts.files) == 3 and facts.coverage.full_scope
    [call] = [
        row for row in _records(facts, "calls") if row.data.get("expression") == f"{alias}.{member}"
    ]
    assert call.data.get("status") == "resolved"
    assert call.data.get("targets") == (f"browser.src.scene_x2e_js.{member}",)
    assert len(call.evidence_ids) == 2
    dependencies = [
        row
        for row in _records(facts, "imports")
        if row.data.get("source_module") == "browser.src.consumer_x2e_js"
    ]
    assert not any(row.data.get("symbol") is None for row in dependencies)
    [dependency] = [row for row in dependencies if row.data.get("symbol") == member]
    assert dependency.data.get("symbols_known") is True
    assert dependency.data.get("binding") == alias
    assert dependency.data.get("script_global") == published
    assert set(dependency.evidence_ids) == set(call.evidence_ids)
    assert dependency.fact_ids == call.fact_ids
    [initializer] = [
        row
        for row in _records(facts, "references")
        if row.data.get("expression") == f"{root}.{published}"
    ]
    assert initializer.fact_ids == call.fact_ids
    [binding] = [row for row in _records(facts, "bindings") if row.data.get("binding") == alias]
    assert len(binding.evidence_ids) >= 2
    [publication] = [
        row for row in _records(facts, "bindings") if row.data.get("script_global") == published
    ]
    assert call.fact_ids == (binding.id, publication.id)
    assert binding.fact_ids == (publication.id,)
    evidence = {item.id: item for item in facts.evidence}
    assert len(publication.evidence_ids) == 2
    assert all(evidence[item].file == "src/scene.js" for item in publication.evidence_ids)


def test_read_only_alias_uses_lexical_declarations_instead_of_shared_spelling(tmp_path):
    facts = _collect(
        tmp_path,
        consumer=(
            "(function () { const port = window.Scene;\n"
            "function other() { const port = window.Layout; port.layout(); }\n"
            "function shadow(port) { port.create = 7; }\n"
            "port.create(); other(); })();"
        ),
    )
    assert facts.coverage.full_scope
    calls = {
        row.data.get("expression"): row
        for row in _records(facts, "calls")
        if row.data.get("expression") in {"port.create", "port.layout"}
    }
    assert calls["port.create"].data.get("targets") == ("browser.src.scene_x2e_js.create",)
    assert calls["port.layout"].data.get("targets") == ("browser.src.layout_x2e_js.layout",)


def test_read_only_alias_does_not_resolve_a_factory_result_call(tmp_path):
    facts = _collect(tmp_path, consumer="const port = window.Scene; port.create()();")
    calls = {row.data.get("expression"): row for row in _records(facts, "calls")}
    assert calls["port.create"].data.get("status") == "resolved"
    assert calls["port.create()"].data.get("status") == "unresolved"
    assert not calls["port.create()"].fact_ids


FACTORY_SCENE = (
    "(function(){function create(){function entity(){} return {entity};} "
    "window.Scene={create};})();"
)


def test_factory_source_member_is_proven_without_claiming_runtime_dispatch(tmp_path):
    facts = _collect(
        tmp_path,
        source=FACTORY_SCENE,
        consumer="const port=window.Scene.create(); port.entity();",
    )
    dependencies = [
        row
        for row in _records(facts, "imports")
        if row.data.get("specifier") == "Scene"
        and row.data.get("source_module") == "browser.src.consumer_x2e_js"
    ]
    assert len(dependencies) == 2
    assert all(row.data.get("symbols_known") is True for row in dependencies)
    assert all(row.data.get("symbol") == "create" for row in dependencies)
    [call] = [
        row for row in _records(facts, "calls") if row.data.get("expression") == "port.entity"
    ]
    assert call.data.get("status") == "unresolved" and not call.data.get("targets")
    assert any(identity.startswith("SCRIPT_FACTORY_SOURCE-") for identity in call.fact_ids)


@pytest.mark.parametrize(
    "body",
    [
        "function entity(){} if(flag)return {entity}; return {entity};",
        "function entity(){} return flag ? {entity} : {};",
        "function entity(){} return {...other,entity};",
        "return {get entity(){return other;}};",
        "function entity(){} return {entity,entity};",
        "function entity(){} return {[key]:entity};",
        "return {entity}; const entity=()=>{};",
        "let entity=()=>{}; return {entity};",
        "const entity=()=>{}; entity=other; return {entity};",
        "function inner(entity){return {entity};} return inner(other);",
    ],
)
def test_unproved_factory_returns_keep_source_member_unknown(tmp_path, body):
    source = f"(function(){{function create(){{{body}}} window.Scene={{create}};}})();"
    facts = _collect(
        tmp_path, source=source, consumer="const port=window.Scene.create(); port.entity();"
    )
    [dependency] = [
        row
        for row in _records(facts, "imports")
        if row.data.get("binding") == "port"
        and row.data.get("script_member") == "create"
        and any(identity.startswith("SCRIPTALIAS-") for identity in row.fact_ids)
        and any(evidence for evidence in row.evidence_ids)
        and row.data.get("symbols_known") is False
    ]
    assert dependency.data.get("target_module") == "browser.src.scene_x2e_js"
    assert any("not statically published" in gap.title for gap in facts.coverage.gaps)


@pytest.mark.parametrize("prefix", ["Flow", "window.Flow", "globalThis.Flow"])
def test_selected_cross_file_escape_member_rebinding_invalidates_factory_proof(tmp_path, prefix):
    consumer = "const port=window.Scene.create(); window.Flow={reportScene:port}; port.entity();"
    _collect(tmp_path, source=FACTORY_SCENE, consumer=consumer)
    (tmp_path / "src/mutator.js").write_text(
        f"{prefix}.reportScene.entity=function replacement(){{}};"
    )
    facts = _collect(tmp_path, source=FACTORY_SCENE, consumer=consumer)
    assert any(
        row.data.get("binding") == "port" and row.data.get("symbols_known") is False
        for row in _records(facts, "imports")
    )
    assert any("not statically published" in gap.title for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "mutator",
    [
        "const F=window.Flow; F.reportScene.entity=replacement;",
        "const F=globalThis.Flow; F.reportScene.entity=replacement;",
        "const A=window.Flow; const F=A; F.reportScene.entity=replacement;",
        "const F=window.Flow; const P=F.reportScene; P.entity=replacement;",
        "function write(){const F=window.Flow; F.reportScene.entity=replacement;} write();",
    ],
)
def test_lexical_alias_writes_cannot_hide_alternative_factory_member_source(tmp_path, mutator):
    consumer = "const port=window.Scene.create(); window.Flow={reportScene:port}; port.entity();"
    _collect(tmp_path, source=FACTORY_SCENE, consumer=consumer)
    (tmp_path / "src/mutator.js").write_text(mutator)
    facts = _collect(tmp_path, source=FACTORY_SCENE, consumer=consumer)
    assert any(
        row.data.get("binding") == "port" and row.data.get("symbols_known") is False
        for row in _records(facts, "imports")
    )


@pytest.mark.parametrize("root", ["window", "globalThis"])
def test_same_file_explicit_global_namespace_rebinding_is_not_a_stable_port(tmp_path, root):
    facts = _collect(
        tmp_path, source=NAMESPACE + f"{root}.Vocabulary=other;", consumer="Vocabulary;"
    )
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)
    assert not any(
        row.data.get("symbol") == "Vocabulary" and row.data.get("symbols_known") is True
        for row in _records(facts, "imports")
    )


def test_opaque_runtime_effect_retains_direct_source_binding_and_own_gap(tmp_path):
    facts = _collect(tmp_path, source=SCENE, consumer="eval(code); Scene.create();")
    [dependency] = [
        row for row in _records(facts, "imports") if row.data.get("specifier") == "Scene"
    ]
    assert dependency.data.get("symbols_known") is True
    [call] = [
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    ]
    assert call.data.get("status") == "unresolved"
    effects = [
        gap
        for gap in facts.coverage.gaps
        if gap.data.get("resolution_dimension") == "runtime_effects"
    ]
    assert effects and all(gap.fact_ids for gap in effects)


@pytest.mark.parametrize(
    "use", ["", "port.create(); port[key]();", "consume(port); port.create();"]
)
def test_alias_decomposition_never_discards_unused_or_unbounded_source_dependency(tmp_path, use):
    facts = _collect(tmp_path, consumer=f"const port=window.Scene; {use}")
    assert any(
        row.data.get("specifier") == "Scene" and row.data.get("symbols_known") is False
        for row in _records(facts, "imports")
    )


NAMESPACE = (
    "var Vocabulary; (function(Vocabulary){Vocabulary.kind='data';})(Vocabulary||(Vocabulary={}));"
)


def test_native_namespace_port_is_bound_to_declaration_and_initialization(tmp_path):
    facts = _collect(tmp_path, source=NAMESPACE, consumer="const schema=Vocabulary;")
    [dependency] = [
        row for row in _records(facts, "imports") if row.data.get("specifier") == "Vocabulary"
    ]
    assert dependency.data.get("symbols_known") is True
    assert dependency.data.get("symbol") == "Vocabulary"
    assert dependency.data.get("target_module") == "browser.src.scene_x2e_js"
    [proof] = [row for row in _records(facts, "bindings") if row.id in dependency.fact_ids]
    assert proof.data.get("script_namespace") == "Vocabulary"
    assert len(proof.evidence_ids) == 2
    evidence = {row.id: row for row in facts.evidence}
    assert all(evidence[item].file == "src/scene.js" for item in proof.evidence_ids)
    assert not any(row.data.get("name") == "Vocabulary" for row in _records(facts, "symbols"))


@pytest.mark.parametrize(
    "source",
    [
        NAMESPACE.replace("var Vocabulary;", ""),
        NAMESPACE.replace("function(Vocabulary)", "function(other)"),
        NAMESPACE.replace("Vocabulary||(Vocabulary={})", "Vocabulary||(other={})"),
        NAMESPACE.replace("var Vocabulary;", "let Vocabulary;"),
        NAMESPACE.replace("function(Vocabulary)", "async function(Vocabulary)"),
        NAMESPACE + " Vocabulary=other;",
        NAMESPACE + NAMESPACE,
        "var Vocabulary={};",
    ],
)
def test_unproved_namespace_envelopes_keep_imports_unknown(tmp_path, source):
    facts = _collect(tmp_path, source=source, consumer="const schema=Vocabulary;")
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)
    assert not any(
        row.data.get("symbol") == "Vocabulary" and row.data.get("symbols_known") is True
        for row in _records(facts, "imports")
    )


def test_other_selected_file_cannot_rebind_a_namespace_port(tmp_path):
    _collect(tmp_path, source=NAMESPACE, consumer="const schema=Vocabulary;")
    (tmp_path / "src/mutator.js").write_text("Vocabulary=other;")
    facts = _collect(tmp_path, source=NAMESPACE, consumer="const schema=Vocabulary;")
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize("root", ["globalThis", "window"])
@pytest.mark.parametrize("writer", ["consumer", "publisher", "separate"])
def test_rebound_global_root_cannot_prove_namespace_binding(tmp_path, root, writer):
    consumer = f"{root}.Vocabulary;"
    source = NAMESPACE
    if writer == "consumer":
        consumer = f"{root}={{}};" + consumer
    elif writer == "publisher":
        source += f"{root}={{}};"
    else:
        _collect(tmp_path, source=source, consumer=consumer)
        (tmp_path / "src/mutator.js").write_text(f"{root}={{}};")
    facts = _collect(tmp_path, source=source, consumer=consumer)
    [dependency] = [
        row
        for row in _records(facts, "imports")
        if row.data.get("source_module") == "browser.src.consumer_x2e_js"
        and row.data.get("specifier") == "Vocabulary"
    ]
    assert dependency.data.get("symbols_known") is False
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


def test_guarded_publication_proves_only_source_origin_and_retains_guard_effect(tmp_path):
    source = "(function(){if(!root)return; function create(){} window.Scene={create};})();"
    facts = _collect(tmp_path, source=source, consumer="const scene=window.Scene;")
    [dependency] = [
        row
        for row in _records(facts, "imports")
        if row.data.get("source_module") == "browser.src.consumer_x2e_js"
    ]
    assert dependency.data.get("target_module") == "browser.src.scene_x2e_js"
    assert dependency.data.get("symbols_known") is False
    assert any(item.startswith("SCRIPTPUBLICATION-") for item in dependency.fact_ids)
    evidence = {row.id: row for row in facts.evidence}
    assert any(
        gap.data.get("resolution_dimension") == "runtime_effects"
        and any("if(!root)return" in evidence[item].excerpt for item in gap.evidence_ids)
        for gap in facts.coverage.gaps
    )


@pytest.mark.parametrize("extra", ["window.Scene={};", "Scene=other;"])
def test_guarded_source_origin_rejects_selected_alternative_bindings(tmp_path, extra):
    source = "(function(){if(!root)return; window.Scene={};})();" + extra
    facts = _collect(tmp_path, source=source, consumer="const scene=window.Scene;")
    assert any(gap.data.get("resolution_dimension") == "imports" for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "consumer",
    [
        "let port = window.Scene; port.create();",
        "const port = window.Scene.create(); port.create();",
        "const port = window.Scene; const copy = port; port.create();",
        "const port = window.Scene; mutate(port); port.create();",
        "const port = window.Scene; const values = [port]; port.create();",
        "const port = window.Scene; const values = {...port}; port.create();",
        "const port = window.Scene; port.create = () => {}; port.create();",
        "const port = window.Scene; [port.create] = [() => {}]; port.create();",
        "const port = window.Scene; for (port.create of []) {} port.create();",
        "const port = window.Scene; port.create++; port.create();",
        "const port = window.Scene; delete port.create; port.create();",
        "const port = window.Scene; port['create'](); port.create();",
        "const port = window.Scene; port?.create(); port.create();",
        "const port = window.Scene; port.create?.(); port.create();",
        "const port = window?.Scene; port.create();",
        "const port = window.Scene; const method = port.create; port.create();",
        "const port = window.Scene; function expose() { return port; } port.create();",
        "const port = window.Scene; Reflect.set(port, 'create', () => {}); port.create();",
        r"const port = window.Scene; \u0070ort.create = () => {}; port.create();",
        "const window = {}; const port = window.Scene; port.create();",
        "const port = window.Scene; function render(port) { port.create(); }",
        "const port = window.Scene; { const {port} = {}; port.create(); }",
    ],
)
def test_unproven_alias_reads_or_writes_do_not_resolve_the_receiver(tmp_path, consumer):
    facts = _collect(tmp_path, consumer=consumer)
    calls = [row for row in _records(facts, "calls") if row.data.get("expression") == "port.create"]
    assert calls and all(row.data.get("status") != "resolved" for row in calls)
    assert len(facts.files) == 3


@pytest.mark.parametrize(
    "source",
    [
        SCENE + SCENE,
        SCENE.replace("return { create };", "if (flag) return {}; return { create };"),
        SCENE.replace("return { create };", "return {};"),
        SCENE + "window.Scene.create = replacement;",
    ],
)
def test_read_only_alias_cannot_repair_an_unproven_publication(tmp_path, source):
    facts = _collect(tmp_path, source=source, consumer="const port = window.Scene; port.create();")
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "port.create"
    )
    assert call.data.get("status") != "resolved"
    assert facts.coverage.gaps and len(facts.files) == 3


@pytest.mark.parametrize(
    ("path", "source"),
    [
        ("consumer.ts", "const port = window.Scene; port.create();"),
        ("consumer.js", "export {}; const port = window.Scene; port.create();"),
    ],
)
def test_read_only_alias_proof_applies_only_to_javascript_scripts(path, source):
    assert not parse(path, source.encode()).script_aliases


def test_script_namespace_coverage_follows_the_existing_module_mode(tmp_path):
    _collect(tmp_path, consumer='eval("Scene.create = 7");')
    (tmp_path / "tsconfig.json").write_text(
        json.dumps(
            {
                "compilerOptions": {
                    "allowJs": True,
                    "module": "node16",
                    "moduleResolution": "node16",
                },
                "include": ["src"],
            }
        )
    )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "browser"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    assert "script-globals-v1" not in facts.capabilities.resolution_features
    assert facts.coverage.full_scope


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize(
    "effect",
    [
        'eval("Scene.create = function other() {}");',
        r'\u0065val("Scene.create = function other() {}");',
        '(0, eval)("Scene.create = function other() {}");',
        'const execute = eval; execute("Scene.create = function other() {}");',
        'globalThis.eval("Scene.create = function other() {}");',
        'globalThis["eval"]("Scene.create = function other() {}");',
        'Function("Scene.create = function other() {}")();',
        r'\u0046unction("Scene.create = function other() {}")();',
        '(function () {}).constructor("Scene.create = function other() {}")();',
        '(function () {})["constructor"]("Scene.create = function other() {}")();',
        r'const execute = (function () {})["con\x73tructor"]; execute("Scene.create = 7")();',
        'function harmless() {} harmless["con" + "structor"].call(null, "Scene.create = 7")();',
        'function harmless() {} const key = "constructor"; '
        'harmless[key].bind(null, "Scene.create = 7")()();',
        'const {["con" + "structor"]: execute} = function () {}; execute("Scene.create = 7")();',
        r'const {"con\x73tructor": execute} = function () {}; execute("Scene.create = 7")();',
        'const {"constructor": execute} = function () {}; execute("Scene.create = 7")();',
        r'const execute = (function () {})[`con\x73tructor`]; execute("Scene.create = 7")();',
        "const key = getKey(); const execute = (function () {})[key]; "
        'execute("Scene.create = 7")();',
        "const key = getKey(); function maker() {} const execute = maker[key]; "
        'execute("Scene.create = 7")();',
        "const key = getKey(); const maker = function () {}; const execute = maker[key]; "
        'execute("Scene.create = 7")();',
        "const key = getKey(); const maker = () => {}; const execute = maker[key]; "
        'execute("Scene.create = 7")();',
        "const key = getKey(); class Maker {} const execute = Maker[key]; "
        'execute("Scene.create = 7")();',
        "const key = getKey(); const Maker = class {}; const execute = Maker[key]; "
        'execute("Scene.create = 7")();',
        "const values = []; const key = getKey(); values[key]();",
        "const values = []; const key = getKey(); new values[key]();",
        'Reflect.get(globalThis, "eval")("Scene.create = function other() {}");',
        'Object.getOwnPropertyDescriptor(globalThis, "eval").value("Scene.create = 7");',
        'const execute = globalThis[key]; execute("Scene.create = 7");',
        'const namespace = this; namespace.eval("Scene.create = 7");',
        'setTimeout("Scene.create = function other() {}", 0);',
        'const execute = setInterval; execute("Scene.create = 7", 0);',
    ],
)
def test_dynamic_namespace_access_retracts_direct_and_alias_targets(tmp_path, alias, effect):
    receiver = "port" if alias else "Scene"
    consumer = ("const port = window.Scene;\n" if alias else "") + effect
    consumer += f"\n{receiver}.create(); {receiver}.create();"
    facts = _collect(tmp_path, consumer=consumer)
    calls = [
        row
        for row in _records(facts, "calls")
        if row.data.get("expression") == f"{receiver}.create"
    ]
    assert len(calls) == 2 and all(row.data.get("status") == "unresolved" for row in calls)
    assert not facts.coverage.full_scope and facts.coverage.gaps
    assert len(facts.files) == 3


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize(
    "body",
    [
        "return data[index];",
        "const selected = data[index]; return selected;",
        "return consume(data[index]);",
        "return data[index].value;",
        "const points = [[1, 2]]; const mid = points[index]; return mid[0];",
    ],
)
def test_data_index_reads_preserve_declared_port_binding(tmp_path, alias, body):
    source = SCENE.replace(
        "function create() {}",
        f"function consume(value) {{ return value; }} function create(data, index) {{ {body} }}",
    )
    consumer = "const port = window.Scene; port.create([], 0);" if alias else "Scene.create([], 0);"
    facts = _collect(tmp_path, source=source, consumer=consumer)
    expression = "port.create" if alias else "Scene.create"
    [call] = [row for row in _records(facts, "calls") if row.data.get("expression") == expression]
    assert call.data.get("status") == "resolved"
    assert call.data.get("targets") == ("browser.src.scene_x2e_js.create",)
    assert len(facts.files) == facts.coverage.files_read == facts.coverage.files_parsed == 3
    assert not any(
        gap.title == "Script namespace effects are not statically bounded"
        for gap in facts.coverage.gaps
    )


@pytest.mark.parametrize("alias", [False, True])
@pytest.mark.parametrize(
    "body",
    [
        "mutate(this);",
        "mutate({value: this});",
        "const receiver = this; mutate(receiver);",
        "return this;",
        "const read = () => this; mutate(read());",
        "Reflect.apply(mutate, null, [this]);",
        "mutate.bind(null, this)();",
        "this.value;",
    ],
)
def test_unproved_published_receiver_retracts_direct_and_alias_targets(tmp_path, alias, body):
    source = "function mutate(object) { object.create = function other() {}; }\n" + SCENE.replace(
        "function create() {}", f"function create() {{ {body} }}"
    )
    receiver = "port" if alias else "Scene"
    consumer = "const port = window.Scene;\n" if alias else ""
    consumer += f"{receiver}.create(); {receiver}.create();"
    facts = _collect(tmp_path, source=source, consumer=consumer)
    calls = [
        row
        for row in _records(facts, "calls")
        if row.data.get("expression") == f"{receiver}.create"
    ]
    assert len(calls) == 2 and all(row.data.get("status") == "unresolved" for row in calls)
    assert not facts.coverage.full_scope and facts.coverage.gaps
    assert len(facts.files) == 3


def test_unrelated_receiver_scopes_and_intrinsic_declaration_names_do_not_capture_publication(
    tmp_path,
):
    source = SCENE.replace(
        "function create() {}",
        "function create() { function nested() { return this.value; } }",
    )
    facts = _collect(
        tmp_path,
        source=source,
        consumer="function eval(value) { return value; }\n"
        "class Holder { constructor() {} method() { return this.value; } }\n"
        "const port = window.Scene; port.create();",
    )
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "port.create"
    )
    assert call.data.get("status") == "resolved" and facts.coverage.full_scope


def test_inline_timer_callback_does_not_assert_dynamic_string_execution(tmp_path):
    facts = _collect(
        tmp_path,
        consumer="setTimeout(() => {}, 0); const port = window.Scene; port.create();",
    )
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "port.create"
    )
    assert call.data.get("status") == "resolved"
    assert not any("namespace effects" in gap.title for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "extra",
    [
        "Scene.create = replacement;",
        "window.Scene = replacement;",
        "window[key] = replacement;",
        "Scene[key] = replacement;",
        "delete Scene.create;",
        "delete window.Scene;",
        "Object.assign(Scene, replacement);",
        "var Scene = replacement;",
        "const alias = Scene; alias.create = () => {};",
        "const alias = window.Scene; alias.create = () => {};",
        "const alias = window; alias.Scene.create = () => {};",
        "(function (global) { const alias = global; alias.Scene.create = () => {}; })(window);",
        "[Scene.create] = [() => {}];",
        "({create: Scene.create} = {create: () => {}});",
        "for (Scene.create of [() => {}]) {}",
        "for (Scene.create in {x: 1}) {}",
        "Scene.create++;",
        "[...Scene.create] = [];",
        "[Scene.create = () => {}] = [];",
    ],
)
def test_rewritten_or_computed_global_is_not_static_proof(tmp_path, extra):
    facts = _collect(tmp_path, extra=extra)
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("status") == "unresolved"
    assert not facts.coverage.full_scope
    assert facts.coverage.gaps


@pytest.mark.parametrize(
    ("consumer", "expression"),
    [
        ("Scene.create();", "Scene.create"),
        ("const port = window.Scene; port.create();", "port.create"),
    ],
)
def test_selected_es_module_global_write_invalidates_script_publication(
    tmp_path, consumer, expression
):
    _collect(tmp_path, consumer=consumer)
    (tmp_path / "src/mutator.js").write_text("export {}; window.Scene.create = () => {};\n")
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "browser"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    call = next(row for row in _records(facts, "calls") if row.data.get("expression") == expression)
    assert call.data.get("status") == "unresolved"
    assert not facts.coverage.full_scope


@pytest.mark.parametrize(
    "consumer",
    [
        "(function () { const {Scene} = {}; Scene.create(); })();",
        "(function () { let {key: Scene = {}} = {}; Scene.create(); })();",
        "(function () { const [Scene, ...rest] = []; Scene.create(); })();",
        "(function () { var {Scene} = {}; Scene.create(); })();",
        "function use({Scene}) { Scene.create(); }",
        "function* use({Scene}) { Scene.create(); }",
        "const use = ({Scene}) => Scene.create();",
        "const use = Scene => Scene.create();",
        "const use = function Scene() { Scene.create(); };",
        "const use = function* Scene() { Scene.create(); };",
        "try {} catch ({Scene}) { Scene.create(); }",
        "for (const {Scene} of []) { Scene.create(); }",
        "for (let Scene in {}) { Scene.create(); }",
        "for (let {Scene} = {}; false;) { Scene.create(); }",
        "class Holder { method({Scene}) { Scene.create(); } }",
        "class Holder { static { var {Scene} = {}; Scene.create(); } }",
        "const Holder = class Scene { method() { Scene.create(); } };",
        "{ class Scene {} Scene.create(); }",
        "switch (0) { case 0: const {Scene} = {}; Scene.create(); }",
        "(function () { if (true) { function Scene() {} } Scene.create(); })();",
        "(function () { if (true) function Scene() {} Scene.create(); })();",
    ],
)
def test_script_receiver_bindings_cover_lexical_positions(consumer):
    syntax = parse("consumer.js", consumer.encode())
    calls = [site for site in syntax.sites if site.path == ("Scene", "create")]
    assert calls and all(not site.script_free for site in calls)
    assert not syntax.concerns


@pytest.mark.parametrize(
    "consumer",
    [
        "{ const {Scene} = {}; } Scene.create();",
        "for (let Scene of []) {} Scene.create();",
        "try {} catch ({Scene}) {} Scene.create();",
        "class Holder { static { var Scene = {}; } } Scene.create();",
        "const Holder = class Scene {}; Scene.create();",
        "const {Scene: local = 0} = {}; Scene.create();",
        "const {local = Scene.create()} = {};",
    ],
)
def test_script_bindings_do_not_capture_keys_defaults_or_outer_scopes(consumer):
    syntax = parse("consumer.js", consumer.encode())
    calls = [site for site in syntax.sites if site.path == ("Scene", "create")]
    assert calls and all(site.script_free for site in calls)
    assert not syntax.concerns


@pytest.mark.parametrize(
    "source",
    [
        rb"const \u0053cene = {}; Scene.create();",
        rb"const \u{53}cene = {}; Scene.create();",
        rb"const {\u0053cene} = {}; Scene.create();",
        rb"function use(\u0053cene) { Scene.create(); }",
    ],
)
def test_escaped_binding_spelling_is_an_explicit_unproved_scope(source):
    syntax = parse("consumer.js", source)
    call = next(site for site in syntax.sites if site.path == ("Scene", "create"))
    assert not call.script_free
    assert any("binding" in concern.reason.lower() for concern in syntax.concerns)


def test_literal_unicode_binding_keeps_its_lexical_identity():
    syntax = parse("consumer.js", "const Scène = {}; Scène.create();".encode())
    call = next(site for site in syntax.sites if site.path == ("Scène", "create"))
    assert not call.script_free
    assert not syntax.concerns


def test_shorthand_shadow_does_not_resolve_to_selected_global_publisher(tmp_path):
    facts = _collect(
        tmp_path,
        consumer="(function () { const {Scene} = {Scene: {create() {}}}; Scene.create(); })();",
    )
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("targets") != ("browser.src.scene_x2e_js.create",)


def test_dynamic_with_scope_cannot_prove_a_global_receiver(tmp_path):
    facts = _collect(tmp_path, consumer="with ({}) { Scene.create(); }")
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("targets") != ("browser.src.scene_x2e_js.create",)
    assert not facts.coverage.full_scope
    assert any("binding" in gap.title.lower() for gap in facts.coverage.gaps)


@pytest.mark.parametrize(
    "source",
    [
        "(function () { const window = {}; function create() {} window.Scene = {create}; })();",
        "(function () { const globalThis = {}; function create() {} "
        "globalThis.Scene = {create}; })();",
        "const window = {}; (function (global) { function create() {} "
        "global.Scene = {create}; })(window);",
        "(function (global) { var global = {}; function create() {} "
        "global.Scene = {create}; })(window);",
        "(function (window) { function create() {} window.Scene = {create}; })({});",
    ],
)
def test_shadowed_publication_receiver_does_not_publish_a_browser_global(tmp_path, source):
    facts = _collect(tmp_path, source=source)
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("targets") != ("browser.src.scene_x2e_js.create",)
    assert not facts.coverage.full_scope


@pytest.mark.parametrize("root", ["window", "globalThis"])
def test_iife_parameter_publication_requires_an_actual_free_global_argument(tmp_path, root):
    facts = _collect(
        tmp_path,
        source="(function (global) { function create() {} "
        f"global.Scene = {{create}}; }})({root});",
    )
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("targets") == ("browser.src.scene_x2e_js.create",)
    assert facts.coverage.full_scope


@pytest.mark.parametrize(
    "source",
    [
        SCENE + SCENE,
        SCENE.replace("return { create };", "if (flag) return {}; return { create };"),
        SCENE.replace("return { create };", "return { create: missing };"),
        SCENE.replace("return { create };", "return { other: create };"),
        SCENE.replace("var Scene", "const Scene"),
        "export {};\n" + SCENE,
    ],
)
def test_ambiguous_missing_conditional_and_module_local_publications_do_not_resolve(
    tmp_path, source
):
    facts = _collect(tmp_path, source=source)
    call = next(
        row for row in _records(facts, "calls") if row.data.get("expression") == "Scene.create"
    )
    assert call.data.get("status") != "resolved"
    assert len(facts.files) == 3


@pytest.mark.parametrize(
    "consumer", ["Scene.create();", "const port = window.Scene; port.create();"]
)
def test_native_required_call_keeps_missing_publication_unknown(tmp_path, consumer):
    target = ArchitectureGraph(
        "declared",
        (
            Entity(
                "consumer",
                "module",
                "browser.src.consumer_x2e_js",
                "typescript",
                presence="planned",
                provenance=("target",),
            ),
            Entity(
                "scene",
                "module",
                "browser.src.scene_x2e_js",
                "typescript",
                presence="planned",
                provenance=("target",),
            ),
            Entity(
                "create",
                "function",
                "browser.src.scene_x2e_js.create",
                "typescript",
                parent_id="scene",
                presence="planned",
                provenance=("target",),
            ),
        ),
        (Relationship("required-call", "calls", "consumer", "create", provenance=("target",)),),
    )
    valid = _collect(tmp_path, consumer=consumer)
    actual = _native_graph(tmp_path, valid)
    assert (
        next(
            row
            for row in compare_graphs(actual, target).assessments
            if row.subject_id == "required-call"
        ).status
        == "PASS"
    )
    missing = _collect(
        tmp_path, source=SCENE.replace("return { create };", "return {};"), consumer=consumer
    )
    actual = _native_graph(tmp_path, missing)
    assert (
        next(
            row
            for row in compare_graphs(actual, target).assessments
            if row.subject_id == "required-call"
        ).status
        == "UNKNOWN"
    )


@pytest.mark.parametrize(
    ("mutation", "expected", "files"),
    [
        ("component", "FAIL", 3),
        ("member", "FAIL", 3),
        ("publication", "UNKNOWN", 3),
        ("file", "UNKNOWN", 2),
        ("object-alias", "UNKNOWN", 3),
    ],
)
@pytest.mark.parametrize("alias", [False, True])
def test_native_complete_requires_rejects_drift_and_missing_actual_globals(
    tmp_path, mutation, expected, files, alias
):
    components = []
    for name in ("consumer", "scene", "layout"):
        components.append(
            {
                "id": name,
                "label": name,
                "role": "component",
                "packages": [],
                "exact_modules": [f"browser.src.{name}_x2e_js"],
                "requires": [
                    {
                        "component": "scene",
                        "through": ["browser.src.scene_x2e_js:create"],
                        "rationale": "Use scene projection.",
                    }
                ]
                if name == "consumer"
                else [],
                "responsibilities": [f"Own {name}."],
                "forbidden_responsibilities": [],
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        )
    contract = {
        "schema_version": "2.2.0",
        "components": components,
        "rules": [
            {
                "id": "browser-ports",
                "kind": "complete_requires",
                "rationale": "Use only declared browser boundaries.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    }
    root = _prepare_repo(
        tmp_path,
        {
            "src/scene.js": SCENE.replace(
                "function create() {}", "function create() {} function hidden() {}"
            ).replace("return { create }", "return { create, hidden }"),
            "src/layout.js": LAYOUT,
            "src/consumer.js": "const port = window.Scene; port.create();\n"
            if alias
            else "Scene.create();\n",
            "tsconfig.json": json.dumps({"compilerOptions": {"allowJs": True}, "include": ["src"]}),
            "contract.json": json.dumps(contract),
            "docs/target.md": "Browser boundary intent.\n",
        },
    )
    config = ScanConfig(("src",), "browser", "contract.json", "unused", language="typescript")

    def run():
        result, artifact = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
        assert artifact is not None, result.diagnostics
        return result, parse_observation(decode_canonical_model(json.loads(artifact)))

    valid, model = run()
    assert next(row for row in valid.rule_assessments if row.id == "browser-ports").status == "PASS"
    assert model.coverage.files_discovered == 3
    intent = (root / "contract.json").read_bytes()
    if mutation == "component":
        (root / "src/consumer.js").write_text(
            "const port = window.Layout; port.layout();\n"
            if alias
            else "Scene.create(); Layout.layout();\n"
        )
    elif mutation == "member":
        (root / "src/consumer.js").write_text(
            "const port = window.Scene; port.hidden();\n" if alias else "Scene.hidden();\n"
        )
    elif mutation == "publication":
        (root / "src/scene.js").write_text("function create() {}\n")
    elif mutation == "file":
        (root / "src/scene.js").unlink()
    else:
        (root / "src/consumer.js").write_text("const alias = Scene; alias.create();\n")
    invalid, model = run()
    assert (
        next(row for row in invalid.rule_assessments if row.id == "browser-ports").status
        == expected
    )
    assert model.coverage.files_discovered == files
    assert (root / "contract.json").read_bytes() == intent


def test_classic_data_reads_preserve_source_bound_publication_and_member_witnesses(tmp_path):
    import hashlib

    files = {
        "src/scene.js": (
            b"var ArchkeelGraphScene = (function () { function create(data) {"
            b"return data.nodes; } return { create }; })();"
        ),
        "src/layout.js": (
            b"(function (global) { function layout(data) { return data.nodes; }"
            b"function decodeLayout() {} function buildAtlasGraph() {} function layoutUml() {}"
            b"function layoutAtlas() {} function routeUmlRelationships() {}"
            b"function hasCompleteManualPositions() {}"
            b"global.ArchkeelReportLayout = { layout, decodeLayout, buildAtlasGraph, layoutUml,"
            b"layoutAtlas, routeUmlRelationships, hasCompleteManualPositions }; })(window);"
        ),
        "src/consumer.js": (
            b"ArchkeelGraphScene.create({}); window.ArchkeelReportLayout.layout({});"
            b"window.MissingData.value;"
        ),
    }
    (tmp_path / "src").mkdir()
    for path, content in files.items():
        (tmp_path / path).write_bytes(content)
    (tmp_path / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"allowJs": True}, "include": ["src"]})
    )
    for path, name, members in (
        ("src/scene.js", "ArchkeelGraphScene", {"create"}),
        (
            "src/layout.js",
            "ArchkeelReportLayout",
            {
                "layout",
                "decodeLayout",
                "buildAtlasGraph",
                "layoutUml",
                "layoutAtlas",
                "routeUmlRelationships",
                "hasCompleteManualPositions",
            },
        ),
    ):
        syntax = parse(path, files[path])
        [publication] = syntax.script_globals
        assert publication.name == name and publication.stable
        assert {published for published, _, _ in publication.members} == members
        assert publication.span.excerpt in files[path].decode()
        assert all(
            any(item.name == local and item.span == span for item in syntax.definitions)
            for _, local, span in publication.members
        )
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("src",), "browser"),
            TypeScriptSettings(),
        )
    )
    validate_source_facts(facts)
    assert {item.rel_path for item in facts.files} == set(files)
    assert set(facts.coverage.selected_files) == set(files)
    assert facts.coverage.files_read == facts.coverage.files_parsed == 3
    digests = {item.path: item.digest for item in facts.inputs}
    for path, content in files.items():
        assert (tmp_path / path).read_bytes() == content
        assert digests[path] == hashlib.sha256(content).hexdigest()
    for expression, target in (
        ("ArchkeelGraphScene.create", "browser.src.scene_x2e_js.create"),
        ("window.ArchkeelReportLayout.layout", "browser.src.layout_x2e_js.layout"),
    ):
        [call] = [
            row for row in _records(facts, "calls") if row.data.get("expression") == expression
        ]
        assert call.data.get("status") == "resolved" and call.data.get("targets") == (target,)
    dependency = next(
        row
        for row in _records(facts, "imports")
        if row.data.get("source_module") == "browser.src.consumer_x2e_js"
        and row.data.get("symbol") == "create"
    )
    assert dependency.data.get("symbol") == "create"
    assert dependency.data.get("symbols_known") is True
    assert not facts.coverage.full_scope
    assert not any(
        gap.title == "Script namespace effects are not statically bounded"
        for gap in facts.coverage.gaps
    )


@pytest.mark.parametrize(
    "consumer,provider,expected",
    [
        (
            "import {create as alias} from './scene.js'; alias();",
            "export function create() {}",
            "PASS",
        ),
        ("import {hidden} from './scene.js'; hidden();", "export function hidden() {}", "FAIL"),
        ("import {create} from './scene.js'; create();", "function create() {}", "UNKNOWN"),
        ("import {create} from './scene.js'; create();", None, "UNKNOWN"),
        (
            "import * as ns from './scene.js'; ns.create();",
            "export function create() {}",
            "UNKNOWN",
        ),
        (
            "export {}; const root = window; root.Scene.search();",
            "export function create() {}",
            "UNKNOWN",
        ),
        ("export {}; window['Scene']['search']();", "export function create() {}", "UNKNOWN"),
    ],
)
def test_named_esm_boundary_permissions_require_source_export_evidence(
    tmp_path, consumer, provider, expected
):
    components = [
        {
            "id": name,
            "label": name,
            "role": "component",
            "packages": [],
            "exact_modules": [f"browser.src.{name}_x2e_js"],
            "requires": [
                {
                    "component": "scene",
                    "through": ["browser.src.scene_x2e_js:create"],
                    "rationale": "Use the declared source port.",
                }
            ]
            if name == "consumer"
            else [],
            "responsibilities": [f"Own {name}."],
            "forbidden_responsibilities": [],
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
        for name in ("consumer", "scene")
    ]
    contract = {
        "schema_version": "2.2.0",
        "components": components,
        "rules": [
            {
                "id": "ports",
                "kind": "complete_requires",
                "rationale": "Bound imports.",
                "provenance": ["docs/target.md"],
                "decided_by": "architect",
            }
        ],
    }
    files = {
        "src/consumer.js": consumer,
        "tsconfig.json": json.dumps(
            {
                "compilerOptions": {
                    "allowJs": True,
                    "module": "esnext",
                    "moduleResolution": "node",
                },
                "include": ["src"],
            }
        ),
        "contract.json": json.dumps(contract),
        "docs/target.md": "Boundary intent.\n",
    }
    if provider is not None:
        files["src/scene.js"] = provider
    root = _prepare_repo(tmp_path, files)
    config = ScanConfig(("src",), "browser", "contract.json", "unused", language="typescript")
    result, artifact = run_report(root, config=config, analyzer=trusted(_TypeScriptCollector()))
    assert artifact is not None, result.diagnostics
    [assessment] = result.rule_assessments
    assert assessment.status == expected
    if expected != "UNKNOWN":
        assert assessment.evaluation_proven
        assert assessment.undecided == 0
    assert (root / "contract.json").read_text() == json.dumps(contract)
