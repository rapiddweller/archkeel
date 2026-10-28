# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Native contextmanager signatures retain source identity and fail closed."""

import json
from dataclasses import replace
from pathlib import Path

import pytest
from test_python_provider_sources import _native_facts, _provider

from archkeel.analyzer.python.collect import collect, provider_sources
from archkeel.ir.facts import ContextManagerSignature, contextmanager_signature
from archkeel.ir.facts_codec import ProtocolError, decode_response, encode_response, freeze_data
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

_PROGRESS = """from collections.abc import Iterator
from contextlib import contextmanager

@contextmanager
def progress(message: str) -> Iterator[None]:
    yield
"""


def _native_case(
    tmp_path: Path,
    source: str = _PROGRESS,
    providers=None,
    final_version: ProtocolVersion = ProtocolVersion.V4,
):
    package = tmp_path / "sample"
    package.mkdir(exist_ok=True)
    (package / "__init__.py").write_text("")
    (package / "api.py").write_text(source)
    request = CollectionRequest(
        SnapshotInput(str(tmp_path), "a" * 40, False),
        SourceScope(("sample",), "sample"),
        PythonSettings(phase=PythonCollectionPhase.PROVIDERS),
        ProtocolVersion.V4,
    )
    discovered = collect(request)
    captured = provider_sources(request, discovered) if providers is None else providers
    final = replace(
        request,
        resolver=PythonSettings(provider_sources=tuple(captured)),
        protocol_version=final_version,
    )
    return _native_facts(final), tuple(captured)


def _signature(facts):
    symbol = next(
        row
        for section in facts.sections
        for row in section.records
        if row.data.get("qualified_name") == "sample.api.progress"
    )
    value = symbol.data.get("contextmanager_signature")
    return symbol, contextmanager_signature(value) if value is not None else None


@pytest.mark.parametrize("version", [ProtocolVersion.V4, ProtocolVersion.V5])
def test_actual_native_contextmanager_keeps_original_signature(tmp_path, version):
    facts, _ = _native_case(tmp_path, final_version=version)
    symbol, signature = _signature(facts)
    assert isinstance(signature, ContextManagerSignature)
    assert symbol.data.get("returns") == "Iterator[None]"
    assert symbol.data.get("signature_decorators_proven") is False
    assert signature.effective_return.wrapper == "contextlib._GeneratorContextManager"
    assert signature.effective_return.payload == "None"
    assert signature.factory == "contextlib.contextmanager"
    assert signature.partial.implementation == "cpython"
    assert signature.partial.version == facts.runtime.version
    assert dict(facts.type_shapes)["None"]
    assert facts == decode_response(encode_response(CollectionResponse(facts, version))).facts


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("@contextmanager\n", "@contextmanager()\n"),
        lambda s: s.replace("@contextmanager\n", "@other\n@contextmanager\n"),
        lambda s: s + "\ncontextmanager = lambda fn: fn\n",
        lambda s: s + "\nIterator = list\n",
        lambda s: s.replace("def progress(", "async def progress("),
        lambda s: s.replace("    yield\n", "    def nested(): yield\n"),
    ],
)
def test_unproved_source_decorator_or_iterator_is_not_a_signature(tmp_path, change):
    facts, _ = _native_case(tmp_path, change(_PROGRESS))
    assert _signature(facts)[1] is None


def test_contextmanager_signature_rejects_missing_and_extra_fields():
    for value in (None, {}, {"kind": "sync-generator-contextmanager-v1"}):
        with pytest.raises(ValueError):
            contextmanager_signature(freeze_data(value))


@pytest.fixture(scope="module")
def native_sources(tmp_path_factory):
    return _native_case(tmp_path_factory.mktemp("context-sources"))[1]


@pytest.mark.parametrize(
    ("module", "before", "after"),
    [
        (
            "contextlib",
            "class _GeneratorContextManagerBase:\n",
            "class _GeneratorContextManagerBase:\n    def __new__(cls, *args): return 7\n",
        ),
        (
            "contextlib",
            "class _GeneratorContextManagerBase:\n",
            "class _GeneratorContextManagerBase:\n"
            "    def __getattribute__(self, name): return iter([7])\n",
        ),
        ("contextlib", "def __enter__(self):", "def __enter__(self, extra):"),
        (
            "contextlib",
            "class ContextDecorator(object):",
            "class ContextDecorator(object, Unknown):",
        ),
        ("contextlib", "def _recreate_cm(self):", "@replacement\n    def _recreate_cm(self):"),
        ("abc", "def abstractmethod(funcobj):", "@replacement\ndef abstractmethod(funcobj):"),
        ("abc", "def abstractmethod(funcobj):", "def abstractmethod(funcobj, extra):"),
        (
            "abc",
            "def __new__(mcls, name, bases, namespace, /, **kwargs):",
            "def __new__(mcls, name, bases, namespace):",
        ),
        (
            "abc",
            "class ABCMeta(type):",
            "class ABCMeta(type):\n        def __call__(cls, *args): return 7",
        ),
        ("functools", "return wrapper\n", "return wrapped\n"),
        ("functools", "'__qualname__', '__doc__'", "'__qualname__', '__code__'"),
        ("_collections_abc", "class Iterator(Iterable):", "class Iterator(object):"),
    ],
)
def test_changed_source_chain_cannot_supply_effective_signature(
    tmp_path, native_sources, module, before, after
):
    original = next(item for item in native_sources if item.module == module)
    assert before in original.source
    changed = _provider(module, original.source.replace(before, after))
    sources = tuple(changed if item.module == module else item for item in native_sources)
    assert _signature(_native_case(tmp_path, providers=sources)[0])[1] is None


def test_exit_body_of_another_runtime_keeps_signature_unproved(tmp_path, native_sources):
    original = next(item for item in native_sources if item.module == "contextlib")
    # 3.11 throws (typ, value, traceback); 3.12 to 3.14 throw (value) only.
    swapped = (
        original.source.replace("self.gen.throw(typ, value, traceback)", "THROW")
        .replace("self.gen.throw(value)", "self.gen.throw(typ, value, traceback)")
        .replace("THROW", "self.gen.throw(value)")
    )
    assert swapped != original.source
    sources = tuple(
        _provider("contextlib", swapped) if item.module == "contextlib" else item
        for item in native_sources
    )
    assert _signature(_native_case(tmp_path, providers=sources)[0])[1] is None


@pytest.mark.parametrize(
    ("imported", "proven"),
    [
        ("from _functools import partial, reduce", True),
        ("from _functools import reduce, partial", False),
        ("from _functools import partial as other, reduce as partial", False),
    ],
    ids=["partial-first", "partial-second", "partial-renamed"],
)
def test_native_partial_must_bind_first_in_its_import(tmp_path, native_sources, imported, proven):
    original = next(item for item in native_sources if item.module == "functools")
    assert "from _functools import partial" in original.source
    source = original.source.replace("from _functools import partial", imported, 1)
    sources = tuple(
        _provider("functools", source) if item.module == "functools" else item
        for item in native_sources
    )
    assert (_signature(_native_case(tmp_path, providers=sources)[0])[1] is not None) is proven


@pytest.mark.parametrize(("slots", "proven"), [("()", True), ('("gen",)', False)])
def test_abstract_context_manager_accepts_only_empty_slots(tmp_path, native_sources, slots, proven):
    original = next(item for item in native_sources if item.module == "contextlib")
    member = "    __class_getitem__ = classmethod(GenericAlias)\n"
    assert member in original.source
    # Python 3.13 and later declare empty slots; drop them before the test adds its own.
    source = original.source.replace("    __slots__ = ()\n", "", 1)
    source = source.replace(member, member + f"    __slots__ = {slots}\n", 1)
    sources = tuple(
        _provider("contextlib", source) if item.module == "contextlib" else item
        for item in native_sources
    )
    assert (_signature(_native_case(tmp_path, providers=sources)[0])[1] is not None) is proven


def test_factory_helper_and_wrapper_names_are_source_bound(tmp_path, native_sources):
    original = next(item for item in native_sources if item.module == "contextlib")
    source = original.source.replace("contextmanager", "managed")
    source = source.replace("helper", "forwarder").replace("_GeneratorContextManager", "_Managed")
    sources = tuple(item for item in native_sources if item.module != "contextlib")
    sources += (_provider("source_context", source),)
    progress = _PROGRESS.replace(
        "from contextlib import contextmanager",
        "from source_context import managed as contextmanager",
    )
    signature = _signature(_native_case(tmp_path, progress, sources)[0])[1]
    assert signature is not None
    assert signature.factory == "source_context.managed"
    assert signature.effective_return.wrapper == "source_context._Managed"


@pytest.mark.parametrize("missing", ["contextlib", "functools", "abc", "_collections_abc"])
def test_missing_actual_source_keeps_signature_unproved(tmp_path, native_sources, missing):
    sources = tuple(item for item in native_sources if item.module != missing)
    assert _signature(_native_case(tmp_path, providers=sources)[0])[1] is None


@pytest.mark.parametrize(
    "binding", ["from fake_types import GenericAlias", "GenericAlias = object"]
)
def test_abstract_generic_alias_needs_its_unique_source_import(tmp_path, native_sources, binding):
    original = next(item for item in native_sources if item.module == "contextlib")
    source = original.source + "\n" + binding + "\n"
    if binding.startswith("from "):
        source = source.replace(
            "from types import MethodType, GenericAlias", "from types import MethodType"
        )
    sources = tuple(
        _provider("contextlib", source) if item.module == "contextlib" else item
        for item in native_sources
    )
    assert _signature(_native_case(tmp_path, providers=sources)[0])[1] is None


def test_intrinsic_needs_supported_runtime_and_actual_native_members(monkeypatch):
    from types import ModuleType

    from archkeel.analyzer.python import callable_signatures as owner

    assert owner._partial_intrinsic() is not None
    assert owner._abc_intrinsic() is not None
    with monkeypatch.context() as changed:
        changed.setattr(owner.sys, "version_info", (3, 15, 0))
        assert owner._partial_intrinsic() is None
    changed_module = ModuleType("_functools")
    changed_module.partial = type("partial", (), {})
    monkeypatch.setattr(owner, "_builtin_module", lambda name: changed_module)
    assert owner._partial_intrinsic() is None
    assert owner._abc_intrinsic() is None


@pytest.mark.parametrize(
    ("module_name", "member"),
    [("_functools", "partial")]
    + [
        ("_abc", name)
        for name in (
            "get_cache_token",
            "_abc_init",
            "_abc_register",
            "_abc_instancecheck",
            "_abc_subclasscheck",
            "_get_dump",
            "_reset_registry",
            "_reset_caches",
        )
    ],
)
def test_intrinsic_requires_every_named_native_member(monkeypatch, module_name, member):
    from archkeel.analyzer.python import callable_signatures as owner

    module = owner._builtin_module(module_name)
    assert module is not None
    with monkeypatch.context() as changed:
        changed.delattr(module, member)
        assert (
            owner._partial_intrinsic() if module_name == "_functools" else owner._abc_intrinsic()
        ) is None


def test_native_module_attribute_fallback_is_never_executed(monkeypatch):
    from archkeel.analyzer.python import callable_signatures as owner

    module = owner._builtin_module("_functools")
    assert module is not None
    original = module.partial
    calls = []

    def fallback(name):
        calls.append(name)
        return original

    with monkeypatch.context() as changed:
        changed.setattr(module, "__getattr__", fallback, raising=False)
        changed.delattr(module, "partial")
        assert owner._partial_intrinsic() is None
    assert calls == []


@pytest.mark.parametrize("subclass", [False, True])
def test_partial_lookalike_cannot_borrow_native_member_identity(monkeypatch, subclass):
    from archkeel.analyzer.python import callable_signatures as owner

    module = owner._builtin_module("_functools")
    assert module is not None
    original = module.partial
    members = {"__module__": "functools"}
    if not subclass:
        members.update(__new__=original.__new__, __call__=original.__call__)
    fake = type("partial", (original,) if subclass else (), members)
    with monkeypatch.context() as changed:
        changed.setattr(module, "partial", fake)
        assert owner._partial_intrinsic() is None


@pytest.mark.parametrize("change", ["missing", "origin", "name", "loader"])
def test_native_module_needs_actual_builtin_spec(monkeypatch, change):
    from importlib.machinery import BuiltinImporter, ModuleSpec

    from archkeel.analyzer.python import callable_signatures as owner

    module = owner._builtin_module("_functools")
    assert module is not None
    spec = ModuleSpec(
        "wrong" if change == "name" else "_functools",
        BuiltinImporter,
        origin="source" if change == "origin" else "built-in",
    )
    if change == "loader":
        spec.loader = None
    with monkeypatch.context() as changed:
        if change == "missing":
            changed.delattr(module, "__spec__")
        else:
            changed.setattr(module, "__spec__", spec)
        assert owner._builtin_module("_functools") is None


def _wire(tmp_path):
    facts, _ = _native_case(tmp_path)
    wire = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    data = next(
        row["data"]
        for section in wire["facts"]["sections"]
        for row in section["records"]
        if row["data"].get("qualified_name") == "sample.api.progress"
    )
    return wire, data


@pytest.mark.parametrize(
    ("part", "key", "value"),
    [
        ("source", "returns", "Iterator[str]"),
        ("source", "namespace_bound", False),
        ("source", "decorators", ["unbound"]),
        ("proof", "factory", "functools.wraps"),
        ("proof", "support_evidence_ids", ["missing"]),
        ("effective", "payload", "str"),
        ("effective", "wrapper", "other.Wrapper"),
        ("partial", "version", "3.10.0"),
        ("partial", "cache_tag", "cpython-310"),
        ("partial", "implementation", "pypy"),
        ("partial", "origin", "source"),
        ("abc", "members", ["_abc_init"]),
        ("abc", "module", "fake_abc"),
    ],
)
def test_wire_cannot_retarget_or_damage_native_signature(tmp_path, part, key, value):
    wire, source = _wire(tmp_path)
    proof = source["contextmanager_signature"]
    parts = {
        "source": source,
        "proof": proof,
        "effective": proof["effective_return"],
        "partial": proof["partial"],
        "abc": proof["abc"],
    }
    parts[part][key] = value
    with pytest.raises(ProtocolError):
        decode_response(json.dumps(wire).encode())


@pytest.mark.parametrize("version", [ProtocolVersion.V1, ProtocolVersion.V2, ProtocolVersion.V3])
def test_effective_signatures_require_v4(tmp_path, version):
    facts, _ = _native_case(tmp_path)
    with pytest.raises(ProtocolError, match="protocol 4"):
        encode_response(CollectionResponse(facts, version))


def test_wire_cannot_copy_signature_onto_foreign_iterator_carrier(tmp_path, native_sources):
    source = (
        _PROGRESS
        + """
from carrier import Carrier
@contextmanager
def foreign() -> Carrier[None]:
    yield
"""
    )
    sources = native_sources + (_provider("carrier", "class Carrier: pass\n"),)
    facts, _ = _native_case(tmp_path, source, sources)
    wire = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    symbols = {
        row["data"].get("name"): row["data"]
        for section in wire["facts"]["sections"]
        for row in section["records"]
        if row["kind"] == "function"
    }
    assert "contextmanager_signature" not in symbols["foreign"]
    symbols["foreign"]["contextmanager_signature"] = symbols["progress"]["contextmanager_signature"]
    with pytest.raises(ProtocolError, match="bound factory/wrapper/iterator"):
        decode_response(json.dumps(wire).encode())


def test_wire_cannot_substitute_foreign_provider_support(tmp_path):
    wire, data = _wire(tmp_path)
    proof = data["contextmanager_signature"]
    proof["support_evidence_ids"] = [wire["facts"]["provider_bindings"][0]["evidence_id"]]
    with pytest.raises(ProtocolError, match="bound factory/wrapper/iterator"):
        decode_response(json.dumps(wire).encode())


@pytest.mark.parametrize("change", ["copy", "extra-selected"])
def test_wire_cannot_copy_signature_onto_same_carrier_nongenerator(tmp_path, change):
    source = (
        _PROGRESS
        + """
@contextmanager
def nongenerator() -> Iterator[None]:
    return None
"""
    )
    facts, _ = _native_case(tmp_path, source)
    wire = json.loads(encode_response(CollectionResponse(facts, ProtocolVersion.V4)))
    symbols = {
        row["data"].get("name"): row
        for section in wire["facts"]["sections"]
        for row in section["records"]
        if row["kind"] == "function"
    }
    assert "contextmanager_signature" not in symbols["nongenerator"]["data"]
    proof = symbols["progress"]["data"]["contextmanager_signature"]
    if change == "copy":
        symbols["nongenerator"]["data"]["contextmanager_signature"] = proof
    else:
        proof["support_evidence_ids"].extend(symbols["nongenerator"]["evidence_ids"])
    with pytest.raises(ProtocolError, match="source evidence|provider support"):
        decode_response(json.dumps(wire).encode())


def test_published_schema_accepts_native_signature(tmp_path):
    import jsonschema

    wire, _ = _wire(tmp_path)
    schema = json.loads((Path(__file__).parents[1] / "schema/source-facts.schema.json").read_text())
    jsonschema.Draft202012Validator(schema).validate(wire)
