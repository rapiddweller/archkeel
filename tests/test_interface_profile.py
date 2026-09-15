# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Verify the AD-9 measurement tool's dedup and module-entry rules on a tiny model."""

from archkeel.ir.model import (
    AnalyzerInfo,
    ArchitectureContract,
    ComponentRole,
    ContractComponent,
    ContractInfo,
    Coverage,
    EvidenceClass,
    Observation,
    Record,
    RecordData,
    Section,
    SourceInfo,
)
from tools.interface_profile import build_profile

_COVERAGE = Coverage(
    status="PASS",
    files_discovered=0,
    files_read=0,
    files_parsed=0,
    calls_analyzed=0,
    calls_resolved=0,
    calls_partially_resolved=0,
    calls_unresolved=0,
    ast_coverage_percent=100.0,
    call_resolution_percent=100.0,
    failures=(),
)


def _import(
    source: str, target: str, symbol: str | None, origin_definition: str | None = ""
) -> Record:
    # A real analyzer always sets origin_definition when symbol is set (it defaults to
    # "target.symbol" and only differs once a re-export chain is followed).
    if origin_definition == "":
        origin_definition = f"{target}.{symbol}" if symbol else None
    return Record(
        id=f"IMP-{source}-{target}-{symbol}",
        evidence_class=EvidenceClass.FACT,
        area="dependencies",
        kind="import",
        title="import",
        subjects=(source, target),
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=(),
        data=RecordData(
            (
                ("source_module", source),
                ("target_module", target),
                ("symbol", symbol),
                ("origin_definition", origin_definition),
                ("symbol_visibility", "private" if symbol and symbol.startswith("_") else None),
                ("under_type_checking", False),
            )
        ),
    )


def _module(name: str, all_exports: tuple[str, ...] = ()) -> Record:
    return Record(
        id=f"MOD-{name}",
        evidence_class=EvidenceClass.FACT,
        area="module_topology",
        kind="module",
        title=name,
        subjects=(name,),
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=(),
        data=RecordData((("qualified_name", name), ("all_exports", all_exports))),
    )


def _function(module: str, name: str, returns: str | None = None) -> Record:
    return Record(
        id=f"SYM-{module}-{name}",
        evidence_class=EvidenceClass.FACT,
        area="repository_topology",
        kind="function",
        title=name,
        subjects=(f"{module}.{name}",),
        evidence_ids=(),
        rule_ids=(),
        fact_ids=(),
        provenance=(),
        data=RecordData(
            (
                ("module", module),
                ("name", name),
                ("parent", None),
                ("symbol_category", "function"),
                ("visibility", "public_name"),
                ("parameters", ()),
                ("returns", returns),
            )
        ),
    )


def _contract() -> ArchitectureContract:
    def component(id_: str, label: str, package: str) -> ContractComponent:
        return ContractComponent(
            id=id_,
            label=label,
            role=ComponentRole.COMPONENT,
            packages=(package,),
            responsibilities=(),
            forbidden_responsibilities=(),
            provenance=(),
        )

    return ArchitectureContract(
        schema_version="2.0.0",
        components=(component("COMP-A", "a", "pkg.a"), component("COMP-B", "b", "pkg.b")),
        rules=(),
    )


def _observation(
    imports: tuple[Record, ...], modules: tuple[Record, ...], symbols: tuple[Record, ...]
) -> Observation:
    return Observation(
        schema_version="test",
        analyzer=AnalyzerInfo(name="test", version="0", code_digest="0"),
        source=SourceInfo(git_head="0", dirty=False, source_digest="0", scope=()),
        contract=ContractInfo(
            schema_version="2.0.0", digest="0", path="architecture-contract.json"
        ),
        coverage=_COVERAGE,
        sections=(
            Section("imports", imports),
            Section("modules", modules),
            Section("symbols", symbols),
        ),
        evidence=(),
    )


def test_module_entry_rule_and_dedup() -> None:
    # pkg.b.half: 2 public names, one used -> half rule qualifies -> one module entry.
    # pkg.b.rare: 4 public names, one used -> below half -> one symbol entry.
    # pkg.b.whole: bare "import pkg.b.whole" -> forced module entry regardless of usage.
    imports = (
        _import("pkg.a.mod", "pkg.b.half", "foo"),
        _import("pkg.a.mod", "pkg.b.half", "foo"),  # duplicate use must not double-count
        _import("pkg.a.mod", "pkg.b.rare", "f1"),
        _import("pkg.a.mod", "pkg.b.whole", None),
    )
    modules = (_module("pkg.b.half"), _module("pkg.b.rare"), _module("pkg.b.whole"))
    symbols = (
        _function("pkg.b.half", "foo"),
        _function("pkg.b.half", "bar"),
        _function("pkg.b.rare", "f1"),
        _function("pkg.b.rare", "f2"),
        _function("pkg.b.rare", "f3"),
        _function("pkg.b.rare", "f4"),
    )
    observation = _observation(imports, modules, symbols)
    profile = build_profile(observation, _contract())

    assert profile["crossing_imports"] == 4
    assert profile["edges"] == 1
    surface = profile["surface"]["b"]
    assert surface == {
        "symbol_entries": 3,  # half:foo, rare:f1, whole (module token)
        "module_first_entries": 3,  # half entry + whole entry + rare:f1
        "module_level_modules": 2,  # half, whole
    }
    assert (
        surface["module_level_modules"]
        <= surface["module_first_entries"]
        <= surface["symbol_entries"]
    )
    assert profile["contract_lines"] == {"symbol_only": 3, "module_first": 3}
    assert profile["module_imports"] == 1
    # foo and f1 each contribute one return position; the whole-module token has no
    # symbol name so it never joins a function record.
    assert profile["signature_positions"] == 2
    assert profile["unknown_positions"] == 2  # neither return annotation is given


def test_signature_lookup_follows_the_reexport_chain() -> None:
    # pkg.b (a package) re-exports Widget from pkg.b.impl; the crossing import names
    # pkg.b, not pkg.b.impl, so the join must follow origin_definition to find it.
    imports = (_import("pkg.a.mod", "pkg.b", "Widget", origin_definition="pkg.b.impl.Widget"),)
    modules = (_module("pkg.b"), _module("pkg.b.impl"))
    symbols = (_function("pkg.b.impl", "Widget"),)
    observation = _observation(imports, modules, symbols)
    profile = build_profile(observation, _contract())

    assert profile["signature_positions"] == 1
    assert profile["unknown_positions"] == 1


def test_anonymize_drops_component_labels() -> None:
    from tools.interface_profile import _anonymize

    imports = (_import("pkg.a.mod", "pkg.b.half", "foo"),)
    modules = (_module("pkg.b.half"),)
    symbols = (_function("pkg.b.half", "foo"),)
    observation = _observation(imports, modules, symbols)
    contract = _contract()
    profile = _anonymize(build_profile(observation, contract), contract)
    assert set(profile["surface"]) == {"C2"}  # a=C1, b=C2, sorted by label
