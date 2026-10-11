# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A direct alias permission binds source origin and every syntactic payload leaf."""

from __future__ import annotations

import json
import subprocess
import sys
from itertools import permutations
from pathlib import Path

import pytest
from test_analyzer import _observe
from test_boundary_type_opaque_map_values import _app
from test_boundary_types_contained_mapping import _commit_report_fixture

from archkeel.analyzer.python.type_shapes import collect_type_shapes
from archkeel.check.evaluation.boundary_types import _boundary_type_verdict, boundary_type_indexes
from archkeel.ir.codec import (
    decode_canonical_model,
    observation_payload,
    parse_contract,
    parse_observation,
)
from archkeel.ir.model import Observation, Record, RecordData
from archkeel.ir.trace import trace_valid_violations

_BODY = (
    "tuple[tuple[str, list[object]] | tuple[str, list[object], Metadata], list[dict[str, object]]]"
)
_SHAPE = _BODY.replace("Metadata", "sample.app.types.Metadata")
_BINDING = {"origin": "sample.app.impl:Packet", "shape": _SHAPE}
_SELECTIONS = [(), (0,), (1,), (2,), (3,), (0, 1, 2, 3)]


def _selectors(facade: bool) -> list[dict[str, object]]:
    owner = f"sample.app{'' if facade else '.impl'}.Session"
    return [
        {
            "qualified_name": f"{owner}.{method}",
            "position": position,
            "annotation": "Packet",
            "alias_body": _BINDING,
            **({"container_depth": 3} if depth else {}),
        }
        for method, position in [("prepare", "return"), ("dispatch", "packet")]
        for depth in [None, 3]
    ]


def _fixture(
    root: Path,
    *,
    facade: bool = False,
    selected: tuple[int, ...] = (0, 1, 2, 3),
    body: str = _BODY,
    prefix: str = "",
    metadata: str = "class Metadata:\n    label: str\n",
    annotation: str = "Packet",
    change: dict[str, object] | None = None,
    bound: bool = True,
    alias_module: bool = False,
    metadata_module: str = "types",
    alias_suffix: str = "",
) -> None:
    owner = f"sample.app{'' if facade else '.impl'}"
    source = (
        f"from .{metadata_module} import Metadata\n"
        + prefix
        + ("from .moved import Packet\n" if alias_module else f"Packet = {body}\n")
        + alias_suffix
        + "class Session:\n"
        + f"    def prepare(self) -> {annotation}: pass\n"
        + f"    def dispatch(self, packet: {annotation}) -> None: pass\n"
        + "    def unrelated(self, counts: dict[str, int]) -> None: pass\n"
        + "    def undecided(self, value: Missing) -> None: pass\n"
    )
    selectors = _selectors(facade)
    if not bound:
        selectors = [
            {key: value for key, value in item.items() if key != "alias_body"} for item in selectors
        ]
    _app(
        root,
        source=source,
        declared=(
            f"{owner}:Session",
            f"sample.app.{metadata_module}:Metadata",
            f"sample.app.{metadata_module}:Other",
        ),
        allowances=tuple({**selectors[index], **(change or {})} for index in selected),
    )
    (root / f"sample/app/{metadata_module}.py").write_text(
        metadata + "class Other:\n    label: str\n"
    )
    (root / "sample/app/moved.py").write_text(
        "from .types import Metadata\n" + f"Packet = {body}\n"
    )
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import Session\n__all__ = ['Session']\n"
        )
    contract_path = root / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = "3.0.0"
    contract_path.write_text(json.dumps(contract))
    (root / "pyproject.toml").write_text(
        '[project]\nname = "sample"\nversion = "0.0.0"\nrequires-python = ">=3.11"\n'
    )
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


def _facts(observation: Observation) -> list[Record]:
    return [
        item
        for item in observation.records("typing_signals") or ()
        if item.kind == "boundary_type_allowance"
    ]


def _targets(observation: Observation) -> list[Record]:
    return [
        item
        for item in trace_valid_violations(observation)
        if str(item.data.get("qualified_name")).endswith((".prepare", ".dispatch"))
    ]


def _unknowns(observation: Observation) -> tuple[Record, ...]:
    return tuple(
        item
        for item in observation.records("unknowns") or ()
        if item.kind == "boundary_type_position"
    )


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("selected", _SELECTIONS)
def test_four_exact_selectors_are_independent_and_keep_unrelated_evidence(
    tmp_path: Path, facade: bool, selected: tuple[int, ...]
) -> None:
    _fixture(tmp_path, facade=facade, selected=())
    before = _observe(tmp_path)
    assert before.observation is not None and before.diagnostics == ()
    unrelated = tuple(
        item
        for item in trace_valid_violations(before.observation)
        if item not in _targets(before.observation)
    )
    unknowns = _unknowns(before.observation)
    assert len(_targets(before.observation)) == 4 and unrelated and unknowns
    _fixture(tmp_path, facade=facade, selected=selected)
    after = _observe(tmp_path)
    assert after.observation is not None and after.diagnostics == ()
    assert len(_targets(after.observation)) == 4 - len(selected)
    assert (
        tuple(
            item
            for item in trace_valid_violations(after.observation)
            if item not in _targets(after.observation)
        )
        == unrelated
    )
    assert _unknowns(after.observation) == unknowns
    facts = _facts(after.observation)
    assert len(facts) == len(selected)
    evidence = {item.id: item for item in after.observation.evidence}
    symbols = {item.id: item for item in after.observation.records("symbols") or ()}
    for fact in facts:
        pair = fact.data.get("alias_body")
        assert isinstance(pair, RecordData) and dict(pair.entries) == _BINDING
        assert fact.provenance == ("docs/architecture/sample.md",)
        assert fact.rule_ids == ("APP-TYPES-NOT-DICT",)
        locations = [evidence[item].file for item in fact.evidence_ids]
        assert "sample/app/impl.py" in locations and "sample/app/types.py" in locations
        assert any(symbols[item].kind == "type_alias" for item in fact.fact_ids if item in symbols)
        assert any(symbols[item].kind == "method" for item in fact.fact_ids if item in symbols)
        if fact.data.get("container_depth") == 3:
            assert fact.data.get("accepted_opacity") is True
            assert "type closure remains unproven" in fact.title
        else:
            assert fact.data.get("accepted_opacity") is None
    repeat = _observe(tmp_path)
    assert repeat.observation is not None
    assert _facts(repeat.observation) == facts
    assert trace_valid_violations(repeat.observation) == trace_valid_violations(after.observation)


@pytest.mark.parametrize("facade", [False, True])
def test_unbound_alias_keeps_the_original_four_findings(tmp_path: Path, facade: bool) -> None:
    _fixture(tmp_path, facade=facade, bound=False)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_targets(result.observation)) == 4 and _facts(result.observation) == []


_MUTATIONS = [
    {"body": _BODY.replace("dict[str, object]", "dict[int, object]")},
    {"body": _BODY.replace("list[dict[str, object]]]", "list[dict[str, object]], str]")},
    {"body": _BODY.replace("Metadata", "Other")},
    {"body": _BODY.replace("str, list[object], Metadata", "str, Metadata, list[object]")},
    {"prefix": "MetaAlias = Metadata\n", "body": _BODY.replace("Metadata", "MetaAlias")},
    {"body": _BODY.replace("list[dict", "tuple[dict")},
    {"body": _BODY.replace("tuple[", "list[", 1)},
    {"body": _BODY.replace("dict[str, object]", "dict[str, list[object]]")},
    {"body": _BODY.replace("tuple[str, list[object]] |", "tuple[str, list[object], object] |")},
    {"body": _BODY.replace(", list[dict", " | tuple[str, list[object]], list[dict")},
    {"body": _BODY.replace("str, list[object]] |", "str, list[object], ...] |")},
    {"body": _BODY.replace("list[object]", "list[object | None]", 1)},
    {"prefix": "class object: pass\n"},
    {"prefix": "class str: pass\n"},
    {"prefix": "class list: pass\n"},
    {"prefix": "class dict: pass\n"},
    {"metadata_module": "renamed"},
    {"alias_suffix": "Packet.__args__ = ()\n"},
    {"alias_suffix": "unknown(Packet)\n"},
    {"alias_suffix": "if condition: Packet = object\n"},
    {"prefix": "from missing import *\n"},
    {"prefix": "object = Missing\n"},
    {"prefix": "Packet = object\n"},
    {"prefix": f"Inner = {_BODY}\n", "body": "Inner"},
    {"prefix": "from typing import Annotated\n", "body": f"Annotated[{_BODY}, 'tag']"},
    {
        "prefix": "from typing import Annotated\n",
        "annotation": "Annotated[Packet, 'tag']",
        "change": {"annotation": "Annotated[Packet, 'tag']"},
    },
    {"annotation": "list[Packet]", "change": {"annotation": "list[Packet]"}},
    {"body": "factory()"},
    {"alias_module": True},
    {"prefix": "from .types import Other as Metadata\n"},
    {"metadata": "class Metadata:\n    label: str\nclass Metadata:\n    label: str\n"},
    {"metadata": "class Hidden:\n    label: str\nMetadata = Hidden\n"},
    {
        "metadata": (
            "from typing import Generic, TypeVar\nT = TypeVar('T')\n"
            "class Metadata(Generic[T]):\n    label: str\n"
        )
    },
]


@pytest.mark.parametrize("selected", [(0,), (1,), (2,), (3,), (0, 1, 2, 3)])
@pytest.mark.parametrize("mutation", _MUTATIONS)
def test_unchanged_binding_fails_closed_after_source_mutation(
    tmp_path: Path, selected: tuple[int, ...], mutation
) -> None:
    _fixture(tmp_path, facade=True, selected=selected, **mutation)
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert _facts(result.observation) == []
    assert _targets(result.observation) or _unknowns(result.observation)


@pytest.mark.parametrize(
    "change",
    [
        {"qualified_name": "sample.app.impl.Session.unrelated"},
        {"position": "other"},
        {"container_depth": 1},
        {"container_depth": 2},
        {"container_depth": 4},
        {"alias_body": {**_BINDING, "origin": "sample.app.moved:Packet"}},
        {
            "alias_body": {
                **_BINDING,
                "shape": _SHAPE.replace("sample.app.types.Metadata", "sample.app.types.Other"),
            }
        },
        {"alias_body": {**_BINDING, "shape": _SHAPE.replace(" | ", "|")}},
    ],
)
def test_wrong_coordinates_and_stale_binding_grant_nothing(tmp_path: Path, change) -> None:
    _fixture(tmp_path, selected=(1, 3), change=change)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facts(result.observation) == [] and len(_targets(result.observation)) == 4


def test_source_verdict_retains_three_object_occurrences_and_one_map_before_dedup(
    tmp_path: Path,
) -> None:
    _fixture(tmp_path, selected=())
    result = _observe(tmp_path)
    assert result.observation is not None
    raw = observation_payload(result.observation)
    symbols = raw["symbols"]
    imports = raw["imports"]
    bindings, classes = boundary_type_indexes(symbols, imports)
    verdict = _boundary_type_verdict(
        "Packet",
        "sample.app.impl",
        parse_contract(json.loads((tmp_path / "contract.json").read_text())),
        {},
        bindings,
        classes,
        type_shapes=collect_type_shapes(["Packet", _BODY, "str"]),
    )
    assert verdict.violations == (
        ("holding object instead of a typed model", (), "object", 3),
        ("holding object instead of a typed model", (), "object", 3),
        ("holding object instead of a typed model", (), "object", 3),
        ("instead of a typed model", (), "dict[str, object]", 2),
    )
    assert len(verdict.mapping_occurrences) == 1
    assert verdict.mapping_occurrences[0].depth == 2


@pytest.mark.parametrize("opaque", ["object", "Missing"])
def test_metadata_field_findings_and_unknowns_survive_payload_grants(
    tmp_path: Path, opaque: str
) -> None:
    metadata = f"class Metadata:\n    label: str\n    opaque: {opaque}\n"
    _fixture(tmp_path, selected=(), metadata=metadata)
    before = _observe(tmp_path)
    assert before.observation is not None
    before_fields = tuple(item for item in _targets(before.observation) if item.data.get("path"))
    before_unknowns = _unknowns(before.observation)
    _fixture(tmp_path, metadata=metadata)
    after = _observe(tmp_path)
    assert after.observation is not None
    assert len(_facts(after.observation)) == 4
    assert tuple(_targets(after.observation)) == before_fields
    assert _unknowns(after.observation) == before_unknowns
    assert before_fields if opaque == "object" else before_unknowns


def _cli(root: Path, command: str, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "from archkeel.cli import main; raise SystemExit(main())",
            command,
            "--root",
            str(root),
            *(["--output", str(output)] if command == "report" else []),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize("selected", _SELECTIONS)
def test_ordinary_cli_report_and_validate_preserve_unrelated_fail_and_unknown(
    tmp_path: Path, facade: bool, selected: tuple[int, ...]
) -> None:
    _fixture(tmp_path, facade=facade, selected=selected)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    report = _cli(tmp_path, "report", output)
    assert report.returncode == 0, (json.loads(report.stdout)["diagnostics"], report.stderr)
    summary = json.loads(report.stdout)
    assert summary["declared_rules"] == "FAIL" and summary["diagnostics"] == []
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert len(_facts(observation)) == len(selected)
    assert len(_targets(observation)) == 4 - len(selected)
    assert _unknowns(observation)
    validate = _cli(tmp_path, "validate", output)
    assert validate.returncode == 2, (validate.stdout, validate.stderr)
    assert json.loads(validate.stdout)["declared_rules"] == "FAIL"


@pytest.mark.parametrize(
    "mutation",
    [
        {"body": _BODY.replace("dict[str, object]", "dict[int, object]")},
        {"body": _BODY.replace("tuple[str, list[object]] |", "tuple[str, list[object], object] |")},
        {"prefix": f"Inner = {_BODY}\n", "body": "Inner"},
        {
            "prefix": "from typing import Annotated\n",
            "annotation": "Annotated[Packet, 'tag']",
            "change": {"annotation": "Annotated[Packet, 'tag']"},
        },
        {"alias_module": True},
        {"metadata_module": "renamed"},
    ],
)
def test_ordinary_cli_source_mutations_have_no_bound_grant(tmp_path: Path, mutation) -> None:
    _fixture(tmp_path, facade=True, **mutation)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    result = _cli(tmp_path, "report", output)
    assert result.returncode == 0, (json.loads(result.stdout)["diagnostics"], result.stderr)
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert _facts(observation) == []
    assert _targets(observation) or _unknowns(observation)


@pytest.mark.parametrize("depth", [None, 1])
def test_present_binding_never_falls_through_to_legacy_direct_map(
    tmp_path: Path, depth: int | None
) -> None:
    annotation = "dict[str, object]"
    change = (
        {"annotation": annotation, "container_depth": depth}
        if depth is not None
        else {"annotation": annotation}
    )
    _fixture(tmp_path, selected=(0,), annotation=annotation, change=change)
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facts(result.observation) == []
    assert _targets(result.observation)


@pytest.mark.parametrize("facade", [False, True])
def test_direct_imported_alias_uses_its_actual_source_origin(tmp_path: Path, facade: bool) -> None:
    _fixture(
        tmp_path,
        facade=facade,
        alias_module=True,
        change={"alias_body": {**_BINDING, "origin": "sample.app.moved:Packet"}},
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_facts(result.observation)) == 4 and _targets(result.observation) == []


def test_union_arm_order_is_preserved_in_the_binding(tmp_path: Path) -> None:
    reversed_body = (
        "tuple[tuple[str, list[object], Metadata] | tuple[str, list[object]], "
        "list[dict[str, object]]]"
    )
    _fixture(tmp_path, body=reversed_body)
    stale = _observe(tmp_path)
    assert stale.observation is not None and _facts(stale.observation) == []
    _fixture(
        tmp_path,
        body=reversed_body,
        change={
            "alias_body": {
                **_BINDING,
                "shape": reversed_body.replace("Metadata", "sample.app.types.Metadata"),
            }
        },
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_facts(result.observation)) == 4 and _targets(result.observation) == []


def test_dto_fields_do_not_inherit_direct_alias_permission(tmp_path: Path) -> None:
    _fixture(
        tmp_path,
        annotation="Envelope",
        prefix="",
        alias_suffix="class Envelope:\n    payload: Packet\n",
        change={"annotation": "Envelope"},
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facts(result.observation) == [] and _targets(result.observation)


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize("selected", _SELECTIONS)
def test_ordinary_validate_cli_proves_exact_permission_with_fail_and_unknown(
    tmp_path: Path, facade: bool, selected: tuple[int, ...]
) -> None:
    _fixture(tmp_path, facade=facade, selected=selected)
    _commit_report_fixture(tmp_path)
    result = _cli(tmp_path, "validate", tmp_path / "unused.json")
    assert result.returncode == 2, result.stderr
    summary = json.loads(result.stdout)
    assert summary["declared_rules"] == "FAIL" and summary["observation_complete"] == "PASS"
    assert summary["coverage"]["status"] == "PASS"
    assert summary["rule_assessments"][0]["count"] == 5 - len(selected)
    assert summary["rule_assessments"][0]["undecided"] == 1
    assert all(item["code"] == "rule.violated" for item in summary["diagnostics"])


@pytest.mark.parametrize("suffix", ["Packet.__args__ = ()\n", "unknown(Packet)\n"])
def test_imported_alias_escape_cannot_reuse_the_source_proof(tmp_path: Path, suffix: str) -> None:
    _fixture(
        tmp_path,
        alias_module=True,
        alias_suffix=suffix,
        change={"alias_body": {**_BINDING, "origin": "sample.app.moved:Packet"}},
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facts(result.observation) == []
    assert _targets(result.observation) or _unknowns(result.observation)


@pytest.mark.parametrize("name", ["Packet", "Metadata"])
def test_reexported_alias_or_metadata_cannot_lend_direct_body_proof(
    tmp_path: Path, name: str
) -> None:
    if name == "Packet":
        _fixture(
            tmp_path,
            alias_module=True,
            change={"alias_body": {**_BINDING, "origin": "sample.app.moved:Packet"}},
        )
        old = "from .moved import Packet"
        source = "from .moved import Packet\n"
    else:
        _fixture(tmp_path)
        old = "from .types import Metadata"
        source = "from .types import Metadata\n"
    (tmp_path / "sample/app/proxy.py").write_text(source)
    path = tmp_path / "sample/app/impl.py"
    path.write_text(path.read_text().replace(old, f"from .proxy import {name}"))
    result = _observe(tmp_path)
    assert result.observation is not None
    assert _facts(result.observation) == []
    assert _targets(result.observation) or _unknowns(result.observation)


def test_applied_proof_links_source_imports_declarations_and_signature(tmp_path: Path) -> None:
    _fixture(
        tmp_path,
        alias_module=True,
        change={"alias_body": {**_BINDING, "origin": "sample.app.moved:Packet"}},
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    imports = {item.id: item for item in result.observation.records("imports") or ()}
    evidence = {item.id: item for item in result.observation.evidence}
    for fact in _facts(result.observation):
        assert {imports[item].data.get("binding") for item in fact.fact_ids if item in imports} == {
            "Packet",
            "Metadata",
        }
        assert {evidence[item].file for item in fact.evidence_ids} == {
            "sample/app/impl.py",
            "sample/app/moved.py",
            "sample/app/types.py",
        }
        assert fact.data.get("source") == "sample.app"
        assert fact.data.get("module") == "sample.app.impl"


@pytest.mark.parametrize("selected", [(0,), (1,), (2,), (3,), (0, 1, 2, 3)])
@pytest.mark.parametrize("mutation", _MUTATIONS)
def test_ordinary_validate_cli_source_mutation_matches_no_permission_control(
    tmp_path: Path, selected: tuple[int, ...], mutation
) -> None:
    _fixture(tmp_path, facade=True, selected=selected, **mutation)
    _commit_report_fixture(tmp_path)
    bound = _cli(tmp_path, "validate", tmp_path / "unused.json")
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["rules"][0]["allowed_positions"] = []
    contract_path.write_text(json.dumps(contract))
    control = _cli(tmp_path, "validate", tmp_path / "unused.json")
    star_import = mutation == {"prefix": "from missing import *\n"}
    assert bound.returncode == control.returncode == (0 if star_import else 2)
    actual, expected = json.loads(bound.stdout), json.loads(control.stdout)
    for key in (
        "declared_rules",
        "observation_complete",
        "rule_assessments",
        "diagnostics",
        "measurements",
    ):
        assert actual[key] == expected[key], (key, actual[key], expected[key])
    assert actual["observation_complete"] == "PASS"
    assert actual["declared_rules"] == ("UNKNOWN" if star_import else "FAIL")
    if star_import:
        assert actual["rule_assessments"][0]["count"] == 0
        assert actual["rule_assessments"][0]["undecided"] == 8
        result = _observe(tmp_path)
        assert result.observation is not None and _facts(result.observation) == []
        assert {
            (item.data.get("qualified_name"), item.data.get("position"), item.data.get("reason"))
            for item in _unknowns(result.observation)
        } == {
            (f"sample.app.Session.{method}", position, "ambiguous_facade")
            for method, position in (
                ("prepare", "return"),
                ("dispatch", "packet"),
                ("dispatch", "return"),
                ("unrelated", "counts"),
                ("unrelated", "return"),
                ("undecided", "value"),
                ("undecided", "return"),
            )
        }


_GROUP_BODY = "dict[str, float] | dict[tuple[int, int], float] | dict[SexKey, float]"
_KEY_BINDING = {"origin": "sample.app.types:SexKey", "shape": "str | None"}
_GROUP_BINDING = {
    "origin": "sample.app.impl:GroupMask",
    "shape": _GROUP_BODY.replace("SexKey", "sample.app.types.SexKey"),
}


def _typed_union_fixture(
    root: Path,
    *,
    facade: bool = False,
    annotation: str = _GROUP_BODY,
    body: str = _GROUP_BODY,
    key_body: str = "str | None",
    key_prefix: str = "",
    key_suffix: str = "",
    prefix: str = "",
    suffix: str = "",
    change: dict[str, object] | None = None,
    allowed: bool = True,
    schema_version: str = "3.1.0",
    local_key: bool = False,
) -> None:
    owner = f"sample.app{'' if facade else '.impl'}"
    selector: dict[str, object] = {
        "qualified_name": f"{owner}.Session.prepare",
        "position": "return",
        "annotation": annotation,
    }
    if "SexKey" in body if annotation == "GroupMask" else "SexKey" in annotation:
        selector["key_alias_body"] = {
            **_KEY_BINDING,
            "origin": f"sample.app.{'impl' if local_key else 'types'}:SexKey",
        }
    if annotation == "GroupMask":
        selector["alias_body"] = {
            **_GROUP_BINDING,
            "shape": body.replace(
                "SexKey", f"sample.app.{'impl' if local_key else 'types'}.SexKey"
            ),
        }
    selector.update(change or {})
    selector = {key: value for key, value in selector.items() if value is not None}
    key_source = key_prefix + f"SexKey = {key_body}\n" + key_suffix
    _app(
        root,
        source=(
            (key_source if local_key else "from .types import SexKey\n")
            + prefix
            + f"GroupMask = {body}\n"
            + suffix
            + "class Session:\n"
            + f"    def prepare(self) -> {annotation}: pass\n"
            + "    def unrelated(self, counts: dict[str, int]) -> None: pass\n"
            + "    def undecided(self, value: Missing) -> None: pass\n"
        ),
        declared=(f"{owner}:Session",),
        allowances=(selector,) if allowed else (),
    )
    (root / "sample/app/types.py").write_text(key_source)
    if facade:
        (root / "sample/app/__init__.py").write_text(
            "from .impl import Session\n__all__ = ['Session']\n"
        )
    contract_path = root / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = schema_version
    contract_path.write_text(json.dumps(contract))
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        '[scan]\nroots = ["."]\nnamespace = "sample"\ncontract = "contract.json"\n'
    )


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_partial_inline_typed_union_proves_all_three_maps(tmp_path: Path, facade: bool) -> None:
    _typed_union_fixture(tmp_path, facade=facade, allowed=False)
    before = _observe(tmp_path)
    assert before.observation is not None and before.diagnostics == ()
    assert len(_targets(before.observation)) == 3
    _typed_union_fixture(tmp_path, facade=facade)
    after = _observe(tmp_path)
    assert after.observation is not None and after.diagnostics == ()
    assert _targets(after.observation) == []
    facts = _facts(after.observation)
    assert len(facts) == 3
    assert {item.data.get("nested_annotation") for item in facts} == set(_GROUP_BODY.split(" | "))
    assert after.observation.records("unknowns") == before.observation.records("unknowns")
    assert trace_valid_violations(after.observation) == tuple(
        item
        for item in trace_valid_violations(before.observation)
        if item not in _targets(before.observation)
    )
    imports = {item.id: item for item in after.observation.records("imports") or ()}
    symbols = {item.id: item for item in after.observation.records("symbols") or ()}
    evidence = {item.id: item for item in after.observation.evidence}
    for fact in facts:
        pair = fact.data.get("key_alias_body")
        assert isinstance(pair, RecordData) and dict(pair.entries) == _KEY_BINDING
        assert fact.data.get("observed_container_depth") == 0
        assert fact.data.get("container_depth") is None
        assert fact.data.get("accepted_opacity") is None
        assert fact.data.get("alias_body") is None
        assert fact.provenance == ("docs/architecture/sample.md",)
        assert {imports[item].data.get("binding") for item in fact.fact_ids if item in imports} == {
            "SexKey"
        }
        assert any(symbols[item].kind == "type_alias" for item in fact.fact_ids if item in symbols)
        assert {evidence[item].file for item in fact.evidence_ids} == {
            "sample/app/impl.py",
            "sample/app/types.py",
        }


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_partial_inline_provider_swap_matches_no_permission(tmp_path: Path, facade: bool) -> None:
    mutation = {"key_prefix": "class str: pass\n"}
    _typed_union_fixture(tmp_path, facade=facade, **mutation)
    after = _observe(tmp_path)
    assert after.observation is not None and _facts(after.observation) == []
    _typed_union_fixture(tmp_path, facade=facade, allowed=False, **mutation)
    before = _observe(tmp_path)
    assert before.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


_TYPED_MUTATIONS = [
    {"key_body": "None | str"},
    {"key_body": "int | None"},
    {"key_body": "str | int"},
    {"key_body": "str | None | None"},
    {"key_prefix": "Inner = str | None\n", "key_body": "Inner"},
    {"key_prefix": "class str: pass\n"},
    {"key_prefix": "from missing import *\n"},
    {"key_prefix": "SexKey = int\n"},
    {"key_suffix": "SexKey.__args__ = ()\n"},
    {"key_suffix": "unknown(SexKey)\n"},
    {"key_suffix": "if condition: SexKey = object\n"},
    {"prefix": "class dict: pass\n"},
    {"prefix": "class tuple: pass\n"},
    {"prefix": "class int: pass\n"},
    {"prefix": "class float: pass\n"},
    {"prefix": "class str: pass\n"},
    {"prefix": "from missing import *\n"},
    {"prefix": "SexKey = str | None\n"},
    {"suffix": "unknown(SexKey)\n"},
    {"suffix": "SexKey.__args__ = ()\n"},
    {"suffix": "if condition: SexKey = object\n"},
    {"annotation": _GROUP_BODY.replace("tuple[int, int]", "tuple[int]")},
    {"annotation": _GROUP_BODY.replace("tuple[int, int]", "tuple[int, int, int]")},
    {"annotation": _GROUP_BODY.replace("tuple[int, int]", "tuple[int, str]")},
    {"annotation": _GROUP_BODY.replace("tuple[int, int]", "int")},
    {"annotation": _GROUP_BODY.replace("float", "object")},
    {"annotation": _GROUP_BODY.replace("float", "Missing")},
    {"prefix": "Value = float\n", "annotation": _GROUP_BODY.replace("float", "Value")},
    {"annotation": _GROUP_BODY + " | dict[str, float]"},
    {"annotation": _GROUP_BODY + " | dict[SexKey, int]"},
    {"annotation": _GROUP_BODY + " | None"},
    {"annotation": _GROUP_BODY + " | Missing"},
    {"annotation": f"list[{_GROUP_BODY}]"},
    {"annotation": f"tuple[{_GROUP_BODY}, int]"},
    {"prefix": "from typing import Annotated\n", "annotation": f"Annotated[{_GROUP_BODY}, 'tag']"},
    {
        "prefix": "from typing import Union\nUnion = object\n",
        "annotation": "Union[dict[str, float], dict[SexKey, int]]",
    },
    {"change": {"key_alias_body": None}},
    {"change": {"key_alias_body": {**_KEY_BINDING, "origin": "sample.app.impl:SexKey"}}},
    {"change": {"key_alias_body": {**_KEY_BINDING, "shape": "None | str"}}},
    {"change": {"alias_body": _GROUP_BINDING}},
    {"change": {"qualified_name": "sample.app.impl.Session.unrelated"}},
    {"change": {"position": "other"}},
    {"annotation": "dict[str, float] | dict[str, int]", "change": {"key_alias_body": _KEY_BINDING}},
    {"annotation": "dict[str, object]", "change": {"key_alias_body": _KEY_BINDING}},
    {
        "annotation": "dict[str, str] | dict[str, object]",
        "change": {"key_alias_body": _KEY_BINDING},
    },
    {"annotation": "GroupMask", "change": {"alias_body": None}},
    {"annotation": "GroupMask", "change": {"key_alias_body": None}},
    {
        "annotation": "GroupMask",
        "change": {
            "alias_body": {
                **_GROUP_BINDING,
                "shape": " | ".join(reversed(_GROUP_BINDING["shape"].split(" | "))),
            }
        },
    },
    {
        "annotation": "GroupMask",
        "change": {"alias_body": {**_GROUP_BINDING, "origin": "sample.app.types:GroupMask"}},
    },
    {"annotation": "GroupMask", "suffix": "unknown(GroupMask)\n"},
    {"annotation": "GroupMask", "prefix": "GroupMask = object\n"},
    {"annotation": "GroupMask", "prefix": f"Inner = {_GROUP_BODY}\n", "body": "Inner"},
]


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize("mutation", _TYPED_MUTATIONS)
def test_typed_union_rejection_matches_same_source_without_permission(
    tmp_path: Path, facade: bool, mutation
) -> None:
    _typed_union_fixture(tmp_path, facade=facade, **mutation)
    after = _observe(tmp_path)
    assert after.observation is not None and after.diagnostics == ()
    assert _facts(after.observation) == []
    _typed_union_fixture(tmp_path, facade=facade, allowed=False, **mutation)
    before = _observe(tmp_path)
    assert before.observation is not None and before.diagnostics == ()
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize(
    "change", [{"field_path": "payload"}, {"container_depth": 1}, {"mapping_depth": 1}]
)
def test_key_binding_rejects_prohibited_selectors_at_contract_boundary(
    tmp_path: Path, change
) -> None:
    _typed_union_fixture(tmp_path, change=change)
    result = _observe(tmp_path)
    assert result.observation is None
    assert result.diagnostics and all(item.kind == "parse_error" for item in result.diagnostics)


@pytest.mark.parametrize("change", [{"field_path": "payload"}, {"container_depth": 1}])
def test_expanded_typed_union_cannot_grant_field_or_depth_selectors(tmp_path: Path, change) -> None:
    _typed_union_fixture(tmp_path, annotation="dict[str, float] | dict[str, int]", change=change)
    after = _observe(tmp_path)
    assert after.observation is not None and _facts(after.observation) == []
    _typed_union_fixture(tmp_path, annotation="dict[str, float] | dict[str, int]", allowed=False)
    before = _observe(tmp_path)
    assert before.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)


@pytest.mark.parametrize("facade", [False, True])
@pytest.mark.parametrize(
    "annotation", ["GroupMask", _GROUP_BODY, "dict[str, float] | dict[str, int]"]
)
def test_typed_union_ordinary_report_and_validate_keep_unrelated_fail_and_unknown(
    tmp_path: Path, facade: bool, annotation: str
) -> None:
    _typed_union_fixture(tmp_path, facade=facade, annotation=annotation)
    _commit_report_fixture(tmp_path)
    output = tmp_path / "architecture.json"
    report = _cli(tmp_path, "report", output)
    assert report.returncode == 0, (report.stdout, report.stderr)
    observation = parse_observation(decode_canonical_model(json.loads(output.read_text())))
    assert _targets(observation) == []
    assert len(_facts(observation)) == (
        2 if annotation == "dict[str, float] | dict[str, int]" else 3
    )
    assert _unknowns(observation)
    validate = _cli(tmp_path, "validate", output)
    assert validate.returncode == 2, (validate.stdout, validate.stderr)
    summary = json.loads(validate.stdout)
    assert summary["declared_rules"] == "FAIL" and summary["observation_complete"] == "PASS"
    assert summary["coverage"]["status"] == "PASS"
    assert summary["rule_assessments"][0]["count"] == 1
    assert summary["rule_assessments"][0]["undecided"] == 1


@pytest.mark.parametrize("facade", [False, True])
def test_key_alias_reexport_cannot_supply_direct_proof(tmp_path: Path, facade: bool) -> None:
    _typed_union_fixture(tmp_path, facade=facade)
    (tmp_path / "sample/app/proxy.py").write_text("from .types import SexKey\n")
    source = tmp_path / "sample/app/impl.py"
    source.write_text(
        source.read_text().replace("from .types import SexKey", "from .proxy import SexKey")
    )
    after = _observe(tmp_path)
    assert after.observation is not None and _facts(after.observation) == []
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["rules"][0]["allowed_positions"] = []
    contract_path.write_text(json.dumps(contract))
    before = _observe(tmp_path)
    assert before.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


def test_expanded_and_aliased_equal_map_arms_are_not_distinct(tmp_path: Path) -> None:
    annotation = "Union[dict[SexKey, float], dict[str | None, float]]"
    _typed_union_fixture(
        tmp_path, annotation=annotation, body="str", prefix="from typing import Union\n"
    )
    after = _observe(tmp_path)
    assert after.observation is not None and _facts(after.observation) == []
    _typed_union_fixture(
        tmp_path,
        annotation=annotation,
        body="str",
        prefix="from typing import Union\n",
        allowed=False,
    )
    before = _observe(tmp_path)
    assert before.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_same_body_key_provider_swap_requires_the_actual_origin(
    tmp_path: Path, facade: bool
) -> None:
    def swap() -> None:
        (tmp_path / "sample/app/alternate.py").write_text("SexKey = str | None\n")
        path = tmp_path / "sample/app/impl.py"
        path.write_text(
            path.read_text().replace("from .types import SexKey", "from .alternate import SexKey")
        )

    _typed_union_fixture(tmp_path, facade=facade)
    swap()
    rejected = _observe(tmp_path)
    assert rejected.observation is not None and _facts(rejected.observation) == []
    _typed_union_fixture(tmp_path, facade=facade, allowed=False)
    swap()
    ordinary = _observe(tmp_path)
    assert ordinary.observation is not None
    assert trace_valid_violations(rejected.observation) == trace_valid_violations(
        ordinary.observation
    )
    assert rejected.observation.records("unknowns") == ordinary.observation.records("unknowns")
    key_import = next(
        item
        for item in rejected.observation.records("imports") or ()
        if item.data.get("binding") == "SexKey"
    )
    assert key_import.data.get("origin_definition") == "sample.app.alternate.SexKey"
    assert key_import.data.get("source_member_binding_static") is True


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
def test_same_builtin_map_provider_alias_is_a_duplicate(tmp_path: Path, facade: bool) -> None:
    annotation = "dict[str, float] | Dict[str, float]"
    change = {
        "annotation": annotation,
        "body": annotation,
        "prefix": "from builtins import dict as Dict\n",
    }
    _typed_union_fixture(tmp_path, facade=facade, **change)
    selected = _observe(tmp_path)
    assert selected.observation is not None and _facts(selected.observation) == []
    _typed_union_fixture(tmp_path, facade=facade, allowed=False, **change)
    ordinary = _observe(tmp_path)
    assert ordinary.observation is not None
    assert trace_valid_violations(selected.observation) == trace_valid_violations(
        ordinary.observation
    )
    assert selected.observation.records("unknowns") == ordinary.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("version", ["3.0.0", "3.1.0"])
@pytest.mark.parametrize(
    "annotation,prefix,depth",
    [
        ("object | None", "", None),
        ("Iterable[object] | None", "from collections.abc import Iterable\n", 1),
    ],
)
def test_existing_nullable_native_allowance_survives_contract_upgrade(
    tmp_path: Path, facade: bool, version: str, annotation: str, prefix: str, depth: int | None
) -> None:
    change = {
        "facade": facade,
        "schema_version": version,
        "annotation": annotation,
        "prefix": prefix,
        "change": {"container_depth": depth},
    }
    _typed_union_fixture(tmp_path, allowed=False, **change)
    before = _observe(tmp_path)
    assert before.observation is not None
    owner = f"sample.app{'' if facade else '.impl'}.Session.prepare"
    before_targets = [
        v
        for v in trace_valid_violations(before.observation)
        if v.data.get("qualified_name") == owner
    ]
    assert len(before_targets) == 1
    assert before_targets[0].data.get("reason") == "holding object instead of a typed model"
    _typed_union_fixture(tmp_path, **change)
    after = _observe(tmp_path)
    assert after.observation is not None
    facts = _facts(after.observation)
    assert len(facts) == 1 and facts[0].data.get("accepted_opacity") is True
    assert facts[0].data.get("key_alias_body") is None
    assert facts[0].data.get("alias_body") is None
    assert trace_valid_violations(after.observation) == tuple(
        v for v in trace_valid_violations(before.observation) if v not in before_targets
    )
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("pair", ["alias_body", "key_alias_body"])
@pytest.mark.parametrize("annotation", ["object | None", "dict[str, object] | None"])
def test_native_nullable_union_cannot_ignore_a_present_wrong_pair(
    tmp_path: Path, facade: bool, pair: str, annotation: str
) -> None:
    change = {"annotation": annotation, "facade": facade, "change": {pair: _KEY_BINDING}}
    _typed_union_fixture(tmp_path, **change)
    after = _observe(tmp_path)
    assert after.observation is not None and _facts(after.observation) == []
    _typed_union_fixture(tmp_path, allowed=False, **change)
    before = _observe(tmp_path)
    assert before.observation is not None
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize("version", ["3.0.0", "3.1.0"])
@pytest.mark.parametrize("depth", [None, 1], ids=["outer", "native-value"])
def test_existing_nullable_native_map_allowance_survives_contract_upgrade(
    tmp_path: Path, facade: bool, version: str, depth: int | None
) -> None:
    change = {
        "annotation": "dict[str, object] | None",
        "facade": facade,
        "schema_version": version,
        "change": {"container_depth": depth},
    }
    _typed_union_fixture(tmp_path, allowed=False, **change)
    before = _observe(tmp_path)
    assert before.observation is not None
    _typed_union_fixture(tmp_path, **change)
    after = _observe(tmp_path)
    assert after.observation is not None
    facts = _facts(after.observation)
    assert len(facts) == 1
    assert facts[0].data.get("accepted_opacity") == (True if depth else None)
    before_findings = trace_valid_violations(before.observation)
    after_findings = trace_valid_violations(after.observation)
    removed = [item for item in before_findings if item not in after_findings]
    assert len(removed) == 1
    expected_reason = (
        "holding object instead of a typed model" if depth else "instead of a typed model"
    )
    assert removed[0].data.get("reason") == expected_reason
    assert after_findings == tuple(item for item in before_findings if item not in removed)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize(
    "mapping",
    [
        "dict[str, int]",
        "dict[str, float]",
        "dict[int, str]",
        "dict[str, str]",
        "dict[str, object]",
        "dict[SexKey, int]",
    ],
)
@pytest.mark.parametrize(
    "nullable,prefix",
    [
        ("{mapping} | None", ""),
        ("None | {mapping}", ""),
        ("Optional[{mapping}]", "from typing import Optional\n"),
        ("Union[{mapping}, None]", "from typing import Union\n"),
    ],
)
def test_ordinary_nullable_map_upgrade_preserves_exact_records(
    tmp_path: Path, facade: bool, mapping: str, nullable: str, prefix: str
) -> None:
    annotation = nullable.format(mapping=mapping)
    _typed_union_fixture(
        tmp_path,
        facade=facade,
        annotation=annotation,
        prefix=prefix,
        schema_version="3.0.0",
        change={"key_alias_body": None},
    )
    before = _observe(tmp_path)
    assert before.observation is not None and before.diagnostics == ()
    assert len(_facts(before.observation)) == 1
    assert all(
        item.data.get("reason") != "instead of a typed model"
        for item in _targets(before.observation)
    )
    inputs = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    contract_path = tmp_path / "contract.json"
    contract = json.loads(contract_path.read_text())
    contract["schema_version"] = "3.1.0"
    contract_path.write_text(json.dumps(contract))
    assert [path for path, content in inputs.items() if path.read_bytes() != content] == [
        contract_path
    ]
    after = _observe(tmp_path)
    assert after.observation is not None and after.diagnostics == ()
    assert _facts(after.observation) == _facts(before.observation)
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize("facade", [False, True], ids=["direct", "facade"])
@pytest.mark.parametrize(
    "mutation",
    [
        {"annotation": "dict[str, int] | dict[str, int] | None"},
        {"annotation": "dict[str, int] | int | None"},
        {"annotation": "dict[str, int] | Missing | None"},
        {"annotation": "dict[str, int] | object | None"},
        {"prefix": "class dict: pass\n"},
        {
            "prefix": "from typing import Optional\nOptional = object\n",
            "annotation": "Optional[dict[str, int]]",
        },
        {
            "prefix": "from typing import Union\nUnion = object\n",
            "annotation": "Union[dict[str, int], None]",
        },
        {
            "annotation": "dict[str, int] | dict[SexKey, int] | None",
            "change": {"key_alias_body": None},
        },
        {"change": {"alias_body": _GROUP_BINDING}},
        {"change": {"key_alias_body": _KEY_BINDING}},
    ],
)
def test_ordinary_nullable_map_cannot_bypass_union_or_binding_proof(
    tmp_path: Path, facade: bool, mutation
) -> None:
    change = {"annotation": "dict[str, int] | None", "facade": facade, **mutation}
    _typed_union_fixture(tmp_path, **change)
    after = _observe(tmp_path)
    assert after.observation is not None and after.diagnostics == ()
    assert _facts(after.observation) == []
    _typed_union_fixture(tmp_path, allowed=False, **change)
    before = _observe(tmp_path)
    assert before.observation is not None and before.diagnostics == ()
    assert trace_valid_violations(after.observation) == trace_valid_violations(before.observation)
    assert after.observation.records("unknowns") == before.observation.records("unknowns")


@pytest.mark.parametrize("alias_module", [False, True])
@pytest.mark.parametrize(
    "suffix", ["Packet.__args__ = ()\n", "unknown(Packet)\n", "unknown(globals())\n"]
)
def test_uncertain_alias_body_is_unknown_not_a_concrete_failure(tmp_path, alias_module, suffix):
    _fixture(tmp_path, alias_module=alias_module, alias_suffix=suffix, selected=())
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert _targets(result.observation) == []
    assert _facts(result.observation) == []
    positions = {item.data.get("qualified_name") for item in _unknowns(result.observation)}
    assert {"sample.app.impl.Session.prepare", "sample.app.impl.Session.dispatch"} <= positions
    assert any(
        item.data.get("qualified_name") == "sample.app.impl.Session.unrelated"
        for item in trace_valid_violations(result.observation)
    )


def test_metadata_only_escape_keeps_proven_literal_failures(tmp_path):
    _fixture(tmp_path, selected=(), metadata="class Metadata:\n    label: str\nunknown(Metadata)\n")
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_targets(result.observation)) == 4
    assert _facts(result.observation) == []


def test_literal_outer_and_sibling_survive_uncertain_alias(tmp_path):
    _fixture(
        tmp_path,
        selected=(),
        alias_suffix="unknown(Packet)\n",
        annotation="dict[str, Packet] | list[object]",
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    targets = _targets(result.observation)
    assert len(targets) == 4
    assert {item.data.get("nested_annotation") for item in targets} == {
        "dict[str, Packet]",
        "object",
    }
    assert len(_unknowns(result.observation)) >= 3


def test_uncertain_inner_alias_does_not_erase_exact_literal_outer_map_permission(tmp_path):
    annotation = "dict[str, Packet]"
    _fixture(
        tmp_path,
        alias_suffix="unknown(Packet)\n",
        annotation=annotation,
        change={"annotation": annotation},
        bound=False,
        selected=(0,),
    )
    result = _observe(tmp_path)
    assert result.observation is not None
    assert len(_facts(result.observation)) == 1
    assert len(_targets(result.observation)) == 1
    assert len(_unknowns(result.observation)) >= 3


@pytest.mark.parametrize(
    "annotation",
    [" | ".join(parts) for parts in permutations(("Missing", "dict[str, int]", "Packet"))],
)
@pytest.mark.parametrize("dto", [False, True])
def test_uncertain_alias_ordinary_permission_is_independent_of_union_order(
    tmp_path, annotation, dto
):
    suffix = "unknown(Packet)\n"
    if dto:
        suffix += f"class Envelope:\n    payload: {annotation}\n"
    _fixture(
        tmp_path,
        annotation="Envelope" if dto else annotation,
        alias_suffix=suffix,
        change={"annotation": annotation, **({"field_path": "payload"} if dto else {})},
        bound=False,
        selected=(0,),
    )
    if dto:
        path = tmp_path / "contract.json"
        contract = json.loads(path.read_text())
        contract["components"][0]["public"].append("sample.app.impl:Envelope")
        path.write_text(json.dumps(contract))
    result = _observe(tmp_path)
    assert result.observation is not None and result.diagnostics == ()
    assert _facts(result.observation) == []
    assert len(_targets(result.observation)) == 2
    assert len(_unknowns(result.observation)) >= 3
