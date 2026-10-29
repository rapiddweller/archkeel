# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""External binding receipts retain source scope and fail closed on changed inputs."""

import abc
import ast
import hashlib
import json
import subprocess
import sys
import sysconfig
import time
import zlib
from collections import Counter
from dataclasses import replace
from importlib.machinery import (
    BYTECODE_SUFFIXES,
    EXTENSION_SUFFIXES,
    ExtensionFileLoader,
    FileFinder,
    SourceFileLoader,
    SourcelessFileLoader,
)
from pathlib import Path
from types import ModuleType

import pytest

from archkeel.analyzer.process import (
    ProcessCollector,
    _requested_facts,
    _requested_provider_sources,
)
from archkeel.analyzer.python import collect as collect_owner
from archkeel.analyzer.python.collect import PythonProviderCollector, collect, provider_sources
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.observation import assemble_observation
from archkeel.cli.observe import observer_for
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import Language, ProviderBinding, ProviderBindingKind, SourceSectionName
from archkeel.ir.facts_codec import (
    ProtocolError,
    decode_request,
    decode_response,
    encode_request,
    encode_response,
)
from archkeel.ir.protocol import (
    PYTHON_IMPORT_SURVEY_SECTIONS,
    CollectionError,
    CollectionErrorKind,
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonProviderSource,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)


def _provider(module: str, source: str, *, package: bool = False) -> PythonProviderSource:
    path = ".archkeel-providers/" + module.replace(".", "/")
    path += "/__init__.py" if package else ".py"
    return PythonProviderSource(module, path, source, hashlib.sha256(source.encode()).hexdigest())


def _request(tmp_path: Path, providers=(), *, imported="contextlib", binding="contextmanager"):
    source = tmp_path / "src/sample"
    source.mkdir(parents=True, exist_ok=True)
    (source / "api.py").write_text(f"from {imported} import {binding}\n__all__ = ['{binding}']\n")
    return CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("src",), "sample"),
        PythonSettings(provider_sources=tuple(providers)),
        ProtocolVersion.V4,
    )


def _native_facts(request):
    request = decode_request(encode_request(request))
    facts = decode_response(
        encode_response(CollectionResponse(collect(request), request.protocol_version))
    ).facts
    _requested_facts(facts, request)
    return facts


def test_source_facts_reject_a_value_occurrence_claimed_as_an_annotation(tmp_path):
    source = tmp_path / "src/sample"
    source.mkdir(parents=True, exist_ok=True)
    (source / "defaults.py").write_text("VALUE = 1\n")
    (source / "consumer.py").write_text("from .defaults import VALUE\nx = VALUE\n")
    request = _request(tmp_path)
    facts = collect(request)
    wire = json.loads(encode_response(CollectionResponse(facts, request.protocol_version)))
    [reference] = [
        item
        for section in wire["facts"]["sections"]
        if section["name"] == "references"
        for item in section["records"]
        if item["kind"] == "value_reference" and item["data"].get("expression") == "VALUE"
    ]
    reference["data"]["reference_context"] = "annotation"

    with pytest.raises(ValueError, match="annotation reference contradicts its source occurrence"):
        decode_response(json.dumps(wire).encode())


def _captured_sources(request):
    initial = replace(
        request,
        resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS),
        protocol_version=ProtocolVersion.V4,
    )
    return provider_sources(initial, _native_facts(initial))


def _provider_passes(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    request = replace(_request(tmp_path), protocol_version=ProtocolVersion.V3)
    initial = _native_facts(
        replace(
            request,
            resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS),
            protocol_version=ProtocolVersion.V4,
        )
    )
    enriched = _native_facts(
        replace(
            request,
            resolver=PythonSettings(provider_sources=(provider,)),
            protocol_version=ProtocolVersion.V4,
        )
    )
    initial = replace(
        initial,
        inputs=enriched.inputs,
        provider_bindings=enriched.provider_bindings,
        evidence=enriched.evidence,
    )
    return request, provider, initial, enriched


def test_provider_capture_never_parses_project_ast_in_the_parent(tmp_path, monkeypatch):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "contextlib.py").write_text(
        (Path(sysconfig.get_path("stdlib")) / "contextlib.py").read_text()
    )
    request = replace(_request(tmp_path), protocol_version=ProtocolVersion.V3)
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: dict.fromkeys(("stdlib", "platstdlib", "purelib", "platlib"), str(environment)),
    )

    def parent_parser_trap(*_args, **_kwargs):
        raise MemoryError("project AST reached the unbounded parent")

    with monkeypatch.context() as traps:
        traps.setattr(ast, "parse", parent_parser_trap)
        traps.setattr(collect_owner, "parse_sources", parent_parser_trap)
        traps.setattr(collect_owner, "provider_sources", parent_parser_trap)
        result = PythonProviderCollector(
            ProcessCollector((sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry"))
        ).collect(request)
    assert not isinstance(result, CollectionError), result
    assert [item.qualified_name for item in result.provider_bindings] == [
        "contextlib.contextmanager"
    ]


@pytest.mark.parametrize("phase", ["initial", "enriched"])
@pytest.mark.parametrize("kind", list(CollectionErrorKind))
def test_provider_pass_errors_are_returned_unchanged(tmp_path, monkeypatch, phase, kind):
    request, provider, initial, _ = _provider_passes(tmp_path)
    expected = CollectionError(kind, "fixture", "bounded collector failure")
    calls = []

    def bounded(_collector, actual):
        calls.append(actual.protocol_version)
        return (
            expected
            if phase == "initial" or len(calls) == 2
            else CollectionResponse(initial, ProtocolVersion.V4, (provider,))
        )

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    result = PythonProviderCollector(ProcessCollector(("native-python",))).collect(request)
    assert result is expected
    assert calls == [ProtocolVersion.V4, ProtocolVersion.V8][: 1 if phase == "initial" else 2]


def test_no_provider_sources_still_require_a_final_full_collection(tmp_path, monkeypatch):
    request, _, initial, _ = _provider_passes(tmp_path)
    initial = replace(
        initial,
        inputs=tuple(
            item for item in initial.inputs if not item.path.startswith(".archkeel-providers/")
        ),
    )
    complete = _native_facts(request)
    calls = []

    def bounded(_collector, actual):
        calls.append(actual)
        return CollectionResponse(initial if len(calls) == 1 else complete, actual.protocol_version)

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    result = PythonProviderCollector(ProcessCollector(("native-python",))).collect(request)
    assert result is complete
    assert calls == [
        replace(
            request,
            resolver=PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
            protocol_version=ProtocolVersion.V4,
        ),
        replace(request, protocol_version=ProtocolVersion.V8),
    ]


def test_provider_passes_share_one_deadline_and_preserve_process_limits(tmp_path, monkeypatch):
    request, provider, initial, enriched = _provider_passes(tmp_path)
    now = [10.0]
    calls = []

    def bounded(_collector, actual):
        calls.append((_collector, actual))
        now[0] += 5 if len(calls) == 1 else 4
        return CollectionResponse(
            initial if len(calls) == 1 else enriched,
            actual.protocol_version,
            (provider,) if len(calls) == 1 else (),
        )

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    monkeypatch.setattr(collect_owner, "monotonic", lambda: now[0])
    process = ProcessCollector(("native-python", "--fixed"), 20, 123456, 654)
    result = PythonProviderCollector(process).collect(request)
    assert result is enriched
    assert calls[0] == (
        process,
        replace(
            request,
            resolver=PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
            protocol_version=ProtocolVersion.V4,
        ),
    )
    second, final_request = calls[1]
    assert second == replace(process, timeout_seconds=15)
    assert final_request == replace(
        request,
        resolver=PythonSettings(provider_sources=(provider,)),
        protocol_version=ProtocolVersion.V8,
    )


@pytest.mark.parametrize("phase", ["initial", "enriched"])
def test_exhausted_provider_deadline_is_a_typed_timeout(tmp_path, monkeypatch, phase):
    request, provider, initial, enriched = _provider_passes(tmp_path)
    now = [0.0]
    calls = []

    def bounded(_collector, actual):
        calls.append(actual.protocol_version)
        current = "initial" if len(calls) == 1 else "enriched"
        now[0] += 11 if current == phase else 1
        return CollectionResponse(
            initial if len(calls) == 1 else enriched,
            actual.protocol_version,
            (provider,) if len(calls) == 1 else (),
        )

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    monkeypatch.setattr(collect_owner, "monotonic", lambda: now[0])
    result = PythonProviderCollector(ProcessCollector(("native-python",), 10)).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.TIMEOUT
    assert result.subject == "native-python"
    assert len(calls) == (2 if phase == "enriched" else 1)


@pytest.mark.parametrize(
    "changed", ["digest", "resolution", "added", "removed", "adapter", "runtime", "scope"]
)
def test_provider_passes_reject_changed_project_manifest_or_execution_origin(
    tmp_path, monkeypatch, changed
):
    request, provider, initial, enriched = _provider_passes(tmp_path)
    if changed in {"digest", "resolution"}:
        path = "src/sample/api.py" if changed == "digest" else "pyproject.toml"
        enriched = replace(
            enriched,
            inputs=tuple(
                replace(item, digest="0" * 64) if item.path == path else item
                for item in enriched.inputs
            ),
        )
    elif changed == "added":
        enriched = replace(
            enriched, inputs=(*enriched.inputs, replace(initial.inputs[0], path="extra.py"))
        )
    elif changed == "removed":
        enriched = replace(
            enriched,
            inputs=tuple(item for item in enriched.inputs if item.path != "src/sample/api.py"),
        )
    elif changed == "adapter":
        enriched = replace(enriched, adapter=replace(enriched.adapter, code_digest="0" * 64))
    elif changed == "runtime":
        enriched = replace(enriched, runtime=replace(enriched.runtime, version="0.0.0"))
    else:
        enriched = replace(enriched, source=replace(enriched.source, scope=("different/**/*.py",)))
    calls = []

    def bounded(_collector, actual):
        calls.append(actual.protocol_version)
        return CollectionResponse(
            initial if len(calls) == 1 else enriched,
            actual.protocol_version,
            (provider,) if len(calls) == 1 else (),
        )

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    result = PythonProviderCollector(ProcessCollector(("native-python",))).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR


def test_custom_python_collector_argv_keeps_single_pass_composition():
    observer = observer_for(Language.PYTHON, collector_argv=("custom-python", "--fixture"))
    assert isinstance(observer.collector, ProcessCollector)
    assert observer.collector.argv == ("custom-python", "--fixture")


def test_default_python_collector_composes_the_native_provider_passes():
    observer = observer_for(Language.PYTHON)
    assert isinstance(observer.collector, PythonProviderCollector)
    assert observer.collector.collector.argv == (
        sys.executable,
        "-I",
        "-B",
        "-m",
        "archkeel.analyzer.python.entry",
    )


@pytest.mark.parametrize("language", [Language.DART, Language.TYPESCRIPT])
def test_other_default_languages_keep_the_original_process_collector(language):
    assert isinstance(observer_for(language).collector, ProcessCollector)


@pytest.mark.parametrize("sibling", ["", "from collections.abc import Mapping\n"])
def test_default_provider_port_runs_both_native_phases_for_actual_contextlib(
    tmp_path, monkeypatch, sibling
):
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = replace(_request(tmp_path), protocol_version=ProtocolVersion.V3)
    api = tmp_path / "src/sample/api.py"
    api.write_text(api.read_text() + sibling)
    observer = observer_for(Language.PYTHON, output_limit_bytes=8_388_608)
    assert isinstance(observer.collector, PythonProviderCollector)
    native = ProcessCollector.collect_response
    calls = []

    def execute(collector, actual):
        calls.append((actual.protocol_version, actual.resolver.phase, actual.scope))
        assert collector.output_limit_bytes == 8_388_608
        return native(collector, actual)

    monkeypatch.setattr(ProcessCollector, "collect_response", execute)
    facts = observer.collector.collect(request)
    assert not isinstance(facts, CollectionError), facts
    assert calls == [
        (ProtocolVersion.V4, PythonCollectionPhase.PROVIDERS, request.scope),
        (ProtocolVersion.V8, PythonCollectionPhase.COLLECT, request.scope),
    ]
    expected = {"contextlib.contextmanager"}
    if sibling:
        expected.update({"collections.abc.Mapping", "_collections_abc.Mapping"})
    assert {item.qualified_name for item in facts.provider_bindings} == expected
    if sibling:
        alias = next(
            item for item in facts.provider_bindings if item.kind is ProviderBindingKind.ALIAS
        )
        assert alias.target == "_collections_abc.Mapping" and alias.supporting_evidence_ids
    assert facts.source.scope == ("src/**/*.py",)


def test_actual_contextmanager_source_declaration_is_certified(tmp_path):
    source = (Path(sysconfig.get_path("stdlib")) / "contextlib.py").read_text()
    request = _request(tmp_path, [_provider("contextlib", source)])
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "contextlib.contextmanager"
    assert binding.kind is ProviderBindingKind.FUNCTION
    evidence = next(item for item in facts.evidence if item.id == binding.evidence_id)
    assert evidence.file == request.resolver.provider_sources[0].path
    assert evidence.excerpt.startswith("def contextmanager(")


def test_named_source_base_and_override_do_not_claim_runtime_member_form(tmp_path):
    source = "class Base:\n    def run(self): pass\nclass ABC(Base):\n    def run(self): opaque()\n"
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    [binding] = _native_facts(request).provider_bindings
    assert binding.qualified_name == "source_tools.ABC"
    assert binding.kind is ProviderBindingKind.CLASS


@pytest.mark.parametrize(
    ("module", "source"),
    [("broken", "def convert(\n"), ("vendor.leaf", "def convert(): pass\n")],
    ids=["syntax", "missing-parent"],
)
def test_unrelated_provider_identity_gap_does_not_erase_known_declaration(tmp_path, module, source):
    providers = [
        _provider("contextlib", "def contextmanager(func): return func\n"),
        _provider(module, source),
    ]
    request = _request(tmp_path, providers)
    api = tmp_path / "src/sample/api.py"
    api.write_text(api.read_text() + f"from {module} import convert\n")
    assert [item.qualified_name for item in _native_facts(request).provider_bindings] == [
        "contextlib.contextmanager"
    ]


def test_import_survey_retains_file_inputs_and_coverage_without_deeper_analysis(
    tmp_path, monkeypatch
):
    request = _request(tmp_path)
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    (tmp_path / "src/sample/broken.py").write_text("def broken(:\n")
    complete = _native_facts(replace(request, protocol_version=ProtocolVersion.V3))

    def forbidden_analysis(*_args, **_kwargs):
        pytest.fail("the import survey reached full source analysis")

    for name in (
        "_provider_bindings",
        "resolve_reexports",
        "collect_symbols",
        "collect_calls_with_resolvers",
        "collect_references",
        "collect_bindings",
        "collect_typing_signals",
        "collect_constructs",
        "collect_type_shapes",
        "collect_state",
        "collect_private_attributes",
    ):
        monkeypatch.setattr(collect_owner, name, forbidden_analysis)
    survey = _native_facts(
        replace(request, resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS))
    )
    assert survey.capabilities.sections == PYTHON_IMPORT_SURVEY_SECTIONS
    assert tuple(section.name for section in survey.sections) == survey.capabilities.sections
    assert not survey.capabilities.constructs
    assert survey.files == complete.files
    assert survey.inputs == complete.inputs
    assert survey.source == complete.source
    assert survey.coverage == complete.coverage
    assert survey.adapter == complete.adapter and survey.runtime == complete.runtime
    assert not survey.provider_bindings and not survey.type_shapes
    assert not survey.state.classes and not survey.state.functions
    assert len(survey.coverage.selected_files) == 2 and not survey.coverage.full_scope


@pytest.mark.parametrize("scope", ["complete", "empty", "parse_failure"])
def test_import_survey_cannot_satisfy_the_full_python_core_profile(tmp_path, scope):
    request = _request(tmp_path)
    selected = tmp_path / "src/sample/api.py"
    if scope == "empty":
        selected.unlink()
    elif scope == "parse_failure":
        selected.write_text("def broken(:\n")
    survey = _native_facts(
        replace(request, resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS))
    )
    with pytest.raises(ProtocolError, match="registered profile"):
        _route_records(survey)


@pytest.mark.parametrize("providers", [False, True])
@pytest.mark.parametrize("returned", ["survey", "partial"])
def test_provider_wrapper_rejects_a_survey_instead_of_final_full_facts(
    tmp_path, monkeypatch, providers, returned
):
    request, provider, initial, complete = _provider_passes(tmp_path)
    if not providers:
        initial = replace(
            initial,
            inputs=tuple(
                item for item in initial.inputs if not item.path.startswith(".archkeel-providers/")
            ),
        )
    final = (
        initial
        if returned == "survey"
        else replace(
            complete,
            capabilities=replace(
                complete.capabilities, sections=complete.capabilities.sections[:-1]
            ),
            sections=complete.sections[:-1],
        )
    )
    calls = []

    def bounded(_collector, actual):
        calls.append(actual)
        return CollectionResponse(
            initial if len(calls) == 1 else final,
            actual.protocol_version,
            (provider,) if providers and len(calls) == 1 else (),
        )

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    result = PythonProviderCollector(ProcessCollector(("native-python",))).collect(request)
    assert isinstance(result, CollectionError)
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert len(calls) == 2
    assert calls[-1].resolver.phase is PythonCollectionPhase.COLLECT


def test_explicit_import_survey_is_delegated_once_without_autophases(tmp_path, monkeypatch):
    request = replace(
        _request(tmp_path), resolver=PythonSettings(phase=PythonCollectionPhase.IMPORTS)
    )
    survey = _native_facts(request)
    calls = []

    def bounded(_collector, actual):
        calls.append(actual)
        return survey

    monkeypatch.setattr(ProcessCollector, "collect", bounded)
    assert PythonProviderCollector(ProcessCollector(("native-python",))).collect(request) is survey
    assert calls == [request]


def _route_contract():
    return {
        "schema_version": "3.6.0",
        "components": [
            {
                "id": "sample",
                "label": "sample",
                "role": "component",
                "packages": ["sample"],
                "public": ["sample.api"],
                "responsibilities": ["Publish declared types."],
                "forbidden_responsibilities": [],
                "provenance": ["architecture.md"],
            },
        ],
        "rules": [
            {
                "id": "DECLARED",
                "kind": "boundary_types",
                "source": "sample.api",
                "rationale": "Every exported binding needs its source route.",
                "decided_by": "architect",
                "provenance": ["architecture.md"],
            },
            {
                "id": "NO-DYNAMIC",
                "kind": "forbidden_construct",
                "source": "sample",
                "constructs": ["getattr"],
                "rationale": "Keep existing construct evaluation active.",
                "decided_by": "architect",
                "provenance": ["architecture.md"],
            },
        ],
    }


def _route_records(facts):
    contract = parse_contract(_route_contract())
    scan = evaluate_source(facts, contract, roots=("src",), namespace="sample")
    return [record for record in scan.unknowns if record["kind"] == "boundary_type_route"], scan


def _route_assessment(tmp_path, facts):
    (tmp_path / "architecture.md").write_text("Publish declared types.\n")
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(_route_contract()))
    observation, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=contract_path,
        roots=("src",),
        namespace="sample",
        language=Language.PYTHON,
    )
    undecided = Counter(
        rule for record in observation.records("unknowns") or () for rule in record.rule_ids
    )
    return next(
        item
        for item in rule_assessments(observation, undecided_by_rule=undecided)
        if item.id == "DECLARED"
    )


@pytest.mark.parametrize(
    ("source", "declaration_kind"),
    [
        (
            "def replace(fn): return 7\n@replace\ndef ABC() -> str: return 'value'\n",
            ProviderBindingKind.DECLARATION,
        ),
        (
            "class Meta(type):\n"
            "    def __new__(mcls, name, bases, namespace): return 7\n"
            "class ABC(metaclass=Meta): pass\n",
            None,
        ),
        (
            "class Meta(type):\n"
            "    def __new__(mcls, name, bases, namespace):\n"
            "        return 7 if name == 'ABC' else super().__new__(mcls, name, bases, namespace)\n"
            "class Base(metaclass=Meta): pass\nclass ABC(Base): pass\n",
            ProviderBindingKind.CLASS,
        ),
        ("def replace(cls): return 7\n@replace\nclass ABC: pass\n", None),
        (
            "def ABC() -> str: return 'value'\nABC.__globals__['ABC'] = 7\n",
            ProviderBindingKind.FUNCTION,
        ),
        (
            "def ABC() -> str: return 'value'\nalias = ABC\nalias.__globals__['ABC'] = 7\n",
            ProviderBindingKind.FUNCTION,
        ),
        (
            "def ABC() -> str: return 'value'\n"
            "class Descriptor:\n"
            "    def __set_name__(self, owner, name): ABC.__globals__['ABC'] = 7\n"
            "class Owner:\n    value = Descriptor()\n",
            ProviderBindingKind.FUNCTION,
        ),
        (
            "class ABC: pass\ndef helper(): pass\n"
            "class Descriptor:\n"
            "    def __set_name__(self, owner, name): helper.__globals__['ABC'] = 7\n"
            "class Owner:\n    value = Descriptor()\n",
            ProviderBindingKind.CLASS,
        ),
        (
            "def ABC() -> str: return 'value'\n"
            "def mutate(): ABC.__globals__['ABC'] = 7\n"
            "def holder(value=mutate()): pass\n",
            ProviderBindingKind.FUNCTION,
        ),
        (
            "def ABC() -> str: return 'value'\n"
            "def mutate(): ABC.__globals__['ABC'] = 7\n"
            "def holder(value: mutate()): pass\n",
            ProviderBindingKind.FUNCTION,
        ),
        (
            "def ABC() -> str: return 'value'\n"
            "def mutate(): ABC.__globals__['ABC'] = 7\n"
            "class Holder:\n    value: mutate()\n",
            ProviderBindingKind.FUNCTION,
        ),
    ],
    ids=[
        "decorated-function",
        "metaclass",
        "inherited-metaclass",
        "decorated-class",
        "function-globals",
        "alias-globals",
        "descriptor-function",
        "descriptor-class-via-function",
        "eager-default",
        "eager-function-annotation",
        "eager-class-annotation",
    ],
)
def test_provider_declaration_kind_and_runtime_replacement_are_separate(
    tmp_path, source, declaration_kind
):
    namespace = {}
    exec(source, namespace)
    assert namespace["ABC"] == 7
    assert not callable(namespace["ABC"]) and not isinstance(namespace["ABC"], type)
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from source_tools import ABC\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.evaluation_proven
    assert assessment.status == ("PASS" if declaration_kind is not None else "UNKNOWN")
    assert assessment.undecided == (0 if declaration_kind is not None else 1)
    assert len(facts.provider_bindings) == (1 if declaration_kind is not None else 0)
    if declaration_kind is not None:
        [binding] = facts.provider_bindings
        assert binding.qualified_name == "source_tools.ABC" and binding.kind is declaration_kind
    assert len(_route_records(facts)[0]) == (0 if declaration_kind is not None else 1)


@pytest.mark.parametrize(
    "definition",
    ["def ABC() -> str: return 'value'\n", "class ABC: pass\n"],
    ids=["function", "class"],
)
@pytest.mark.parametrize(
    ("body", "mutation"),
    [
        ("__import__('sys').modules[__name__].ABC = 7", "helper()"),
        ("pass", "helper.__globals__['ABC'] = 7"),
        ("pass", "alias = helper\nalias.__globals__['ABC'] = 7"),
    ],
    ids=["opaque-body", "function-globals", "alias-globals"],
)
def test_provider_source_identity_is_separate_from_deferred_namespace_mutation(
    tmp_path, monkeypatch, definition, body, mutation
):
    source = definition + f"def helper():\n    {body}\n"
    provider = ModuleType("runtime_provider")
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    exec(source, provider.__dict__)
    assert callable(provider.ABC)
    exec(mutation, {"helper": provider.helper})
    assert provider.ABC == 7
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    (tmp_path / "src/sample/api.py").write_text(
        f"from source_tools import helper\n{mutation}\nfrom source_tools import ABC\n"
        "def keep(value: str) -> str: return value\n__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assert "source_tools.ABC" in {item.qualified_name for item in facts.provider_bindings}
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "PASS"
    assert assessment.evaluation_proven
    assert assessment.undecided == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "helper.__globals__['__builtins__']['__import__']('source_tools').ABC = 7\n",
        "load = helper.__globals__['__builtins__']['__import__']\nload('source_tools').ABC = 7\n",
        "helper.__globals__.__getitem__('__builtins__')['__import__']('source_tools').ABC = 7\n",
        "helper.__globals__.get('__builtins__')['__import__']('source_tools').ABC = 7\n",
        "helper.__getattribute__('__globals__')['__builtins__']['__import__']"
        "('source_tools').ABC = 7\n",
        "helper.__builtins__.get('__import__')('source_tools').ABC = 7\n",
        "stream.gi_frame.f_globals.get('__builtins__')['__import__']('source_tools').ABC = 7\n",
    ],
    ids=[
        "chained-callee",
        "aliased-callee",
        "namespace-getitem-callhead",
        "namespace-get-callhead",
        "function-getattribute-callhead",
        "function-builtins-callhead",
        "generator-frame-source-declaration",
    ],
)
def test_exposed_function_namespace_does_not_erase_another_provider_declaration(
    tmp_path, monkeypatch, mutation
):
    source = "class ABC: pass\n"
    other = "def helper(): pass\ndef produce():\n    yield 1\nstream = produce()\n"
    provider = ModuleType("runtime_provider")
    helpers = ModuleType("runtime_helpers")
    exec(source, provider.__dict__)
    exec(other, helpers.__dict__)
    with monkeypatch.context() as runtime:
        runtime.setitem(sys.modules, "source_tools", provider)
        exec(mutation, {"helper": helpers.helper, "stream": helpers.stream})
    assert provider.ABC == 7
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path,
        [_provider("source_tools", source), _provider("helpers", other)],
        imported="source_tools",
        binding="ABC",
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from helpers import helper, stream\n" + mutation + "from source_tools import ABC\n"
        "def keep(value: str) -> str: return value\n__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assert "source_tools.ABC" in {item.qualified_name for item in facts.provider_bindings}
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert assessment.undecided == 0


@pytest.mark.parametrize(
    "mutation",
    [
        "__import__('source_tools').ABC = 7\n",
        "load = __import__\nload('source_tools').ABC = 7\n",
        "__builtins__['__import__']('source_tools').ABC = 7\n",
    ],
    ids=["direct", "aliased", "implicit-builtins"],
)
def test_selected_runtime_import_mutation_preserves_external_source_declaration(
    tmp_path, monkeypatch, mutation
):
    source = "class ABC: pass\n"
    provider = ModuleType("runtime_provider")
    exec(source, provider.__dict__)
    with monkeypatch.context() as runtime:
        runtime.setitem(sys.modules, "source_tools", provider)
        exec(mutation, {})
    assert provider.ABC == 7
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    (tmp_path / "src/sample/api.py").write_text(
        mutation + "from source_tools import ABC\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assert [item.qualified_name for item in facts.provider_bindings] == ["source_tools.ABC"]
    routes, scan = _route_records(facts)
    assert [record["data"]["qualified_name"] for record in routes] == ["sample.api.ABC"]
    assert {
        (record["data"]["qualified_name"], record["data"]["position"], record["data"]["reason"])
        for record in scan.unknowns
        if record["kind"] == "boundary_type_position"
    } == {
        ("sample.api.keep", "value", "ambiguous_facade"),
        ("sample.api.keep", "return", "ambiguous_facade"),
    }
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "UNKNOWN" and assessment.evaluation_proven
    assert assessment.undecided == 4


@pytest.mark.parametrize("captured", [True, False], ids=["captured", "missing-source"])
@pytest.mark.parametrize("effect", ["eager", "deferred", "pure"])
def test_provider_declaration_does_not_require_sibling_runtime_closure(
    tmp_path, monkeypatch, captured, effect
):
    source = "class ABC: pass\n"
    sibling = {
        "eager": "import source_tools\nsource_tools.ABC = 7\n",
        "deferred": "import source_tools\ndef helper(): source_tools.ABC = 7\n",
        "pure": "def helper(): pass\n",
    }[effect]
    provider = ModuleType("runtime_provider")
    helpers = ModuleType("runtime_helpers")
    exec(source, provider.__dict__)
    with monkeypatch.context() as runtime:
        runtime.setitem(sys.modules, "source_tools", provider)
        exec(sibling, helpers.__dict__)
        if effect == "deferred":
            helpers.helper()
    if effect == "pure":
        assert isinstance(provider.ABC, type)
    else:
        assert provider.ABC == 7
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    providers = [_provider("source_tools", source)]
    if captured:
        providers.append(_provider("helpers", sibling))
    request = _request(tmp_path, providers, imported="source_tools", binding="ABC")
    use = "from helpers import helper\nhelper()\n" if effect == "deferred" else "import helpers\n"
    (tmp_path / "src/sample/api.py").write_text(
        use + "from source_tools import ABC\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.evaluation_proven
    [binding] = [
        item for item in facts.provider_bindings if item.qualified_name == "source_tools.ABC"
    ]
    assert binding.kind is ProviderBindingKind.CLASS
    assert assessment.status == "PASS" and assessment.undecided == 0
    assert {item.path for item in facts.inputs if item.path.startswith(".archkeel-providers/")} == {
        item.path for item in providers
    }


@pytest.mark.parametrize("opaque", [True, False], ids=["opaque-initializer", "inert-module"])
def test_governed_sibling_effects_do_not_erase_external_source_declarations(
    tmp_path, monkeypatch, opaque
):
    source = "class ABC: pass\n"
    sibling = "__import__('source_tools').ABC = 7\n" if opaque else "value = 1\n"
    provider = ModuleType("runtime_provider")
    exec(source, provider.__dict__)
    with monkeypatch.context() as runtime:
        runtime.setitem(sys.modules, "source_tools", provider)
        exec(sibling, {})
    if opaque:
        assert provider.ABC == 7
    else:
        assert isinstance(provider.ABC, type)
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    (tmp_path / "src/sample/effects.py").write_text(sibling)
    (tmp_path / "src/sample/api.py").write_text(
        "import sample.effects\nfrom source_tools import ABC\n"
        "def keep(value: str) -> str: return value\n__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.evaluation_proven
    [binding] = facts.provider_bindings
    assert (
        binding.qualified_name == "source_tools.ABC" and binding.kind is ProviderBindingKind.CLASS
    )
    assert assessment.status == "PASS" and assessment.undecided == 0


def test_actual_provider_dependency_effect_keeps_the_distinct_source_receipt(tmp_path, monkeypatch):
    source = (Path(sysconfig.get_path("stdlib")) / "contextlib.py").read_text()
    namespace = {"__name__": "runtime_contextlib"}
    original = abc.ABCMeta.__init__

    def mutate_namespace(cls, *args, **kwargs):
        original(cls, *args, **kwargs)
        caller = sys._getframe(1).f_globals
        if caller is namespace and "contextmanager" in caller:
            caller["contextmanager"] = 7

    with monkeypatch.context() as dependency:
        dependency.setattr(abc.ABCMeta, "__init__", mutate_namespace)
        exec(source, namespace)
    assert namespace["contextmanager"] == 7
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(tmp_path, [_provider("contextlib", source)])
    (tmp_path / "src/sample/api.py").write_text(
        "from contextlib import contextmanager\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['contextmanager', 'keep']\n"
    )
    facts = _native_facts(request)
    assert [item.qualified_name for item in facts.provider_bindings] == [
        "contextlib.contextmanager"
    ]
    assert request.resolver.provider_sources[0].source == source
    [captured] = [item for item in facts.inputs if item.path.startswith(".archkeel-providers/")]
    assert captured.digest == hashlib.sha256(source.encode()).hexdigest()
    missing = _native_facts(replace(request, resolver=PythonSettings()))
    assert facts.files == missing.files and facts.coverage == missing.coverage
    assert facts.source.source_digest != missing.source.source_digest
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert assessment.undecided == 0


@pytest.mark.parametrize(
    ("source", "kind"),
    [
        ("def ABC() -> str: return 'value'\n", ProviderBindingKind.FUNCTION),
        ("class ABC: pass\n", ProviderBindingKind.CLASS),
    ],
    ids=["undecorated-function", "bare-class"],
)
def test_direct_provider_identity_retains_its_receipt(tmp_path, source, kind):
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider("source_tools", source)], imported="source_tools", binding="ABC"
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from source_tools import ABC\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['ABC', 'keep']\n"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "source_tools.ABC" and binding.kind is kind
    [imported] = next(s for s in facts.sections if s.name is SourceSectionName.IMPORTS).records
    assert imported.data.get("source_member_binding_static") is False
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert assessment.undecided == 0


def test_pure_nonframework_provider_retains_source_receipt_without_member_proof(tmp_path):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(tmp_path, [provider])
    (tmp_path / "src/sample/api.py").write_text(
        "from contextlib import contextmanager\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['contextmanager', 'keep']\n"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "contextlib.contextmanager"
    assert binding.kind is ProviderBindingKind.FUNCTION
    [imported] = next(s for s in facts.sections if s.name is SourceSectionName.IMPORTS).records
    assert imported.data.get("source_member_binding_static") is False
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == "PASS" and assessment.evaluation_proven
    assert assessment.undecided == 0


@pytest.mark.parametrize(
    ("module", "binding", "kind", "namespace_proven"),
    [
        ("contextlib", "contextmanager", ProviderBindingKind.FUNCTION, False),
        ("abc", "ABC", None, True),
    ],
)
def test_actual_provider_sources_retain_namespace_and_source_guards(
    tmp_path, module, binding, kind, namespace_proven
):
    path = Path(sysconfig.get_path("stdlib")) / f"{module}.py"
    qualified = f"{module}.{binding}"
    (tmp_path / "pyproject.toml").write_text("[project]\nrequires-python = '>=3.11'\n")
    request = _request(
        tmp_path, [_provider(module, path.read_text())], imported=module, binding=binding
    )
    (tmp_path / "src/sample/api.py").write_text(
        f"from {module} import {binding}\ndef keep(value: str) -> str: return value\n"
        f"__all__ = ['{binding}', 'keep']\n"
    )
    facts = _native_facts(request)
    missing = _native_facts(replace(request, resolver=PythonSettings()))
    if kind is None:
        assert not facts.provider_bindings
    else:
        assert [item.qualified_name for item in facts.provider_bindings] == [qualified]
        assert facts.provider_bindings[0].kind is kind
    assert facts.files == missing.files
    assert facts.coverage == missing.coverage
    for name in (SourceSectionName.SYMBOLS, SourceSectionName.CALLS, SourceSectionName.IMPORTS):
        assert next(s for s in facts.sections if s.name is name) == next(
            s for s in missing.sections if s.name is name
        )
    unresolved, baseline = _route_records(missing)
    resolved, candidate = _route_records(facts)
    assert len(unresolved) == 1
    [imported] = next(s for s in facts.sections if s.name is SourceSectionName.IMPORTS).records
    assert imported.data.get("source_member_binding_static") is namespace_proven
    assert resolved == ([] if kind is not None else unresolved)
    assert baseline.coverage == candidate.coverage
    assert baseline.typing_signals == candidate.typing_signals
    receipts = [
        item for item in candidate.scope_observations if item["kind"] == "source_provider_binding"
    ]
    if kind is None:
        assert not receipts
    else:
        [receipt] = receipts
        assert receipt["data"]["qualified_name"] == qualified
        assert receipt["data"]["digest"] == request.resolver.provider_sources[0].digest
        assert receipt["evidence_ids"] == [facts.provider_bindings[0].evidence_id]
    assessment = _route_assessment(tmp_path, facts)
    assert assessment.status == ("PASS" if kind is not None else "UNKNOWN")
    assert assessment.evaluation_proven
    assert assessment.undecided == (0 if kind is not None else 1)


@pytest.mark.parametrize("renamed", [False, True], ids=["dataclasses", "nonframework"])
def test_actual_replace_source_has_a_direct_provider_declaration(tmp_path, renamed):
    source = (Path(sysconfig.get_path("stdlib")) / "dataclasses.py").read_text()
    module, name = "dataclasses", "replace"
    if renamed:
        module, name = "value_tools", "copy_record"
        tree = ast.parse(source)
        next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "replace"
        ).name = name
        source = ast.unparse(tree)
    provider = _provider(module, source)
    request = _request(tmp_path, [provider], imported=module, binding=name)
    missing = _native_facts(replace(request, resolver=PythonSettings()))
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == f"{module}.{name}"
    assert binding.kind is ProviderBindingKind.FUNCTION
    [evidence] = [item for item in facts.evidence if item.id == binding.evidence_id]
    assert evidence.file == provider.path
    assert facts.files == missing.files and facts.coverage == missing.coverage
    assert len(_route_records(missing)[0]) == 1
    assert not _route_records(facts)[0]


@pytest.mark.parametrize(
    "source",
    [
        "Payload = factory()\n",
        "Payload: object = factory()\n",
        "Other = Payload = factory()\n",
        "def decorate(fn): return 7\n@decorate\ndef Payload(value: str) -> str: return value\n",
        "@factory()\nasync def Payload(value: str) -> str: return value\n",
    ],
    ids=["assign", "annotated", "chained", "decorated", "decorator-factory"],
)
def test_provider_declaration_records_only_direct_source_identity(tmp_path, source):
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="Payload"
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from value_tools import Payload\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['Payload', 'keep']\n"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "value_tools.Payload"
    assert binding.kind.value == "declaration"
    assert not _route_records(facts)[0]
    assert _route_assessment(tmp_path, facts).status == "PASS"


@pytest.mark.parametrize(
    "source",
    [
        "Payload: object\n",
        "Payload, Other = factory()\n",
        "(Payload := factory())\n",
        "if enabled:\n    Payload = factory()\n",
        "Payload = factory()\nPayload = other()\n",
        "Payload = factory()\nfrom elsewhere import Payload\n",
        "Payload = factory()\ndef mutate():\n    global Payload\n    Payload = None\n",
        "Payload = factory()\nfrom elsewhere import *\n",
        "Payload = factory()\nglobals()['Payload'] = None\n",
    ],
    ids=[
        "annotation-only",
        "destructuring",
        "named-expression",
        "conditional",
        "duplicate",
        "import",
        "global",
        "star",
        "dynamic-rebind",
    ],
)
def test_provider_declaration_requires_a_complete_unique_direct_binding(tmp_path, source):
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="Payload"
    )
    facts = _native_facts(request)
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


def test_actual_future_feature_is_a_source_declaration(tmp_path):
    source = (Path(sysconfig.get_path("stdlib")) / "__future__.py").read_text()
    request = _request(
        tmp_path, [_provider("__future__", source)], imported="__future__", binding="annotations"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "__future__.annotations"
    assert binding.kind.value == "declaration"
    assert not _route_records(facts)[0]


@pytest.mark.parametrize("name", ["Final", "TypeAlias"])
def test_actual_typing_forms_have_declaration_receipts(tmp_path, name):
    source = (Path(sysconfig.get_path("stdlib")) / "typing.py").read_text()
    provider = _provider("typing", source)
    request = _request(tmp_path, [provider], imported="typing", binding=name)
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == f"typing.{name}"
    assert binding.kind is ProviderBindingKind.DECLARATION
    [evidence] = [item for item in facts.evidence if item.id == binding.evidence_id]
    assert evidence.file == provider.path and evidence.excerpt.startswith(f"def {name}(")
    assert not _route_records(facts)[0]


def test_actual_pathlib_path_has_a_class_receipt(tmp_path):
    stdlib = Path(sysconfig.get_path("stdlib"))
    package = (stdlib / "pathlib/__init__.py").is_file()
    source = (stdlib / ("pathlib/__init__.py" if package else "pathlib.py")).read_text()
    if "\nclass Path(" not in source:
        pytest.skip("pathlib publishes Path only through two star imports (Python 3.13)")
    provider = _provider("pathlib", source, package=package)
    facts = _native_facts(_request(tmp_path, [provider], imported="pathlib", binding="Path"))
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "pathlib.Path"
    assert binding.kind is ProviderBindingKind.CLASS
    assert not _route_records(facts)[0]


def test_actual_typing_runtime_module_publication_has_no_declaration_receipt(tmp_path):
    source = (Path(sysconfig.get_path("stdlib")) / "typing.py").read_text()
    request = _request(tmp_path, [_provider("typing", source)], imported="typing", binding="io")
    facts = _native_facts(request)
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize(
    ("declaration", "declared"),
    [
        ("Payload = object()\n", True),
        ("Payload: object = object()\n", True),
        ("def replace(fn): return 7\n@replace\ndef Payload(value): return value\n", True),
        ("def Payload(value): return value\n", False),
        ("class Payload: pass\n", False),
    ],
    ids=["assign", "annotated", "decorated", "function", "class"],
)
def test_registry_mutation_is_separate_from_a_lexical_provider_declaration(
    tmp_path, monkeypatch, declaration, declared
):
    source = "import sys\n" + declaration + "sys.modules[__name__] = None\n"
    provider = ModuleType("runtime_provider")
    monkeypatch.setitem(sys.modules, provider.__name__, provider)
    exec(source, provider.__dict__)
    assert sys.modules[provider.__name__] is None and "Payload" in provider.__dict__
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="Payload"
    )
    facts = _native_facts(request)
    assert bool(facts.provider_bindings) is declared
    if declared:
        assert facts.provider_bindings[0].kind is ProviderBindingKind.DECLARATION
    assert len(_route_records(facts)[0]) == (0 if declared else 1)


@pytest.mark.parametrize("decorator", [False, True], ids=["type-shape", "signature"])
@pytest.mark.parametrize("registry", [False, True], ids=["intact-registry", "replaced-registry"])
def test_provider_declaration_cannot_prove_value_shape_or_decorator_signature(
    tmp_path, decorator, registry
):
    source = (
        "def replace(fn): return 7\n@replace\ndef Payload(fn): return fn\n"
        if decorator
        else "Payload = factory()\n"
    )
    if registry:
        source += "import sys\nsys.modules[__name__] = None\n"
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="Payload"
    )
    api = (
        "@Payload\ndef keep(value: str) -> str: return value\n"
        if decorator
        else "def keep(value: Payload) -> Payload: return value\n"
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from value_tools import Payload\n" + api + "__all__ = ['Payload', 'keep']\n"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.kind.value == "declaration"
    routes, scan = _route_records(facts)
    assert not routes
    assert {
        (item["data"]["position"], item["data"]["reason"])
        for item in scan.unknowns
        if item["kind"] == "boundary_type_position"
    } == {
        (position, "ambiguous_facade" if decorator else "external_type")
        for position in ("value", "return")
    }
    assert _route_assessment(tmp_path, facts).status == "UNKNOWN"


@pytest.mark.parametrize(
    "body",
    [
        "def helper(globals): return globals\n",
        "def helper(source): exec(source)\n",
        "import sys\ndef helper(): return sys.modules.get(__name__)\n",
        "helper = lambda source: exec(source)\n",
        "import sys\nasync def helper(): return sys.modules.get(__name__)\n",
    ],
    ids=["local-globals", "deferred-exec", "deferred-registry-read", "lambda", "async"],
)
def test_deferred_provider_bodies_do_not_erase_direct_source_identity(tmp_path, body):
    source = "def convert(value): return value\n" + body
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="convert"
    )
    [binding] = _native_facts(request).provider_bindings
    assert binding.qualified_name == "value_tools.convert"


@pytest.mark.parametrize(
    "effect",
    [
        "exec(source)\n",
        "def holder(value=exec(source)): pass\n",
        "def holder(value: exec(source)): pass\n",
        "holder = lambda value=exec(source): value\n",
        "@exec(source)\ndef holder(): pass\n",
        "class Holder(exec(source)): pass\n",
        "class Holder:\n    import sys\n    sys.modules[__name__] = None\n",
        "class Holder:\n    exec(source)\n",
    ],
    ids=[
        "module",
        "default",
        "annotation",
        "lambda-default",
        "decorator",
        "base",
        "class-registry",
        "class-exec",
    ],
)
def test_eager_provider_identity_gaps_stay_unknown(tmp_path, effect):
    source = "def convert(value): return value\n" + effect
    request = _request(
        tmp_path, [_provider("value_tools", source)], imported="value_tools", binding="convert"
    )
    facts = _native_facts(request)
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize(
    ("suffix", "declared"),
    [
        ("\ncontextmanager = None\n", False),
        ("\nif conditional:\n    contextmanager = None\n", False),
        ("\ndef mutate():\n    global contextmanager\n    contextmanager = None\n", False),
        ("\nglobals()['contextmanager'] = None\n", False),
        # PEP 562: a module __getattr__ runs only for names that are missing.
        ("\ndef __getattr__(name):\n    return None\n", True),
        ("\nvalue = opaque()\n", True),
        ("\nimport unavailable\n", True),
        ("\nfrom unavailable import factory\n", True),
        ("\nfrom unavailable import contextmanager\n", False),
        ("\nfrom unavailable import *\n", False),
        ("\ndef contextmanager(func): return func\n", False),
        ("\ndel contextmanager\n", False),
        ("\nitems = [(contextmanager := None) for item in [1]]\n", False),
        ("\ndef helper(contextmanager): return contextmanager\n", True),
    ],
)
def test_provider_source_binders_and_runtime_effects_are_distinct(tmp_path, suffix, declared):
    request = _request(
        tmp_path, [_provider("contextlib", "def contextmanager(func): return func\n" + suffix)]
    )
    facts = _native_facts(request)
    assert bool(facts.provider_bindings) is declared
    assert len(_route_records(facts)[0]) == (0 if declared else 1)


_HOOK = "def __getattr__(name): return None\n"
_STAR = "from errno import *\n"


@pytest.mark.parametrize(
    ("source", "declared"),
    [
        (_HOOK + "class Payload: pass\n", False),
        ("class Payload: pass\n" + _HOOK, True),
        (_HOOK, False),
        ("class Payload: pass\n" + _HOOK + "Payload = 1\n", False),
        ("if flag:\n    class Payload: pass\n" + _HOOK, False),
        (_STAR + "class Payload: pass\n", True),
        ("try:\n    " + _STAR + "except ImportError:\n    pass\nclass Payload: pass\n", True),
        ("from unavailable import *\nclass Payload: pass\n", False),
        ("from .errno import *\nclass Payload: pass\n", False),
        (
            "class Other:\n    def __getattr__(self, name): return None\nclass Payload: pass\n"
            + _HOOK,
            True,
        ),
        ("class Payload: pass\n" + _STAR, False),
        (_STAR + "class Payload: pass\nfrom os import *\n", False),
        (_STAR, False),
        (_STAR + "class Payload: pass\nPayload = 1\n", False),
        (_STAR + "if flag:\n    class Payload: pass\n", False),
        (_STAR + "class Payload: pass\nglobals()['Payload'] = 1\n", False),
        (_STAR + "class Payload: pass\n" + _HOOK, True),
        (_STAR + _HOOK + "class Payload: pass\n", False),
        ("match handler:\n    case __getattr__:\n        pass\nclass Payload: pass\n", False),
        (
            "try:\n    pass\nexcept Exception as __getattr__:\n    pass\nclass Payload: pass\n",
            False,
        ),
    ],
    ids=[
        "hook-before",
        "hook-after",
        "hook-unbound",
        "hook-twice",
        "hook-conditional",
        "stdlib-star-before",
        "stdlib-star-in-try-before",
        "foreign-star-before",
        "relative-star-before",
        "method-hook-before",
        "star-after",
        "star-around",
        "star-unbound",
        "star-twice",
        "star-conditional",
        "star-dynamic-rebind",
        "star-then-hook-after",
        "star-then-hook-before",
        "match-capture-hook-before",
        "except-name-hook-before",
    ],
)
@pytest.mark.parametrize("module", ["textwrap", "value_tools"], ids=["stdlib", "third-party"])
def test_direct_binding_survives_missing_name_hooks_only_in_the_stdlib(
    tmp_path, source, declared, module
):
    # A hook or star import before the binding can answer during an import cycle.
    request = _request(tmp_path, [_provider(module, source)], imported=module, binding="Payload")
    facts = _native_facts(request)
    known = declared and module == "textwrap"
    assert [item.qualified_name for item in facts.provider_bindings] == (
        [f"{module}.Payload"] if known else []
    )
    assert len(_route_records(facts)[0]) == (0 if known else 1)


@pytest.mark.parametrize(
    "source",
    [
        "def contextmanager(\n",
        "if enabled:\n    def contextmanager(func): return func\n",
        "import sys as runtime\ndef contextmanager(func): return func\n"
        "runtime.modules[__name__] = None\n",
        "from sys import modules as registry\ndef contextmanager(func): return func\n"
        "registry[__name__] = None\n",
        "import sys\nsystem = sys\ndef contextmanager(func): return func\n"
        "system.modules[__name__] = None\n",
        "__path__ = ['elsewhere']\ndef contextmanager(func): return func\n",
        "class contextmanager(factory()): pass\n",
    ],
    ids=[
        "syntax",
        "conditional",
        "module-alias",
        "symbol-alias",
        "assigned-alias",
        "path",
        "base-call",
    ],
)
def test_provider_source_identity_gaps_remain_unknown(tmp_path, source):
    request = _request(tmp_path, [_provider("contextlib", source)])
    assert not _native_facts(request).provider_bindings


def test_package_parent_can_name_its_own_source_child(tmp_path):
    providers = [
        _provider("vendor", "from . import leaf\n", package=True),
        _provider("vendor.leaf", "def convert(): pass\n"),
    ]
    request = _request(tmp_path, providers, imported="vendor.leaf", binding="convert")
    assert [item.qualified_name for item in _native_facts(request).provider_bindings] == [
        "vendor.leaf.convert"
    ]


@pytest.mark.parametrize(
    "parent",
    [
        "leaf = None\n",
        "if conditional:\n    leaf = None\n",
        "def __getattr__(name): return None\n",
        "from somewhere import *\n",
        "import sys\nsys.modules[__name__].leaf = None\n",
        "__path__ = ['elsewhere']\n",
        "def mutate():\n    global leaf\n    leaf = None\n",
        "import vendor\np = vendor\np.leaf = None\n",
        "import vendor\nvendor.__dict__['leaf'] = None\n",
    ],
)
def test_package_initializer_precedence_and_dynamic_routes_remain_unknown(tmp_path, parent):
    providers = [
        _provider("vendor", parent, package=True),
        _provider("vendor.leaf", "def convert(): pass\n"),
    ]
    request = _request(tmp_path, providers, imported="vendor.leaf", binding="convert")
    facts = _native_facts(request)
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


def test_package_route_needs_its_initializer_source(tmp_path):
    child = _provider("vendor.leaf", "def convert(): pass\n")
    request = _request(tmp_path, [child], imported="vendor.leaf", binding="convert")
    assert not _native_facts(request).provider_bindings
    complete = replace(
        request,
        resolver=PythonSettings(provider_sources=(_provider("vendor", "", package=True), child)),
    )
    assert [item.qualified_name for item in _native_facts(complete).provider_bindings] == [
        "vendor.leaf.convert"
    ]


@pytest.mark.parametrize(
    "source",
    [
        "def contextmanager(func): return func\n",
        "contextmanager = factory()\n",
        "@replace\ndef contextmanager(func): return func\n",
    ],
    ids=["function", "assigned-declaration", "decorated-declaration"],
)
def test_stale_or_unrequested_provider_receipts_are_rejected(tmp_path, source):
    provider = _provider("contextlib", source)
    request = _request(tmp_path, [provider])
    facts = _native_facts(request)
    stale = replace(provider, source=provider.source + "\n", digest="0" * 64)
    with pytest.raises(ProtocolError, match="digest"):
        encode_request(replace(request, resolver=PythonSettings(provider_sources=(stale,))))
    with pytest.raises(ProtocolError, match="provider sources"):
        _requested_facts(facts, replace(request, resolver=PythonSettings()))
    stale_inputs = tuple(
        replace(item, digest="0" * 64) if item.path == provider.path else item
        for item in facts.inputs
    )
    with pytest.raises(ProtocolError, match="provider sources"):
        _requested_facts(replace(facts, inputs=stale_inputs), request)


@pytest.mark.parametrize("version", [ProtocolVersion.V1, ProtocolVersion.V2, ProtocolVersion.V3])
def test_legacy_protocols_cannot_carry_provider_claims(tmp_path, version):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    request = _request(tmp_path, [provider])
    with pytest.raises(ProtocolError, match="4.0.0"):
        encode_request(replace(request, protocol_version=version))
    with pytest.raises(ProtocolError, match="4.0.0"):
        encode_response(CollectionResponse(_native_facts(request), version))


def test_duplicate_provider_identity_is_rejected(tmp_path):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    request = _request(tmp_path, [provider, provider])
    with pytest.raises(ProtocolError, match="duplicate"):
        encode_request(request)


def test_unsupported_provider_constant_claim_is_rejected(tmp_path):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    request = _request(tmp_path, [provider])
    payload = json.loads(
        encode_response(CollectionResponse(_native_facts(request), ProtocolVersion.V4))
    )
    payload["facts"]["provider_bindings"][0]["kind"] = "static_constant"
    with pytest.raises(ProtocolError, match="ProviderBindingKind"):
        decode_response(json.dumps(payload).encode())


def test_capture_uses_source_files_without_importing_packages_and_rejects_ambiguous_sources(
    tmp_path, monkeypatch
):
    provider_root = tmp_path / "environment"
    provider_root.mkdir()
    monkeypatch.setattr(sys, "path", [str(provider_root)])
    (provider_root / "contextlib.py").write_text(
        "raise RuntimeError('must not run')\ndef contextmanager(func): return func\n"
    )
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: dict.fromkeys(("stdlib", "platstdlib", "purelib", "platlib"), str(provider_root)),
    )
    request = _request(tmp_path)
    sources = _captured_sources(request)
    assert [item.module for item in sources] == ["contextlib"]
    second = tmp_path / "second"
    second.mkdir()
    (second / "contextlib.py").write_text("def contextmanager(func): return func\n")
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: {
            "stdlib": str(provider_root),
            "platstdlib": str(provider_root),
            "purelib": str(second),
            "platlib": str(second),
        },
    )
    assert not _captured_sources(request)


@pytest.mark.parametrize(
    "state", ["active", "missing", "ambiguous", "selected", "bytecode", "native", "escaped"]
)
def test_capture_retains_active_overlay_sources_and_rejects_competing_origins(
    tmp_path, monkeypatch, state
):
    overlay = tmp_path / "overlay"
    base = tmp_path / "base-site"
    overlay.mkdir()
    base.mkdir()
    source = "raise RuntimeError('capture must not import')\nclass Item: pass\n"
    (base / "vendor.py").write_text(source)
    request = _request(tmp_path, imported="vendor", binding="Item")
    (tmp_path / "src/sample/api.py").write_text(
        "from vendor import Item\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['Item', 'keep']\n"
    )
    active = [str(base)]
    if state == "missing":
        active = []
    elif state == "selected":
        (tmp_path / "src/vendor.py").write_text("class Item: pass\n")
    elif state == "escaped":
        outside = tmp_path / "elsewhere.py"
        outside.write_text(source)
        (base / "vendor.py").unlink()
        (base / "vendor.py").symlink_to(outside)
    elif state in {"ambiguous", "bytecode", "native"}:
        competing = tmp_path / "competing"
        competing.mkdir()
        suffix = (
            ".py"
            if state == "ambiguous"
            else ".pyc"
            if state == "bytecode"
            else EXTENSION_SUFFIXES[0]
        )
        (competing / ("vendor" + suffix)).write_bytes(b"class Item: pass\n")
        active.append(str(competing))
    monkeypatch.setattr(sys, "path", active)
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: dict.fromkeys(("stdlib", "platstdlib", "purelib", "platlib"), str(overlay)),
    )
    sources = _captured_sources(request)
    assert bool(sources) is (state == "active")
    if state == "active":
        [captured] = sources
        assert captured.source == source
        assert captured.digest == hashlib.sha256(source.encode()).hexdigest()
        facts = _native_facts(replace(request, resolver=PythonSettings(provider_sources=sources)))
        assert _route_assessment(tmp_path, facts).status == "PASS"
    else:
        assert not _native_facts(request).provider_bindings


def test_provider_receipt_cannot_borrow_selected_evidence(tmp_path):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    facts = _native_facts(_request(tmp_path, [provider]))
    payload = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    payload["facts"]["provider_bindings"][0]["evidence_id"] = facts.files[0].evidence_id
    with pytest.raises(ProtocolError, match="separate resolution source"):
        decode_response(json.dumps(payload).encode())


def test_capture_respects_package_precedence_and_package_source_root(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    (first / "vendor").mkdir(parents=True)
    (first / "vendor/__init__.py").write_text("")
    (first / "vendor.py").write_text("raise RuntimeError('package takes precedence')\n")
    (second / "vendor").mkdir(parents=True)
    (second / "vendor/leaf.py").write_text("def convert(): pass\n")
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: {
            "stdlib": str(first),
            "platstdlib": str(first),
            "purelib": str(second),
            "platlib": str(second),
        },
    )
    sources = _captured_sources(_request(tmp_path, imported="vendor.leaf", binding="convert"))
    assert [source.path for source in sources] == [".archkeel-providers/vendor/__init__.py"]


@pytest.mark.parametrize("placement", ["module", "package", "package_source_wins"])
def test_capture_matches_native_extension_precedence_without_loading_code(
    tmp_path, monkeypatch, placement
):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "vendor.py").write_text("def convert(): pass\n")
    if placement != "module":
        (environment / "vendor").mkdir()
        (environment / "vendor/__init__.py").write_text("def convert(): pass\n")
    extension = environment / ("vendor/__init__" if placement == "package" else "vendor")
    extension = extension.with_suffix(EXTENSION_SUFFIXES[0])
    extension.write_bytes(b"never loaded")
    finder = FileFinder(
        str(environment), (ExtensionFileLoader, EXTENSION_SUFFIXES), (SourceFileLoader, [".py"])
    )
    spec = finder.find_spec("vendor")
    assert spec is not None
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: dict.fromkeys(("stdlib", "platstdlib", "purelib", "platlib"), str(environment)),
    )
    sources = _captured_sources(_request(tmp_path, imported="vendor", binding="convert"))
    if placement == "package_source_wins":
        assert isinstance(spec.loader, SourceFileLoader)
        assert [source.path for source in sources] == [".archkeel-providers/vendor/__init__.py"]
    else:
        assert isinstance(spec.loader, ExtensionFileLoader)
        assert spec.origin == str(extension)
        assert not sources


def test_capture_rejects_sourceless_package_precedence_and_builtin_shadow_sources(
    tmp_path, monkeypatch
):
    environment = tmp_path / "environment"
    (environment / "vendor").mkdir(parents=True)
    (environment / "vendor.py").write_text("def convert(): pass\n")
    (environment / "vendor/__init__.pyc").write_bytes(b"never loaded")
    (environment / "sys.py").write_text("def getsizeof(value): return 0\n")
    finder = FileFinder(
        str(environment), (SourceFileLoader, [".py"]), (SourcelessFileLoader, BYTECODE_SUFFIXES)
    )
    assert isinstance(finder.find_spec("vendor").loader, SourcelessFileLoader)
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: dict.fromkeys(("stdlib", "platstdlib", "purelib", "platlib"), str(environment)),
    )
    assert not _captured_sources(_request(tmp_path, imported="vendor", binding="convert"))
    assert not _captured_sources(_request(tmp_path, imported="sys", binding="getsizeof"))


@pytest.mark.parametrize("placement", ["local", "other_root", "same_root"])
def test_capture_respects_sourceless_module_precedence(tmp_path, monkeypatch, placement):
    environment = tmp_path / "environment"
    environment.mkdir()
    (environment / "vendor.py").write_text("def convert(): pass\n")
    competing = tmp_path if placement == "local" else environment
    if placement == "other_root":
        competing = tmp_path / "other"
        competing.mkdir()
    (competing / "vendor.pyc").write_bytes(b"never loaded")
    finder = FileFinder(
        str(competing), (SourceFileLoader, [".py"]), (SourcelessFileLoader, BYTECODE_SUFFIXES)
    )
    spec = finder.find_spec("vendor")
    assert spec is not None
    assert isinstance(
        spec.loader, SourceFileLoader if placement == "same_root" else SourcelessFileLoader
    )
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: {
            "stdlib": str(environment),
            "platstdlib": str(environment),
            "purelib": str(competing if placement == "other_root" else environment),
            "platlib": str(environment),
        },
    )
    sources = _captured_sources(_request(tmp_path, imported="vendor", binding="convert"))
    assert bool(sources) is (placement == "same_root")


@pytest.mark.parametrize(
    "source",
    [
        "def contextmanager(func): return func\n",
        "contextmanager = factory()\n",
        "@replace\ndef contextmanager(func): return func\n",
    ],
    ids=["function", "assigned-declaration", "decorated-declaration"],
)
def test_v4_provider_wire_agrees_with_published_schema_and_rejects_legacy_extensions(
    tmp_path, source
):
    import jsonschema
    from referencing import Registry, Resource

    provider = _provider("contextlib", source)
    request = _request(tmp_path, [provider])
    facts = _native_facts(request)
    schema_root = Path(__file__).parents[1] / "schema"
    schema = json.loads((schema_root / "source-facts.schema.json").read_text())
    validator = jsonschema.Draft202012Validator(schema)
    request_payload = json.loads(encode_request(request))
    response_payload = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    validator.validate(request_payload)
    validator.validate(response_payload)
    assert decode_response(json.dumps(response_payload).encode()).facts == facts
    common = json.loads((schema_root / "architecture-ir-common.schema.json").read_text())
    profile = json.loads((schema_root / "architecture-ir-python-decoded.schema.json").read_text())
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    receipt_schema = profile["properties"]["scope_observations"]["items"]
    [receipt] = [
        item
        for item in _route_records(facts)[1].scope_observations
        if item["kind"] == "source_provider_binding"
    ]
    jsonschema.Draft202012Validator(receipt_schema, registry=registry).validate(receipt)
    for payload in (request_payload, response_payload):
        payload["protocol_version"] = "3.0.0"
        with pytest.raises(jsonschema.ValidationError):
            validator.validate(payload)


@pytest.mark.parametrize("package", [False, True], ids=["module", "package"])
@pytest.mark.parametrize("parent_source", ["", "from . import leaf\n"])
def test_submodule_provider_receipt_uses_its_own_source_identity(tmp_path, package, parent_source):
    parent = _provider("vendor", parent_source, package=True)
    child = _provider("vendor.leaf", "VALUE = 1\n", package=package)
    request = _request(tmp_path, [parent, child], imported="vendor", binding="leaf")
    (tmp_path / "src/sample/api.py").write_text(
        "from vendor import leaf\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['leaf', 'keep']\n"
    )
    facts = _native_facts(request)
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "vendor.leaf" and binding.kind.value == "module"
    evidence = next(item for item in facts.evidence if item.id == binding.evidence_id)
    assert evidence.file == child.path
    missing = _native_facts(replace(request, resolver=PythonSettings()))
    assert len(_route_records(missing)[0]) == 1
    assert _route_records(facts)[0] == []
    assert facts.coverage == missing.coverage and facts.files == missing.files
    assert _route_assessment(tmp_path, facts).status == "PASS"

    stale_inputs = tuple(
        replace(item, digest="0" * 64) if item.path == child.path else item for item in facts.inputs
    )
    with pytest.raises(ProtocolError, match="provider sources"):
        _requested_facts(replace(facts, inputs=stale_inputs), request)
    with pytest.raises(ProtocolError, match="binding disagrees with requested source"):
        _requested_facts(
            replace(facts, provider_bindings=(replace(binding, qualified_name="vendor.other"),)),
            request,
        )
    payload = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    next(item for item in payload["facts"]["evidence"] if item["id"] == binding.evidence_id)[
        "file"
    ] = parent.path
    with pytest.raises(ProtocolError, match="separate resolution source"):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize(
    "parent",
    [
        "leaf = 1\n",
        "if condition:\n    leaf = 1\n",
        "def mutate():\n    global leaf\n    leaf = 1\n",
        "def __getattr__(name): return 1\n",
        "from somewhere import *\n",
        "import sys\nsys.modules[__name__].leaf = 1\n",
        "__path__ = ['elsewhere']\n",
    ],
)
def test_competing_parent_binding_never_claims_submodule_identity(tmp_path, parent):
    request = _request(
        tmp_path,
        [_provider("vendor", parent, package=True), _provider("vendor.leaf", "VALUE = 1\n")],
        imported="vendor",
        binding="leaf",
    )
    assert all(item.kind.value != "module" for item in _native_facts(request).provider_bindings)


@pytest.mark.parametrize(
    ("missing", "child_source"),
    [
        ("parent", ""),
        ("child", ""),
        ("invalid-child", "def broken(\n"),
        ("dynamic-child", "def __getattr__(name): return 1\n"),
    ],
)
def test_missing_submodule_source_does_not_close_the_route(tmp_path, missing, child_source):
    parent = _provider("vendor", "", package=True)
    child = _provider("vendor.leaf", child_source)
    sources = (
        [parent] if missing == "child" else [child] if missing == "parent" else [parent, child]
    )
    facts = _native_facts(_request(tmp_path, sources, imported="vendor", binding="leaf"))
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize("competing", ["none", "local", "ambiguous"])
def test_capture_discovers_from_import_submodules_without_loading_them(
    tmp_path, monkeypatch, competing
):
    environment = tmp_path / "environment"
    (environment / "vendor").mkdir(parents=True)
    (environment / "vendor/__init__.py").write_text("raise RuntimeError('never imported')\n")
    (environment / "vendor/leaf.py").write_text("raise RuntimeError('never imported')\n")
    other = tmp_path / "other"
    other.mkdir()
    if competing == "local":
        (tmp_path / "src/vendor").mkdir(parents=True)
        (tmp_path / "src/vendor/__init__.py").write_text("")
        (tmp_path / "src/vendor/leaf.py").write_text("")
    elif competing == "ambiguous":
        (other / "vendor").mkdir()
        (other / "vendor/__init__.py").write_text("")
        (other / "vendor/leaf.py").write_text("")
    monkeypatch.setattr(
        sysconfig,
        "get_paths",
        lambda: {
            "stdlib": str(environment),
            "platstdlib": str(environment),
            "purelib": str(other),
            "platlib": str(other),
        },
    )
    sources = _captured_sources(_request(tmp_path, imported="vendor", binding="leaf"))
    assert [item.module for item in sources] == (
        ["vendor", "vendor.leaf"] if competing == "none" else []
    )


def test_default_provider_port_certifies_actual_rich_box_submodule(tmp_path):
    request = replace(
        _request(tmp_path, imported="rich", binding="box"), protocol_version=ProtocolVersion.V3
    )
    (tmp_path / "src/sample/api.py").write_text(
        "from rich import box\ndef keep(value: str) -> str: return value\n"
        "__all__ = ['box', 'keep']\n"
    )
    facts = observer_for(Language.PYTHON).collector.collect(request)
    assert not isinstance(facts, CollectionError), facts
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "rich.box" and binding.kind.value == "module"
    evidence = next(item for item in facts.evidence if item.id == binding.evidence_id)
    assert evidence.file == ".archkeel-providers/rich/box.py"
    assert _route_records(facts)[0] == []
    assert _route_assessment(tmp_path, facts).status == "PASS"

    import jsonschema

    schema = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(
        json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    )


def test_native_provider_alias_retains_publishing_and_terminal_sources(tmp_path):
    sources = [
        _provider("vendor", "from .leaf import convert as public\n", package=True),
        _provider("vendor.leaf", "def convert(value): return value\n"),
    ]
    facts = _native_facts(_request(tmp_path, sources, imported="vendor", binding="public"))
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    alias = by_name["vendor.public"]
    assert alias.kind is ProviderBindingKind.ALIAS
    assert alias.target == "vendor.leaf.convert"
    evidence = {item.id: item for item in facts.evidence}
    assert evidence[alias.evidence_id].file == sources[0].path
    assert evidence[by_name[alias.target].evidence_id].file == sources[1].path
    assert _route_records(facts)[0] == []


@pytest.mark.parametrize("terminal", ["missing", "cycle", "conditional", "rebound"])
def test_provider_alias_without_a_unique_terminal_remains_unknown(tmp_path, terminal):
    source = {
        "missing": "",
        "cycle": "from vendor import public as convert\n",
        "conditional": "if choice:\n    def convert(value): return value\n",
        "rebound": "def convert(value): return value\nconvert = 1\n",
    }[terminal]
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", "from .leaf import convert as public\n", package=True),
                _provider("vendor.leaf", source),
            ],
            imported="vendor",
            binding="public",
        )
    )
    assert len(_route_records(facts)[0]) == 1


def test_native_provider_discovery_binds_actual_resources_files_in_two_passes(
    tmp_path, monkeypatch
):
    request = replace(
        _request(tmp_path, imported="importlib.resources", binding="files"),
        protocol_version=ProtocolVersion.V3,
    )
    calls = []
    native = ProcessCollector.collect_response

    def execute(collector, actual):
        calls.append(actual.resolver.phase)
        return native(collector, actual)

    monkeypatch.setattr(ProcessCollector, "collect_response", execute)
    facts = observer_for(Language.PYTHON).collector.collect(request)
    assert not isinstance(facts, CollectionError), facts
    assert calls == [PythonCollectionPhase.PROVIDERS, PythonCollectionPhase.COLLECT]
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    assert by_name["importlib.resources.files"].target == "importlib.resources._common.files"
    assert "importlib.resources._common.files" in by_name
    assert _route_records(facts)[0] == []
    assert all(not item.rel_path.startswith(".archkeel-providers/") for item in facts.files)


@pytest.mark.parametrize("change", ["target", "missing-target", "support", "foreign-publisher"])
def test_provider_alias_wire_rejects_unbound_proof_fields(tmp_path, change):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", "from .leaf import convert as public\n", package=True),
                _provider("vendor.leaf", "def convert(value): return value\n"),
            ],
            imported="vendor",
            binding="public",
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    alias = next(item for item in payload["facts"]["provider_bindings"] if item["kind"] == "alias")
    if change == "target":
        alias["target"] = "vendor.bad target"
    elif change == "missing-target":
        del alias["target"]
    elif change == "support":
        alias["supporting_evidence_ids"] = [facts.files[0].evidence_id]
    else:
        terminal = next(
            item for item in payload["facts"]["provider_bindings"] if item["kind"] != "alias"
        )
        alias["evidence_id"] = terminal["evidence_id"]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


def test_provider_discovery_readback_rejects_changed_provider_before_full_collection(
    tmp_path, monkeypatch
):
    request, provider, initial, _ = _provider_passes(tmp_path)
    calls = []

    source = provider.source + "\nchanged = True\n"
    changed = replace(provider, source=source, digest=hashlib.sha256(source.encode()).hexdigest())

    def bounded(_collector, actual):
        calls.append(actual)
        return CollectionResponse(initial, ProtocolVersion.V4, (changed,))

    monkeypatch.setattr(ProcessCollector, "collect_response", bounded)
    result = PythonProviderCollector(ProcessCollector(("native-python",))).collect(request)
    assert isinstance(result, CollectionError) and result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "changed after discovery" in result.message
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("publisher", "terminal", "known"),
    [
        ("from model import *\n", "__all__ = ['Payload']\nclass Payload: pass\n", True),
        ("from model import *\n", "class Payload: pass\n", False),
        (
            "from model import *\n",
            "if flag:\n    __all__ = ['Payload']\nclass Payload: pass\n",
            False,
        ),
        ("from model import *\n", "__all__ = ['Other']\nclass Payload: pass\n", False),
        (
            "from model import *\n",
            "__all__ = ['Payload']\n__all__.append('Other')\nclass Payload: pass\n",
            False,
        ),
        (
            "from model import *\n",
            "__all__ = ['Payload']\nclass Payload: pass\nclass Payload: pass\n",
            False,
        ),
        (
            "from model import *\nif flag:\n    Payload = 1\n",
            "__all__ = ['Payload']\nclass Payload: pass\n",
            False,
        ),
        (
            "if flag:\n    from model import *\n",
            "__all__ = ['Payload']\nclass Payload: pass\n",
            False,
        ),
        (
            "from model import *\nfrom other import *\n",
            "__all__ = ['Payload']\nclass Payload: pass\n",
            False,
        ),
        (
            "from model import *\ndef __getattr__(name): return None\n",
            "__all__ = ['Payload']\nclass Payload: pass\n",
            False,
        ),
    ],
)
def test_closed_star_alias_requires_its_complete_export_and_unique_terminal(
    tmp_path, publisher, terminal, known
):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", "", package=True),
                _provider("vendor.facade", publisher),
                _provider("model", terminal),
            ],
            imported="vendor.facade",
            binding="Payload",
        )
    )
    assert len(_route_records(facts)[0]) == (0 if known else 1)
    if known:
        alias = next(
            item for item in facts.provider_bindings if item.kind is ProviderBindingKind.ALIAS
        )
        assert alias.target == "model.Payload" and alias.supporting_evidence_ids
        evidence = {item.id: item for item in facts.evidence}
        assert evidence[alias.supporting_evidence_ids[0]].file == ".archkeel-providers/model.py"


@pytest.mark.parametrize(
    "change",
    [
        "none",
        "source-bool",
        "source-body",
        "missing-file",
        "side-hash",
        "loader-missing",
        "nested-filename",
    ],
)
def test_frozen_star_source_needs_matching_native_code_and_side_source(
    tmp_path, monkeypatch, change
):
    source = "__all__ = ['Payload']\nFLAG = 1\nclass Payload:\n    def run(self): return FLAG\n"
    code = compile(source, "<frozen model>", "exec", dont_inherit=True, optimize=sys.flags.optimize)
    environment = tmp_path / "stdlib"
    environment.mkdir()
    actual = (
        source.replace("FLAG = 1", "FLAG = True")
        if change == "source-bool"
        else source.replace("return FLAG", "return 7")
        if change == "source-body"
        else source
    )
    side = environment / "model.py"
    if change != "missing-file":
        side.write_text(actual if change != "side-hash" else actual + "changed = True\n")
    native_find = collect_owner.FrozenImporter.find_spec
    monkeypatch.setattr(
        collect_owner.FrozenImporter,
        "find_spec",
        lambda name: object() if name == "model" else native_find(name),
    )
    if change == "nested-filename":
        from types import CodeType

        constants = tuple(
            item.replace(co_filename="<wrong>") if isinstance(item, CodeType) else item
            for item in code.co_consts
        )
        code = code.replace(co_consts=constants)
    monkeypatch.setattr(
        collect_owner.FrozenImporter,
        "get_code",
        lambda name: None if change == "loader-missing" else code,
    )
    native_path = sysconfig.get_path
    monkeypatch.setattr(
        sysconfig,
        "get_path",
        lambda name, *args, **kwargs: (
            str(environment) if name == "stdlib" else native_path(name, *args, **kwargs)
        ),
    )
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", "from model import *\n", package=True),
                _provider("model", actual),
            ],
            imported="vendor",
            binding="Payload",
        )
    )
    assert len(_route_records(facts)[0]) == (0 if change == "none" else 1)


# A real top-level stdlib name (sched) stands for the published module.
_REGISTRY = "import sys\nimport sched\nsys.modules['json.leaf'] = sched\n"


@pytest.mark.parametrize(
    ("parent", "known"),
    [
        (_REGISTRY, True),
        (
            "import sched\nimport sys as _sys\n_sys.modules['json.leaf'] = sched\nleaf = sched\n",
            True,
        ),
        ("import sys\nimport sched\nif flag:\n    sys.modules['json.leaf'] = sched\n", False),
        ("import sys\nimport sched\nkey = 'json.leaf'\nsys.modules[key] = sched\n", False),
        ("import sys\nimport sched\nsys.modules['json.leaf'] = sched.inner\n", False),
        ("import sys\nimport sched\nsys.modules['other.leaf'] = sched\n", False),
        (_REGISTRY + "sys.modules['json.leaf'] = sched\n", False),
        (_REGISTRY + "import other\nsys.modules['json.leaf'] = other\n", False),
        (_REGISTRY + "del sys.modules['json.leaf']\n", False),
        (_REGISTRY + "def reset():\n    sys.modules['json.leaf'] = None\n", False),
        (_REGISTRY.replace("import sched", "import other as sched"), False),
        (_REGISTRY.replace("import sched", "from sched import sched"), False),
        (_REGISTRY + "sched = None\n", False),
        (_REGISTRY + "leaf = None\n", False),
        (_REGISTRY + "leaf = sys\n", False),
        (_REGISTRY + "def reset():\n    global leaf\n    leaf = None\n", False),
        (_REGISTRY + "def __getattr__(name): return None\n", False),
        ("import sched\nimport sys\nsys.modules['json.leaf'] = sched\n", True),
        (
            "import sys\nimport sched\nfrom .sched import x\nsys.modules['json.leaf'] = sched\n",
            False,
        ),
        ("import sys\nimport sched\nimport json.sched\nsys.modules['json.leaf'] = sched\n", False),
        (
            "import sys\nimport sched\nfrom . import sched as _m\n"
            "sys.modules['json.leaf'] = sched\n",
            False,
        ),
        ("import sys\nimport sched\nimport other\nsys.modules['json.leaf'] = sched\n", False),
        (_REGISTRY + "import other\nleaf = sched\n", False),
        (_REGISTRY + "from .tools import helper\n", False),
        (_REGISTRY + "import json.sched\n", False),
        (_REGISTRY + "import sched as m\nm.Payload = None\n", False),
        (_REGISTRY + "import importlib\nimportlib.import_module('sched').Payload = None\n", False),
        (_REGISTRY + "leaf = sched\nleaf.Payload = None\n", False),
        (_REGISTRY + "leaf = sched\nvalue = leaf.Payload\n", True),
        (_REGISTRY + "import other\nsys.__dict__['modules']['json.leaf'] = other\n", False),
    ],
    ids=[
        "exact",
        "aliased-registry-and-attribute",
        "conditional",
        "computed-key",
        "member-value",
        "foreign-key",
        "written-twice",
        "rewritten-to-other-module",
        "deleted",
        "deferred-write",
        "renamed-import",
        "from-import",
        "rebound-value",
        "rebound-attribute",
        "attribute-other-module",
        "attribute-global-rebind",
        "missing-name-hook",
        "sys-imported-after-value",
        "relative-submodule-import",
        "dotted-submodule-import",
        "relative-module-import",
        "other-import-before-write",
        "other-import-before-attribute",
        "relative-import-after",
        "dotted-import-after",
        "second-import-mutates",
        "importlib-mutates",
        "attribute-alias-mutates",
        "attribute-alias-read",
        "registry-namespace-rewrite",
    ],
)
def test_registry_published_child_is_an_alias_of_its_module(tmp_path, parent, known):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent, package=True),
                _provider("sched", "class Payload: pass\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    assert len(_route_records(facts)[0]) == (0 if known else 1)
    assert ("json.leaf.Payload" in by_name) is known
    if known:
        alias = by_name["json.leaf.Payload"]
        assert alias.kind is ProviderBindingKind.ALIAS and alias.target == "sched.Payload"
        evidence = {item.id: item for item in facts.evidence}
        assert evidence[alias.evidence_id].file == ".archkeel-providers/json/__init__.py"
        assert "sys.modules['json.leaf'] = sched" in evidence[alias.evidence_id].excerpt
        assert evidence[alias.supporting_evidence_ids[0]].file == ".archkeel-providers/sched.py"


_WRITE = "sys.modules['json.leaf'] = sched\n"


@pytest.mark.parametrize(
    ("parent", "known"),
    [
        ("import sys\nimport sched\n" + _WRITE, True),
        ("import sys as registry\nimport sched\nregistry.modules['json.leaf'] = sched\n", True),
        ("import sys\nimport sched\n" + _WRITE + "def read(sys): return sys\n", True),
        ("import sched\n" + _WRITE, False),
        ("from sys import modules\nimport sched\nmodules['json.leaf'] = sched\n", False),
        ("import sys\nimport sched\nsys = sched\n" + _WRITE, False),
        (
            "from types import SimpleNamespace\nsys = SimpleNamespace(modules={})\nimport sched\n"
            + _WRITE,
            False,
        ),
        ("if flag:\n    import sys\nimport sched\n" + _WRITE, False),
        ("def load():\n    import sys\nimport sched\n" + _WRITE, False),
        ("import sys\nimport sched\n" + _WRITE + "del sys\n", False),
        ("import sys\nimport sched\nfrom other import *\n" + _WRITE, False),
        ("import sys\nimport sys\nimport sched\n" + _WRITE, False),
        (
            "import sys\nimport sched\n"
            + _WRITE
            + "def reset():\n    global sys\n    sys = None\n",
            False,
        ),
        ("import sched\n" + _WRITE + "import sys\n", False),
        ("import sys\n" + _WRITE + "import sched\n", False),
    ],
    ids=[
        "plain-sys",
        "aliased-sys",
        "parameter-named-sys",
        "no-sys-import",
        "from-sys-import",
        "sys-rebound",
        "sys-local-object",
        "sys-conditional",
        "sys-in-function",
        "sys-deleted",
        "star-import",
        "sys-imported-twice",
        "sys-global-rebind",
        "sys-after-write",
        "value-after-write",
    ],
)
def test_registry_receiver_is_a_stable_sys_import(tmp_path, parent, known):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent, package=True),
                _provider("sched", "class Payload: pass\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    assert (
        "json.leaf.Payload" in {item.qualified_name for item in facts.provider_bindings}
    ) is known
    assert len(_route_records(facts)[0]) == (0 if known else 1)


@pytest.mark.parametrize(
    ("parent", "target", "expected"),
    [
        (_REGISTRY + "leaf = sched\n", "Payload = None\n", ProviderBindingKind.ALIAS),
        (_REGISTRY, "class Payload: pass\n", ProviderBindingKind.ALIAS),
        (_REGISTRY + "def __getattr__(name): return None\n", "class Payload: pass\n", None),
        ("import sys\nimport sched\nfrom . import leaf\n" + _WRITE, "class Payload: pass\n", None),
        (
            "import sys\nimport sched\nif flag:\n    " + _WRITE,
            "class Payload: pass\n",
            None,
        ),
    ],
    ids=["other-value", "same-class", "parent-hook", "child-imported-first", "conditional-write"],
)
def test_registry_publication_wins_over_a_captured_child_file(tmp_path, parent, target, expected):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent, package=True),
                _provider("json.leaf", "class Payload: pass\n"),
                _provider("sched", target),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    evidence = {item.id: item.file for item in facts.evidence}
    assert all(
        evidence[item.evidence_id] != ".archkeel-providers/json/leaf.py"
        for item in facts.provider_bindings
    )
    binding = by_name.get("json.leaf.Payload")
    assert (binding.kind if binding is not None else None) is expected
    if binding is not None:
        assert binding.target == "sched.Payload"


@pytest.mark.parametrize(
    ("parent", "kept"),
    [
        ("", True),
        ("def label(labels): return labels['json.leaf']\n", True),
        ("labels = {}\nlabels['json.leaf'] = 1\n", True),
        ("def env():\n    import os\n    return os.environ['json.leaf']\n", True),
        ("import sys\ndef path(): return sys.path['json.leaf']\n", True),
        ("class Other:\n    modules = {}\nOther.modules['json.leaf'] = 1\n", True),
        ("import sys\ndef other(): return sys.modules['json.other']\n", True),
        ("import sys\ndef read(): return sys.modules['json.leaf']\n", False),
        ("import sys\ndef drop(): del sys.modules['json.leaf']\n", False),
        ("import sys\ndef read(): return sys.modules.get('json.leaf')\n", False),
        ("import sys\ndef drop(): return sys.modules.pop('json.leaf')\n", False),
        ("import sys\ndef put(value): sys.modules.setdefault('json.leaf', value)\n", False),
        ("from sys import modules\ndef read(): return modules['json.leaf']\n", False),
        ("if flag:\n    import sys\ndef read(): return sys.modules['json.leaf']\n", False),
        ("import sys\nkey = 'json.' + 'leaf'\nloaded = sys.modules[key]\n", False),
        ("import sys\nregistry = sys.modules\n", False),
        ("import sys\nimport other\nsys.__dict__['modules']['json.leaf'] = other\n", False),
        ("import sys\ndef read(key): return sys.modules[key]\n", True),
        ("import sys\ndef escape(): return sys.modules\n", True),
    ],
    ids=[
        "empty",
        "unrelated-lookup",
        "unrelated-dict-write",
        "environment",
        "sys-path",
        "other-modules-attribute",
        "other-registry-key",
        "registry-read",
        "registry-del",
        "registry-get",
        "registry-pop",
        "registry-setdefault",
        "from-sys-modules",
        "unstable-sys",
        "computed-key",
        "registry-escape",
        "registry-namespace",
        "deferred-computed-key",
        "deferred-registry-escape",
    ],
)
def test_child_file_yields_only_to_module_registry_access(tmp_path, parent, kept):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent, package=True),
                _provider("json.leaf", "class Payload: pass\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    kinds = {item.qualified_name: item.kind for item in facts.provider_bindings}
    assert kinds == ({"json.leaf.Payload": ProviderBindingKind.CLASS} if kept else {})


_PUBLISH = "sys.modules['json.leaf'] = sched\n"


@pytest.mark.parametrize(
    ("parent", "known"),
    [
        ("import sys\nimport sched\n" + _PUBLISH, True),
        ("import sys\nimport sched, other\n" + _PUBLISH, False),
        ("import sys\nimport other, sched\n" + _PUBLISH, False),
        ("import sys\nimport other as alias, sched\n" + _PUBLISH, False),
        ("import sys, sched\n" + _PUBLISH, False),
        (
            "import sys as registry, other\nimport sched\nregistry.modules['json.leaf'] = sched\n",
            False,
        ),
        ("import other\nimport sys\nimport sched\n" + _PUBLISH, False),
        ("from other import helper\nimport sys\nimport sched\n" + _PUBLISH, False),
        ("import sys\nimport sched\n" + _PUBLISH + "import other\n", False),
        ("import sys\nimport sched\n" + _PUBLISH + "from other import first, second\n", False),
        ("import sys\nimport sched\n" + _PUBLISH + "def load():\n    import other\n", False),
        ("import sys\nimport sched\n" + _PUBLISH + "from json import other\n", False),
        ("import sys\nimport sched\n" + _PUBLISH + "from os.path import join\n", False),
        ("import sys\nimport sched\n" + _PUBLISH + "from .itertools import chain\n", False),
        ("from itertools import chain\nimport sys\nimport sched\n" + _PUBLISH, True),
        ("import sys\nimport sched\n" + _PUBLISH + "import itertools as tools, keyword\n", True),
        ("import sys\nimport sched\n" + _PUBLISH + "def load():\n    import heapq\n", True),
    ],
    ids=[
        "own-statement",
        "other-after-comma",
        "other-before-comma",
        "renamed-other-before-comma",
        "with-sys",
        "with-sys-alias",
        "other-statement-before",
        "other-from-import-before",
        "other-statement-after",
        "other-from-import-after",
        "other-import-in-function",
        "own-package-from-import",
        "dotted-from-import",
        "relative-stdlib-name",
        "stdlib-before",
        "stdlib-after",
        "stdlib-in-function",
    ],
)
def test_registry_publication_allows_no_foreign_import(tmp_path, parent, known):
    # A foreign module runs its own code at import time and can change the published module.
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent, package=True),
                _provider("sched", "class Payload: pass\n"),
                _provider("other", "import sched\nmodel.Payload = None\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    assert (
        "json.leaf.Payload" in {item.qualified_name for item in facts.provider_bindings}
    ) is known


_RESET = "reset = {0}.reset\nreset()\n"


@pytest.mark.parametrize(
    ("target", "extra", "known"),
    [("sched", "", True), ("model", "", False), ("model", _RESET, False)],
    ids=["stdlib-target", "third-party-target", "third-party-stored-call"],
)
def test_registry_publication_needs_a_stdlib_target(tmp_path, target, extra, known):
    # A stored member call runs code of the published module; only stdlib code is trusted.
    parent = f"import sys\nimport {target}\nsys.modules['json.leaf'] = {target}\n"
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", parent + extra.format(target), package=True),
                _provider(
                    target,
                    "import sys\nclass Payload: pass\n"
                    "def reset():\n    sys.modules[__name__].Payload = None\n",
                ),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    assert (
        "json.leaf.Payload" in {item.qualified_name for item in facts.provider_bindings}
    ) is known


def test_registry_alias_needs_the_published_module_source(tmp_path):
    facts = _native_facts(
        _request(
            tmp_path,
            [_provider("json", _REGISTRY, package=True)],
            imported="json.leaf",
            binding="Payload",
        )
    )
    assert not facts.provider_bindings
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize(
    ("parent", "known"),
    [
        (_REGISTRY, True),
        (_REGISTRY + "sys.modules['json.leaf'] = sched\n", False),
        ("import sys\nsys.modules[__name__] = None\n", False),
    ],
    ids=["child-write", "child-written-twice", "own-write"],
)
def test_child_registry_write_keeps_the_package_member_identity(tmp_path, parent, known):
    facts = _native_facts(
        _request(
            tmp_path,
            [_provider("json", parent + "class Payload: pass\n", package=True)],
            imported="json",
            binding="Payload",
        )
    )
    kinds = {item.qualified_name: item.kind for item in facts.provider_bindings}
    assert (kinds.get("json.Payload") is ProviderBindingKind.CLASS) is known


def test_actual_collections_member_has_a_class_receipt(tmp_path):
    source = (Path(sysconfig.get_path("stdlib")) / "collections/__init__.py").read_text()
    provider = _provider("collections", source, package=True)
    facts = _native_facts(_request(tmp_path, [provider], imported="collections", binding="Counter"))
    [binding] = facts.provider_bindings
    assert binding.qualified_name == "collections.Counter"
    assert binding.kind is ProviderBindingKind.CLASS
    assert not _route_records(facts)[0]


def test_registry_alias_needs_a_static_target_module(tmp_path):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("json", _REGISTRY, package=True),
                _provider("sched", "class Payload: pass\nexec(source)\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        )
    )
    assert "json.leaf.Payload" not in {item.qualified_name for item in facts.provider_bindings}
    assert len(_route_records(facts)[0]) == 1


def _registry_alias_case(tmp_path):
    request = _request(
        tmp_path,
        [
            _provider("json", _REGISTRY, package=True),
            _provider("sched", "class Payload: pass\n"),
        ],
        imported="json.leaf",
        binding="Payload",
    )
    request = replace(request, protocol_version=ProtocolVersion.V4)
    return request, collect(request)


@pytest.mark.parametrize(
    ("change", "accepted"),
    [("none", True), ("foreign-file", False), ("grandparent", False)],
)
def test_registry_alias_evidence_must_sit_in_the_parent_initializer(tmp_path, change, accepted):
    request, facts = _registry_alias_case(tmp_path)
    wire = json.loads(encode_response(CollectionResponse(facts, request.protocol_version)))
    [alias] = [item for item in wire["facts"]["provider_bindings"] if item["kind"] == "alias"]
    if change == "foreign-file":
        alias["evidence_id"] = alias["supporting_evidence_ids"][0]
    elif change == "grandparent":
        alias["qualified_name"] = "json.leaf.inner.Payload"
    if accepted:
        decode_response(json.dumps(wire).encode())
    else:
        with pytest.raises(ValueError, match="separate resolution source"):
            decode_response(json.dumps(wire).encode())


@pytest.mark.parametrize(
    ("qualified", "accepted"), [("json.leaf.Payload", True), ("json.leaf.inner.Payload", False)]
)
def test_requested_registry_alias_must_name_a_child_of_its_initializer(
    tmp_path, qualified, accepted
):
    request, facts = _registry_alias_case(tmp_path)
    facts = replace(
        facts,
        provider_bindings=tuple(
            replace(item, qualified_name=qualified)
            if item.kind is ProviderBindingKind.ALIAS
            else item
            for item in facts.provider_bindings
        ),
    )
    if accepted:
        _requested_facts(facts, request)
    else:
        with pytest.raises(ProtocolError, match="disagrees with requested source"):
            _requested_facts(facts, request)


@pytest.mark.parametrize(
    "parent",
    [
        _REGISTRY.replace("json", "vendor"),
        "import sys\nimport sched\nsys.modules['vendor.leaf'] = sched\nleaf = sched\n",
    ],
    ids=["exact", "with-attribute"],
)
def test_third_party_registry_layout_stays_unknown(tmp_path, parent):
    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", parent, package=True),
                _provider("sched", "class Payload: pass\n"),
            ],
            imported="vendor.leaf",
            binding="Payload",
        )
    )
    assert "vendor.leaf.Payload" not in {item.qualified_name for item in facts.provider_bindings}
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize(
    ("change", "known"),
    [
        ("", True),
        ("value = sched.Payload\n", True),
        ("class Local(sched.Payload): pass\n", True),
        ("sched.Payload = None\n", False),
        ("sched.Other = None\n", False),
        ("del sched.Payload\n", False),
        ("sched.count += 1\n", False),
        ("setattr(sched, 'Payload', None)\n", False),
        ("sched.__dict__['Payload'] = None\n", False),
        ("vars(sched)['Payload'] = None\n", False),
        ("alias = sched\nalias.Payload = None\n", False),
        ("def reset():\n    sched.Payload = None\n", False),
        ("sched.reset()\n", False),
    ],
    ids=[
        "unchanged",
        "member-read",
        "member-base",
        "assign",
        "assign-other",
        "delete",
        "augmented",
        "setattr",
        "namespace",
        "vars",
        "alias",
        "deferred-assign",
        "method-call",
    ],
)
@pytest.mark.parametrize("before", [True, False], ids=["before-write", "after-write"])
def test_registry_publication_needs_an_unchanged_module(tmp_path, change, known, before):
    parent = "import sys\nimport sched\n" + change + _WRITE if before else _REGISTRY + change
    facts = _native_facts(
        _request(
            tmp_path,
            [_provider("json", parent, package=True), _provider("sched", "class Payload: pass\n")],
            imported="json.leaf",
            binding="Payload",
        )
    )
    # Only `import sys` may stand between the import of the module and the write.
    expected = known and not (before and change)
    assert (
        "json.leaf.Payload" in {item.qualified_name for item in facts.provider_bindings}
    ) is expected


def _injected(facts, qualified, evidence_file):
    [evidence] = [item for item in facts.evidence if item.file == evidence_file][:1]
    alias = ProviderBinding(qualified, ProviderBindingKind.ALIAS, evidence.id, "sched.Payload")
    return replace(facts, provider_bindings=(*facts.provider_bindings, alias))


def test_requested_registry_alias_needs_its_published_target(tmp_path):
    request = replace(
        _request(
            tmp_path,
            [
                _provider("json", _REGISTRY, package=True),
                _provider("sched", "class Payload: pass\n"),
                _provider("other", "Payload = None\n"),
            ],
            imported="json.leaf",
            binding="Payload",
        ),
        protocol_version=ProtocolVersion.V4,
    )
    facts = collect(request)
    providers = request.resolver.provider_sources
    assert collect_owner._registry_aliases_proven(facts, providers)
    retargeted = replace(
        facts,
        provider_bindings=tuple(
            replace(item, target="other.Payload", supporting_evidence_ids=())
            if item.kind is ProviderBindingKind.ALIAS
            else item
            for item in facts.provider_bindings
        ),
    )
    assert not collect_owner._registry_aliases_proven(retargeted, providers)


@pytest.mark.parametrize(
    ("parent", "extra", "qualified", "evidence_file"),
    [
        (_REGISTRY, (), "json.ghost.Payload", ".archkeel-providers/json/__init__.py"),
        (_REGISTRY, (), "other.leaf.Payload", ".archkeel-providers/json/__init__.py"),
        (
            _REGISTRY,
            (_provider("json.real", "Payload = None\n"),),
            "json.real.Payload",
            ".archkeel-providers/json/__init__.py",
        ),
        (
            _REGISTRY.replace("json", "vendor") + "class Thing: pass\n",
            (),
            "vendor.leaf.Payload",
            ".archkeel-providers/vendor/__init__.py",
        ),
    ],
    ids=["unpublished-child", "foreign-package", "captured-child", "third-party-parent"],
)
def test_requested_registry_alias_needs_the_producer_proof(
    tmp_path, parent, extra, qualified, evidence_file
):
    package = evidence_file.split("/")[1]
    imported, binding = ("json.leaf", "Payload") if package == "json" else ("vendor", "Thing")
    request = replace(
        _request(
            tmp_path,
            [
                _provider(package, parent, package=True),
                _provider("sched", "class Payload: pass\n"),
                *extra,
            ],
            imported=imported,
            binding=binding,
        ),
        protocol_version=ProtocolVersion.V4,
    )
    facts = collect(request)
    providers = request.resolver.provider_sources
    assert collect_owner._registry_aliases_proven(facts, providers)
    assert not collect_owner._registry_aliases_proven(
        _injected(facts, qualified, evidence_file), providers
    )


def test_provider_collector_rejects_an_unproven_registry_alias(tmp_path, monkeypatch):
    request = replace(
        _request(tmp_path, imported="collections.abc", binding="Iterator"),
        protocol_version=ProtocolVersion.V3,
    )
    checked = []

    def unproven(facts, providers):
        checked.append(providers)
        return False

    monkeypatch.setattr(collect_owner, "_registry_aliases_proven", unproven)
    result = observer_for(Language.PYTHON).collector.collect(request)
    assert isinstance(result, CollectionError) and checked
    assert result.kind is CollectionErrorKind.PROTOCOL_ERROR


def test_default_provider_discovery_binds_actual_collections_iterator(tmp_path, monkeypatch):
    request = replace(
        _request(tmp_path, imported="collections.abc", binding="Iterator"),
        protocol_version=ProtocolVersion.V3,
    )
    calls = []
    native = ProcessCollector.collect_response

    def execute(collector, actual):
        calls.append(actual.resolver.phase)
        return native(collector, actual)

    monkeypatch.setattr(ProcessCollector, "collect_response", execute)
    facts = observer_for(Language.PYTHON).collector.collect(request)
    assert not isinstance(facts, CollectionError), facts
    assert calls == [PythonCollectionPhase.PROVIDERS, PythonCollectionPhase.COLLECT]
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    alias = by_name["collections.abc.Iterator"]
    assert alias.target == "_collections_abc.Iterator"
    assert alias.supporting_evidence_ids
    assert alias.target in by_name
    assert _route_records(facts)[0] == []


@pytest.mark.parametrize(("left", "right"), [("True", "1"), ("0.0", "-0.0")])
def test_frozen_code_comparison_retains_constant_types_and_signed_zero(left, right):
    from archkeel.analyzer.python.source import _same_provider_code

    original = compile("VALUE = " + left, "<frozen model>", "exec")
    changed = compile("VALUE = " + right, "<frozen model>", "exec")
    assert _same_provider_code(original, original)
    assert not _same_provider_code(original, changed)


@pytest.mark.parametrize("field", ["target", "support"])
def test_direct_provider_encoding_cannot_silently_discard_alias_fields(tmp_path, field):
    facts = _native_facts(
        _request(tmp_path, [_provider("contextlib", "def contextmanager(func): return func\n")])
    )
    [binding] = facts.provider_bindings
    forged = (
        replace(binding, target="other.value")
        if field == "target"
        else replace(binding, supporting_evidence_ids=(binding.evidence_id,))
    )
    with pytest.raises(
        ProtocolError, match="direct provider binding cannot carry alias proof fields"
    ):
        encode_response(
            CollectionResponse(replace(facts, provider_bindings=(forged,)), ProtocolVersion.V4)
        )


def test_alias_receipts_roundtrip_both_provenance_sources_in_published_schemas(tmp_path):
    import jsonschema
    from referencing import Registry, Resource

    facts = _native_facts(
        _request(
            tmp_path,
            [
                _provider("vendor", "from model import *\n", package=True),
                _provider("model", "__all__ = ['Payload']\nclass Payload: pass\n"),
            ],
            imported="vendor",
            binding="Payload",
        )
    )
    schema_root = Path(__file__).parents[1] / "schema"
    schema = json.loads((schema_root / "source-facts.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(
        json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    )
    common = json.loads((schema_root / "architecture-ir-common.schema.json").read_text())
    profile = json.loads((schema_root / "architecture-ir-python-decoded.schema.json").read_text())
    registry = Registry().with_resource(common["$id"], Resource.from_contents(common))
    receipt = next(
        item
        for item in _route_records(facts)[1].scope_observations
        if item["kind"] == "source_provider_binding" and item["data"].get("target")
    )
    jsonschema.Draft202012Validator(
        profile["properties"]["scope_observations"]["items"], registry=registry
    ).validate(receipt)
    assert receipt["data"]["target"] == "model.Payload"
    assert len(receipt["evidence_ids"]) == 2


@pytest.mark.parametrize(
    "statement", ["from .missing import Payload\n", "from .missing import *\n"]
)
def test_unresolved_relative_provider_alias_keeps_other_receipts_and_unknown_route(
    tmp_path, statement
):
    request = _request(
        tmp_path,
        [
            _provider("contextlib", "def contextmanager(func): return func\n"),
            _provider("facade", statement),
        ],
    )
    api = tmp_path / "src/sample/api.py"
    api.write_text(
        "from contextlib import contextmanager\nfrom facade import Payload\n"
        "__all__ = ['contextmanager', 'Payload']\n"
    )
    facts = _native_facts(request)
    assert {item.qualified_name for item in facts.provider_bindings} == {
        "contextlib.contextmanager"
    }
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize("route", ["direct", "alias-target", "alias-origin", "module"])
@pytest.mark.parametrize(
    "declaration", ["class MadeUp: pass\n", "def MadeUp(): pass\n", "MadeUp = factory()\n"]
)
@pytest.mark.parametrize(
    ("module", "importer"),
    [("_collections_abc", collect_owner.FrozenImporter), ("_abc", collect_owner.BuiltinImporter)],
)
def test_forged_interpreter_provider_cannot_supply_any_binding_kind(
    tmp_path, route, declaration, module, importer
):
    assert importer.find_spec(module) is not None
    sources = [_provider(module, declaration)]
    imported = module
    if route == "alias-target":
        imported = "vendor"
        sources.append(_provider("vendor", f"from {module} import MadeUp\n"))
    elif route == "alias-origin":
        sources[0] = _provider(module, "from model import MadeUp\n")
        sources.append(_provider("model", declaration))
    elif route == "module":
        sources[0] = _provider(module, "", package=True)
        sources.append(_provider(f"{module}.MadeUp", "VALUE = 1\n"))
    facts = _native_facts(_request(tmp_path, sources, imported=imported, binding="MadeUp"))
    assert all(not item.qualified_name.startswith(f"{module}.") for item in facts.provider_bindings)
    assert len(_route_records(facts)[0]) == 1


@pytest.mark.parametrize("alias", [False, True], ids=["direct", "normal-alias"])
def test_real_frozen_provider_keeps_direct_and_normal_alias_source_binding(tmp_path, alias):
    source = (Path(sysconfig.get_path("stdlib")) / "_collections_abc.py").read_text()
    sources = [_provider("_collections_abc", source)]
    imported = "_collections_abc"
    if alias:
        imported = "vendor"
        sources.append(_provider("vendor", "from _collections_abc import Iterator\n"))
    facts = _native_facts(_request(tmp_path, sources, imported=imported, binding="Iterator"))
    assert "_collections_abc.Iterator" in {item.qualified_name for item in facts.provider_bindings}
    assert _route_records(facts)[0] == []


def test_provider_recapture_is_killed_by_the_native_process_deadline(tmp_path):
    request = replace(
        _request(tmp_path, imported="math", binding="cos"),
        protocol_version=ProtocolVersion.V3,
    )
    marker = tmp_path / "provider-capture-started"
    code = (
        "import time\nfrom pathlib import Path\n"
        "from archkeel.analyzer.python import entry\n"
        "def blocked_capture(request, facts):\n"
        f"    Path({str(marker)!r}).write_text('started')\n"
        "    time.sleep(30)\n    return ()\n"
        "entry.provider_sources = blocked_capture\nentry.main()\n"
    )
    started = time.monotonic()
    result = PythonProviderCollector(
        ProcessCollector((sys.executable, "-I", "-B", "-c", code), timeout_seconds=0.6)
    ).collect(request)
    elapsed = time.monotonic() - started
    assert marker.read_text() == "started"
    assert isinstance(result, CollectionError) and result.kind is CollectionErrorKind.TIMEOUT
    assert elapsed < 3, f"blocked provider capture escaped its process deadline: {elapsed}"


def test_provider_capture_shares_the_native_response_output_limit(tmp_path):
    request = replace(
        _request(tmp_path, imported="math", binding="cos"),
        resolver=PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
    )
    baseline = encode_response(CollectionResponse(_native_facts(request), ProtocolVersion.V4))
    limit = len(baseline) + 1024
    native = ProcessCollector(
        (sys.executable, "-I", "-B", "-m", "archkeel.analyzer.python.entry"),
        output_limit_bytes=limit,
    )
    assert isinstance(native.collect_response(request), CollectionResponse)
    code = (
        "import hashlib\nfrom archkeel.analyzer.python import entry\n"
        "from archkeel.ir.protocol import PythonProviderSource\n"
        "source = '#' + 'x' * 100000\n"
        "provider = PythonProviderSource('vendor', '.archkeel-providers/vendor.py', "
        "source, hashlib.sha256(source.encode()).hexdigest())\n"
        "entry.provider_sources = lambda request, facts: (provider,)\nentry.main()\n"
    )
    result = replace(native, argv=(sys.executable, "-I", "-B", "-c", code)).collect_response(
        request
    )
    assert isinstance(result, CollectionError) and result.kind is CollectionErrorKind.PROTOCOL_ERROR
    assert "output exceeded" in result.message


@pytest.mark.parametrize("change", ["missing", "extra", "changed", "wrong-phase"])
def test_captured_provider_buffers_are_bound_to_the_exact_discovery_manifest(tmp_path, change):
    request, provider, initial, _ = _provider_passes(tmp_path)
    request = replace(
        request,
        resolver=PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
        protocol_version=ProtocolVersion.V4,
    )
    providers = (provider,)
    if change == "missing":
        providers = ()
    elif change == "extra":
        providers += (_provider("extra", "value = 1\n"),)
    elif change == "changed":
        providers = (_provider("contextlib", "def contextmanager(func): return None\n"),)
    else:
        request = replace(request, resolver=PythonSettings())
    response = CollectionResponse(initial, ProtocolVersion.V4, providers)
    with pytest.raises(ProtocolError, match="captured provider sources disagree"):
        _requested_provider_sources(response, request)


@pytest.mark.parametrize("change", ["digest", "duplicate", "identity", "missing-field"])
def test_captured_provider_wire_rejects_invalid_buffers(tmp_path, change):
    _, provider, initial, _ = _provider_passes(tmp_path)
    payload = json.loads(
        encode_response(CollectionResponse(initial, ProtocolVersion.V4, (provider,)))
    )
    if change == "digest":
        payload["provider_sources"][0]["source"] += "changed = True\n"
    elif change == "duplicate":
        payload["provider_sources"] *= 2
    elif change == "identity":
        payload["provider_sources"][0]["module"] = "unbound"
    else:
        del payload["provider_sources"]
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())


@pytest.mark.parametrize("version", [ProtocolVersion.V1, ProtocolVersion.V2, ProtocolVersion.V3])
def test_captured_provider_buffers_cannot_leak_into_legacy_envelopes(tmp_path, version):
    request, provider, _, _ = _provider_passes(tmp_path)
    facts = _native_facts(request)
    payload = json.loads(encode_response(CollectionResponse(facts, version)))
    assert "provider_sources" not in payload
    payload["provider_sources"] = []
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(payload).encode())
    with pytest.raises(ProtocolError, match="captured provider sources require"):
        encode_response(CollectionResponse(facts, version, (provider,)))


@pytest.mark.parametrize(
    "version",
    [ProtocolVersion.V4, ProtocolVersion.V6, ProtocolVersion.V7, ProtocolVersion.V8],
)
def test_captured_provider_response_roundtrips_against_the_published_schema(tmp_path, version):
    from jsonschema import Draft202012Validator

    _, provider, initial, _ = _provider_passes(tmp_path)
    response = CollectionResponse(initial, version, (provider,))
    payload = encode_response(response)
    schema = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_text())
    validator = Draft202012Validator(schema)
    document = zlib.decompress(payload) if version is ProtocolVersion.V8 else payload
    validator.validate(json.loads(document))
    assert decode_response(payload) == response
    assert encode_response(decode_response(payload)) == payload
    for legacy_version in (ProtocolVersion.V1, ProtocolVersion.V2, ProtocolVersion.V3):
        legacy = json.loads(document)
        legacy["protocol_version"] = legacy_version
        assert not validator.is_valid(legacy)


@pytest.mark.parametrize(
    "version",
    [ProtocolVersion.V4, ProtocolVersion.V6, ProtocolVersion.V7, ProtocolVersion.V8],
)
def test_full_python_facts_cannot_claim_provider_capture_buffers(tmp_path, version):
    request, provider, _, _ = _provider_passes(tmp_path)
    with pytest.raises(
        ProtocolError, match="captured provider sources require a Python import survey"
    ):
        decode_response(
            encode_response(CollectionResponse(_native_facts(request), version, (provider,)))
        )


@pytest.mark.parametrize(
    "access", ["none", "f_globals", "f_builtins", "opaque-call", "direct-base", "dataclass"]
)
def test_native_creation_requires_the_retained_namespace_proof(tmp_path, access):
    from test_boundary_types_non_init_facades import _write_app

    helpers = (
        "import sys\n"
        "class Replacement:\n"
        "    def __init_subclass__(cls):\n"
        "        namespace = sys.modules[cls.__module__].__dict__\n"
        "        namespace['Base'].get = lambda self: {}\n"
        "def produce():\n    yield 1\nstream = produce()\n"
        "def mutate(value):\n    import typing\n    typing.TypedDict = Replacement\n"
        "def replace_dataclass(value):\n"
        "    import dataclasses\n"
        "    def replace(cls):\n"
        "        namespace = sys.modules[cls.__module__].__dict__\n"
        "        namespace['Base'].get = lambda self: {}\n"
        "        return cls\n"
        "    dataclasses.dataclass = replace\n"
    )
    prefix = {
        "none": "",
        "f_globals": (
            "from helpers import stream\n"
            "stream.gi_frame.f_globals.get('__builtins__')['__import__']('typing').TypedDict = "
            "stream.gi_frame.f_globals.get('Replacement')\n"
        ),
        "f_builtins": (
            "from helpers import stream\n"
            "stream.gi_frame.f_builtins.get('__import__')('typing').TypedDict = "
            "stream.gi_frame.f_builtins.get('__import__')('helpers').Replacement\n"
        ),
        "opaque-call": "from helpers import stream, mutate\nmutate(stream)\n",
        "direct-base": "from helpers import Replacement\n",
        "dataclass": "from helpers import stream, replace_dataclass\nreplace_dataclass(stream)\n",
    }[access]
    base = "Replacement" if access == "direct-base" else "TypedDict"
    owner = "@dataclass\nclass Owner" if access == "dataclass" else f"class Owner({base})"
    factory_import = (
        ""
        if access == "direct-base"
        else "from dataclasses import dataclass\n"
        if access == "dataclass"
        else "from typing import TypedDict\n"
    )
    source = (
        prefix
        + factory_import
        + (
            "class Base:\n    def get(self) -> str: return ''\n"
            f"{owner}:\n    value: 'str'\n"
            "class Child(Base): pass\n"
        )
    )
    _write_app(tmp_path, public=["sample.app.api:Child"], init="", api=source, implementation="")
    (tmp_path / "helpers.py").write_text(helpers)
    # Run provider mutation in a separate interpreter so typing in the test process stays intact.
    runtime = subprocess.run(
        [
            sys.executable,
            "-c",
            "import json,sys\nfrom types import ModuleType\n"
            "api = ModuleType('runtime_api'); sys.modules['runtime_api'] = api\n"
            f"exec({source!r}, api.__dict__)\n"
            "print(json.dumps(api.Child().get()))\n",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert json.loads(runtime.stdout) == ("" if access == "none" else {})
    facts = _native_facts(
        CollectionRequest(
            SnapshotInput(str(tmp_path), "a" * 40, False),
            SourceScope(("sample",), "sample"),
            PythonSettings(provider_sources=(_provider("helpers", helpers),)),
            ProtocolVersion.V4,
        )
    )
    observation, _ = assemble_observation(
        facts,
        contract_root=tmp_path,
        contract_path=tmp_path / "contract.json",
        roots=("sample",),
        namespace="sample",
        language=Language.PYTHON,
    )
    undecided = Counter(
        rule for record in observation.records("unknowns") or () for rule in record.rule_ids
    )
    [assessment] = rule_assessments(observation, undecided_by_rule=undecided)
    assert assessment.status == ("PASS" if access == "none" else "UNKNOWN")
    assert assessment.undecided == 0 if access == "none" else assessment.undecided >= 1
    symbols = {
        record.data.get("name"): record
        for record in observation.records("symbols") or ()
        if record.data.get("qualified_name")
        in {"sample.app.api.Base", "sample.app.api.Child", "sample.app.api.Owner"}
    }
    assert all(symbol.data.get("source_binding_unique") is True for symbol in symbols.values())
    for name in ("Base", "Child"):
        assert symbols[name].data.get("source_member_binding_static") is (access == "none")
    assert (symbols["Owner"].data.get("typed_dict_header_static") is True) is (access == "none")
