# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""External binding receipts retain source scope and fail closed on changed inputs."""

import hashlib
import json
import os
import sysconfig
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest
from collector_pin import assembled

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.cli.observe import observer_for
from archkeel.ir.codec import parse_contract
from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import Language, ProviderBinding, ProviderBindingKind
from archkeel.ir.facts_codec import (
    ProtocolError,
    encode_request,
    encode_response,
)
from archkeel.ir.protocol import (
    CollectionError,
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


def test_custom_python_collector_argv_keeps_single_pass_composition():
    observer = observer_for(Language.PYTHON, collector_argv=("custom-python", "--fixture"))
    assert isinstance(observer.collector, ProcessCollector)
    assert observer.collector.argv == ("custom-python", "--fixture")


@pytest.mark.parametrize("language", [Language.DART, Language.TYPESCRIPT])
def test_other_default_languages_keep_the_original_process_collector(language):
    assert isinstance(observer_for(language).collector, ProcessCollector)


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
    observation, _ = assembled(
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


def _pathlib_star_providers():
    """The real pathlib files of Python 3.13, or a skip: the facade stars two sources."""
    stdlib = Path(sysconfig.get_path("stdlib"))
    init = stdlib / "pathlib/__init__.py"
    if not (init.is_file() and "from ._local import *" in init.read_text()):
        pytest.skip("pathlib publishes Path only through two star imports (Python 3.13)")
    return [
        _provider("pathlib", init.read_text(), package=True),
        *(
            _provider(f"pathlib.{name}", (stdlib / f"pathlib/{name}.py").read_text())
            for name in ("_abc", "_local")
        ),
    ]


_HOOK = "def __getattr__(name): return None\n"
_STAR = "from errno import *\n"


def test_duplicate_provider_identity_is_rejected(tmp_path):
    provider = _provider("contextlib", "def contextmanager(func): return func\n")
    request = _request(tmp_path, [provider, provider])
    with pytest.raises(ProtocolError, match="duplicate"):
        encode_request(request)


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


def test_native_provider_discovery_binds_actual_resources_files_in_one_pass(tmp_path, monkeypatch):
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
    assert calls == [PythonCollectionPhase.PROVIDERS]
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    assert by_name["importlib.resources.files"].target == "importlib.resources._common.files"
    assert "importlib.resources._common.files" in by_name
    assert _route_records(facts)[0] == []
    assert all(not item.rel_path.startswith(".archkeel-providers/") for item in facts.files)


_EXPORTS_PAYLOAD = "__all__ = ['Payload']\nclass Payload: pass\n"
_EXPORTS_OTHER = "__all__ = ['Other']\nclass Other: pass\n"


# A real top-level stdlib name (sched) stands for the published module.
_REGISTRY = "import sys\nimport sched\nsys.modules['json.leaf'] = sched\n"


_WRITE = "sys.modules['json.leaf'] = sched\n"


_PUBLISH = "sys.modules['json.leaf'] = sched\n"


_RESET = "reset = {0}.reset\nreset()\n"


def _injected(facts, qualified, evidence_file):
    [evidence] = [item for item in facts.evidence if item.file == evidence_file][:1]
    alias = ProviderBinding(qualified, ProviderBindingKind.ALIAS, evidence.id, "sched.Payload")
    return replace(facts, provider_bindings=(*facts.provider_bindings, alias))


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
    assert calls == [PythonCollectionPhase.PROVIDERS]
    by_name = {item.qualified_name: item for item in facts.provider_bindings}
    alias = by_name["collections.abc.Iterator"]
    assert alias.target == "_collections_abc.Iterator"
    assert alias.supporting_evidence_ids
    assert alias.target in by_name
    assert _route_records(facts)[0] == []


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _provider_of(facts):
    item = next(item for item in facts.inputs if item.path.startswith(".archkeel-providers/"))
    return PythonProviderSource("contextlib", item.path, "", item.digest)
