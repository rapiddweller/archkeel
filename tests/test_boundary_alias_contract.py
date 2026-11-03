# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exact alias bindings are opt-in contract 3.0 data, never a legacy rewrite."""

import hashlib
import json
from dataclasses import FrozenInstanceError, asdict, replace
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from test_codec import raw_observation
from test_contract_model import _maximal_contract
from test_widening import _boundary_types

from archkeel.check.declarations import load_contract, project_rule_declaration
from archkeel.ir.codec import (
    CONTRACT_SCHEMA_VERSION,
    contract_bytes,
    contract_digest,
    decode_canonical_model,
    encode_canonical_model,
    observation_payload,
    parse_contract,
    parse_observation,
)
from archkeel.ir.codec_contract import _rule_payload
from archkeel.ir.model import BoundaryTypeAllowance, module_references
from archkeel.ir.widening import Amendment, contract_widenings, verify_amendment

ROOT = Path(__file__).parents[1]
BODY = {
    "origin": "sample.core.api:Page",
    "shape": (
        "tuple[tuple[str, list[object]] | tuple[str, list[object], sample.core.Metadata], "
        "list[dict[str, object]]]"
    ),
}


def _document(version="3.0.0", **selector):
    return {
        "schema_version": version,
        "components": [],
        "rules": [
            {
                "id": "BOUNDARY",
                "kind": "boundary_types",
                "source": "sample.core",
                "rationale": "Bind the reviewed body.",
                "provenance": ["docs/decision.md"],
                "decided_by": "architect",
                "allowed_positions": [
                    {
                        "qualified_name": "sample.core.api.run",
                        "position": "return",
                        "annotation": "Page",
                        **selector,
                    }
                ],
            }
        ],
    }


def _validator(version="3.0.0"):
    schema = json.loads(
        (ROOT / f"schema/architecture-contract-{version[:3]}.schema.json").read_bytes()
    )
    Draft202012Validator.check_schema(schema)
    assert schema["$id"] == f"urn:archkeel:architecture-contract:{version}"
    return Draft202012Validator(schema)


@pytest.mark.parametrize("depth", [None, 3])
def test_alias_binding_typed_roundtrip_and_declaration(depth):
    from archkeel.ir.model import BoundaryAliasBody

    raw = _document(alias_body=BODY, **({"container_depth": depth} if depth else {}))
    contract = parse_contract(raw)
    selector = contract.rules[0].allowed_positions[0]
    assert selector.alias_body == BoundaryAliasBody(**BODY)
    with pytest.raises(FrozenInstanceError):
        selector.alias_body.origin = "changed"
    encoded = json.loads(contract_bytes(contract))
    assert _validator().is_valid(encoded)
    assert parse_contract(encoded) == contract
    assert _rule_payload(contract.rules[0])["allowed_positions"][0]["alias_body"] == BODY
    declaration = project_rule_declaration(contract.rules[0])
    assert declaration["data"]["allowed_positions"][0]["alias_body"] == BODY
    raw_observed = raw_observation()
    raw_observed["declarations"] = [declaration]
    parsed = parse_observation(decode_canonical_model(encode_canonical_model(raw_observed)))
    assert (
        observation_payload(parsed)["declarations"][0]["data"]["allowed_positions"][0]["alias_body"]
        == BODY
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "body",
        {},
        {"origin": "x"},
        {"shape": "x"},
        {**BODY, "extra": True},
        {**BODY, "origin": ""},
        {**BODY, "origin": "  "},
        {**BODY, "shape": ""},
        {**BODY, "shape": "\n"},
        {**BODY, "origin": 1},
        {**BODY, "shape": False},
        {**BODY, "origin": None},
        {**BODY, "shape": []},
    ],
)
def test_alias_binding_rejects_malformed_pairs(body):
    raw = _document(alias_body=body)
    assert not _validator().is_valid(raw)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize("selector", [{"field_path": "payload"}, {"mapping_depth": 2}])
def test_alias_binding_rejects_incompatible_coordinates(selector):
    raw = _document(alias_body=BODY, **selector)
    assert not _validator().is_valid(raw)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0", "2.3.0"])
def test_alias_binding_rejected_by_legacy_versions_and_loader(version, tmp_path):
    raw = _document(version, alias_body=BODY)
    legacy = json.loads((ROOT / "schema/architecture-contract.schema.json").read_bytes())
    assert not Draft202012Validator(legacy).is_valid(raw)
    assert not _validator().is_valid(raw)
    with pytest.raises(ValueError, match="alias_body.*3.0.0"):
        parse_contract(raw)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="alias_body.*3.0.0"):
        load_contract(path)
    bound = parse_contract(_document(alias_body=BODY))
    with pytest.raises(ValueError, match="alias_body.*3.0.0"):
        contract_bytes(replace(bound, schema_version=version))


def test_alias_binding_duplicate_identity_includes_both_strings():
    raw = _document(alias_body=BODY)
    positions = raw["rules"][0]["allowed_positions"]
    positions += [
        {**positions[0], "alias_body": {**BODY, "origin": "other:Page"}},
        {**positions[0], "alias_body": {**BODY, "shape": "changed"}},
        {key: value for key, value in positions[0].items() if key != "alias_body"},
    ]
    assert _validator().is_valid(raw)
    assert len(parse_contract(raw).rules[0].allowed_positions) == 4
    positions.append({**positions[0], "alias_body": dict(reversed(list(BODY.items())))})
    assert not _validator().is_valid(raw)
    with pytest.raises(ValueError, match="unique entries"):
        parse_contract(raw)


@pytest.mark.parametrize("version", ["3.0.0", "3.1.0"])
def test_contract_3_inherits_layer_and_uml_capabilities_without_default_change(version):
    raw = _maximal_contract()
    raw["schema_version"] = version
    contract = parse_contract(raw)
    assert any(item.layer for item in contract.components)
    assert any(item.kind == "layer_order" for item in contract.rules)
    assert contract.declarations.uml is not None
    assert _validator(version).is_valid(json.loads(contract_bytes(contract)))
    assert parse_contract(json.loads(contract_bytes(contract))) == contract
    assert CONTRACT_SCHEMA_VERSION == "2.1.0"


@pytest.mark.parametrize("key", ["origin", "shape"])
def test_alias_binding_change_is_widening_and_invalidates_amendment(key):
    before = parse_contract(_document())
    after = parse_contract(_document(alias_body=BODY))
    changes = contract_widenings(before, after)
    assert len(changes) == 1 and "allowed_positions gained" in changes[0]
    amendment = Amendment(contract_digest(before), contract_digest(after), "who", "why")
    assert verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(after)
    )
    changed = parse_contract(_document(alias_body={**BODY, key: "changed"}))
    assert len(contract_widenings(after, changed)) == 1
    assert not verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(changed)
    )
    assert (
        contract_widenings(
            after, replace(before, rules=(replace(before.rules[0], allowed_positions=()),))
        )
        == ()
    )


def test_alias_binding_widening_order_is_structural():
    raw = _document(alias_body=BODY)
    first = raw["rules"][0]["allowed_positions"][0]
    positions = [
        {**first, "alias_body": {"origin": origin, "shape": shape}}
        for origin, shape in [("b", "a"), ("a", "b"), ("a", "a")]
    ]
    positions.append({key: value for key, value in first.items() if key != "alias_body"})
    raw["rules"][0]["allowed_positions"] = positions
    before = replace(parse_contract(_document()), rules=(_boundary_types(),))
    after = replace(
        before,
        rules=(
            replace(
                _boundary_types(), allowed_positions=parse_contract(raw).rules[0].allowed_positions
            ),
        ),
    )
    changes = contract_widenings(before, after)
    raw["rules"][0]["allowed_positions"].reverse()
    reversed_after = replace(
        after,
        rules=(
            replace(
                after.rules[0], allowed_positions=parse_contract(raw).rules[0].allowed_positions
            ),
        ),
    )
    assert contract_widenings(before, reversed_after) == changes
    assert "alias_body" not in changes[0]
    assert "origin='a', shape='a'" in changes[1]
    assert "origin='a', shape='b'" in changes[2]
    assert "origin='b', shape='a'" in changes[3]


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def test_absent_binding_preserves_prechange_contracts_payloads_repr_ids_and_observation():
    pinned = json.loads((ROOT / "tests/boundary_alias_legacy.json").read_bytes())
    # Fixed inputs only: the focused UML case was pinned against pre-refactor 465f099.
    # Full live-policy fingerprints are retired; test_contract_model.py retains
    # schema, reference and round-trip checks for current repository contracts.
    for path, expected in pinned.items():
        if path.endswith("sha256"):
            continue
        if path.startswith("legacy-"):
            contract = parse_contract(_document(path.removeprefix("legacy-"), container_depth=3))
        else:
            contract = parse_contract(json.loads((ROOT / path).read_bytes()))
        assert (
            hashlib.sha256(contract_bytes(contract)).hexdigest() == expected["contract_sha256"]
        ), path
        assert (
            _hash([_rule_payload(rule) for rule in contract.rules])
            == expected["rule_payload_sha256"]
        ), path
        assert [
            repr(item)
            for rule in contract.rules
            if rule.kind == "boundary_types"
            for item in rule.allowed_positions
        ] == expected["allowance_reprs"], path
        assert (
            _hash([project_rule_declaration(rule) for rule in contract.rules])
            == expected["declarations_sha256"]
        ), path
        assert (
            _hash([asdict(item) for item in module_references(contract)])
            == expected["module_references_sha256"]
        ), path
    assert (
        _hash(observation_payload(parse_observation(raw_observation())))
        == pinned["observation_sha256"]
    )
    assert _hash(encode_canonical_model(raw_observation())) == pinned["wire_sha256"]
    assert (
        hashlib.sha256((ROOT / "schema/architecture-contract.schema.json").read_bytes()).hexdigest()
        == pinned["legacy_schema_sha256"]
    )
    assert (
        repr(BoundaryTypeAllowance("a", "return", "", "Page"))
        == "BoundaryTypeAllowance(qualified_name='a', position='return', field_path='', "
        "annotation='Page', container_depth=None)"
    )


def test_bound_origin_reference_is_unique_not_held_and_rename_is_bounded():
    from archkeel.ir.renames import renamed_contract

    contract = parse_contract(_document(alias_body=BODY))
    pointers = {item.pointer: item for item in module_references(contract)}
    pointer = "/rules/0/allowed_positions/0/alias_body/origin"
    assert pointers[pointer].value == BODY["origin"]
    assert not pointers[pointer].held
    assert len([item for item in module_references(contract) if item.pointer == pointer]) == 1
    absent = parse_contract(_document())
    assert pointer not in {item.pointer for item in module_references(absent)}
    for renames, expected in [
        ((("sample", "moved"),), "moved.core.api:Page"),
        ((("sample", "broad"), ("sample.core.api", "exact")), "exact:Page"),
        ((("sample.core.api", "exact"),), "exact:Page"),
        ((("sample.core.ap", "lookalike"),), BODY["origin"]),
        ((("other", "unrelated"),), BODY["origin"]),
    ]:
        changed = renamed_contract(contract, dict(renames))
        body = changed.rules[0].allowed_positions[0].alias_body
        assert body.origin == expected
        assert body.shape == BODY["shape"]


def test_explicit_origin_rename_comparison_preserves_shape_change_as_widening():
    from archkeel.ir.renames import renamed_contract

    before = parse_contract(_document(alias_body=BODY))
    renamed = renamed_contract(before, {"sample.core.api": "moved.api"})
    moved = _document(alias_body={**BODY, "origin": "moved.api:Page"})
    moved["rules"][0]["allowed_positions"][0]["qualified_name"] = "moved.api.run"
    after = parse_contract(moved)
    assert contract_widenings(renamed, after) == ()
    assert len(contract_widenings(before, after)) == 1
    moved["rules"][0]["allowed_positions"][0]["alias_body"]["shape"] = BODY["shape"].replace(
        "sample.core.Metadata", "moved.Metadata"
    )
    changed_shape = parse_contract(moved)
    assert len(contract_widenings(renamed, changed_shape)) == 1


@pytest.mark.parametrize(
    "name",
    [
        "architecture-contract.schema.json",
        "architecture-contract-3.0.schema.json",
        "architecture-contract-3.1.schema.json",
    ],
)
def test_schema_refresh_preserves_version_vocabulary_and_repairs_owned_fragments(name, tmp_path):
    from tools.architecture_graph_schema import _update_contract_schema

    original = (ROOT / "schema" / name).read_bytes()
    target = tmp_path / name
    target.write_bytes(original)
    _update_contract_schema(target)
    assert target.read_bytes() == original
    _update_contract_schema(target)
    assert target.read_bytes() == original
    schema = json.loads(original)
    schema["$defs"]["component"]["properties"]["layer"] = {}
    schema["$defs"]["layerOrder"] = {}
    schema["$defs"]["uml"] = {}
    target.write_text(json.dumps(schema, indent=2) + "\n")
    _update_contract_schema(target)
    assert target.read_bytes() == original
    _update_contract_schema(target)
    assert target.read_bytes() == original
    Draft202012Validator.check_schema(json.loads(target.read_bytes()))


@pytest.mark.parametrize(
    "name",
    [
        "architecture-contract.schema.json",
        "architecture-contract-3.0.schema.json",
        "architecture-contract-3.1.schema.json",
    ],
)
def test_schema_refresh_retains_target_owned_root_constraints(name, tmp_path):
    from tools.architecture_graph_schema import _update_contract_schema

    schema = json.loads((ROOT / "schema" / name).read_bytes())
    constraints = [*schema.get("allOf", []), {"not": {"required": ["opaque"]}}]
    schema["allOf"] = constraints
    target = tmp_path / name
    target.write_text(json.dumps(schema, indent=2) + "\n")
    _update_contract_schema(target)
    refreshed = json.loads(target.read_bytes())
    assert refreshed["allOf"] == constraints
    assert refreshed["$defs"]["boundaryTypes"] == schema["$defs"]["boundaryTypes"]
    assert (
        refreshed["properties"]["rules"]["items"]["oneOf"].count({"$ref": "#/$defs/layerOrder"})
        == 1
    )


@pytest.mark.parametrize("repeated", [False, True])
def test_schema_refresh_cli_updates_explicit_targets_and_keeps_single_target(repeated, tmp_path):
    import subprocess
    import sys

    arguments = []
    targets = []
    names = ["architecture-contract.schema.json"]
    if repeated:
        names.extend(
            ["architecture-contract-3.0.schema.json", "architecture-contract-3.1.schema.json"]
        )
    for name in names:
        target = tmp_path / name
        original = (ROOT / "schema" / name).read_bytes()
        changed = json.loads(original)
        changed["$defs"]["component"]["properties"]["layer"] = {}
        target.write_text(json.dumps(changed, indent=2) + "\n")
        targets.append((target, original))
        arguments.extend(["--contract", str(target)])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.architecture_graph_schema",
            str(tmp_path / "graph.json"),
            *arguments,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    for target, original in targets:
        assert target.read_bytes() == original


KEY_BODY = {"origin": "sample.app.profile:SexKey", "shape": "str | None"}


@pytest.mark.parametrize("root_body", [None, BODY])
def test_key_alias_body_contract31_roundtrip(root_body):
    from archkeel.ir.model import BoundaryAliasBody

    raw = _document(
        "3.1.0", key_alias_body=KEY_BODY, **({"alias_body": root_body} if root_body else {})
    )
    contract = parse_contract(raw)
    selector = contract.rules[0].allowed_positions[0]
    assert selector.key_alias_body == BoundaryAliasBody(**KEY_BODY)
    with pytest.raises(FrozenInstanceError):
        selector.key_alias_body.origin = "changed"
    encoded = json.loads(contract_bytes(contract))
    assert _validator("3.1.0").is_valid(encoded)
    assert parse_contract(encoded) == contract
    assert _rule_payload(contract.rules[0])["allowed_positions"][0]["key_alias_body"] == KEY_BODY
    declaration = project_rule_declaration(contract.rules[0])
    assert declaration["data"]["allowed_positions"][0]["key_alias_body"] == KEY_BODY
    observed = raw_observation()
    observed["declarations"] = [declaration]
    parsed = parse_observation(decode_canonical_model(encode_canonical_model(observed)))
    assert (
        observation_payload(parsed)["declarations"][0]["data"]["allowed_positions"][0][
            "key_alias_body"
        ]
        == KEY_BODY
    )
    opaque = {"origin": "  sample.app.profile:SexKey  ", "shape": " str | None\n"}
    roundtrip = parse_contract(_document("3.1.0", key_alias_body=opaque))
    assert (
        json.loads(contract_bytes(roundtrip))["rules"][0]["allowed_positions"][0]["key_alias_body"]
        == opaque
    )


@pytest.mark.parametrize(
    "body",
    [
        None,
        [],
        "body",
        {},
        {"origin": "x"},
        {"shape": "x"},
        {**KEY_BODY, "extra": True},
        {**KEY_BODY, "origin": ""},
        {**KEY_BODY, "origin": "  "},
        {**KEY_BODY, "shape": ""},
        {**KEY_BODY, "shape": "\n"},
        {**KEY_BODY, "origin": 1},
        {**KEY_BODY, "shape": False},
        {**KEY_BODY, "origin": None},
        {**KEY_BODY, "shape": []},
    ],
)
def test_key_alias_body_rejects_malformed_pairs(body):
    raw = _document("3.1.0", key_alias_body=body)
    assert not _validator("3.1.0").is_valid(raw)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize(
    "coordinates",
    [
        {"field_path": "payload"},
        {"mapping_depth": 1},
        {"container_depth": 1},
        {"container_depth": 0},
        {"container_depth": None},
    ],
)
def test_key_alias_body_requires_empty_path_and_absent_depth(coordinates):
    raw = _document("3.1.0", key_alias_body=KEY_BODY, **coordinates)
    assert not _validator("3.1.0").is_valid(raw)
    with pytest.raises(ValueError):
        parse_contract(raw)


@pytest.mark.parametrize("version", ["2.1.0", "2.2.0", "2.3.0", "3.0.0"])
def test_key_alias_body_rejects_old_versions(version, tmp_path):
    raw = _document(version, key_alias_body=KEY_BODY)
    schema_name = (
        "architecture-contract-3.0.schema.json"
        if version == "3.0.0"
        else "architecture-contract.schema.json"
    )
    assert not Draft202012Validator(
        json.loads((ROOT / "schema" / schema_name).read_bytes())
    ).is_valid(raw)
    with pytest.raises(ValueError, match="key_alias_body.*3.1.0"):
        parse_contract(raw)
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="key_alias_body.*3.1.0"):
        load_contract(path)
    bound = parse_contract(_document("3.1.0", key_alias_body=KEY_BODY))
    with pytest.raises(ValueError, match="key_alias_body.*3.1.0"):
        contract_bytes(replace(bound, schema_version=version))


@pytest.mark.parametrize("field", ["origin", "shape"])
def test_key_alias_body_identity_and_amendment(field):
    before = parse_contract(_document("3.1.0", key_alias_body=KEY_BODY))
    after = parse_contract(_document("3.1.0", key_alias_body={**KEY_BODY, field: "changed"}))
    assert len(contract_widenings(before, after)) == 1
    amendment = Amendment(contract_digest(before), contract_digest(after), "who", "why")
    assert verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(after)
    )
    assert not verify_amendment(
        amendment, before_digest=contract_digest(before), after_digest=contract_digest(before)
    )
    raw = _document("3.1.0", key_alias_body=KEY_BODY)
    positions = raw["rules"][0]["allowed_positions"]
    positions += [
        {**positions[0], "key_alias_body": {**KEY_BODY, field: "changed"}},
        {key: value for key, value in positions[0].items() if key != "key_alias_body"},
    ]
    assert len(parse_contract(raw).rules[0].allowed_positions) == 3
    assert _validator("3.1.0").is_valid(raw)
    positions.append({**positions[0], "key_alias_body": dict(reversed(list(KEY_BODY.items())))})
    assert not _validator("3.1.0").is_valid(raw)
    with pytest.raises(ValueError, match="unique entries"):
        parse_contract(raw)


def test_key_alias_body_widening_sort_and_origin_rename():
    from archkeel.ir.renames import renamed_contract

    body = {**BODY, "shape": "dict[SexKey, str] | dict[str, int]"}
    before = parse_contract(
        _document("3.1.0", alias_body=body, key_alias_body=KEY_BODY, field_path="")
    )
    pointer = "/rules/0/allowed_positions/0/key_alias_body/origin"
    references = [item for item in module_references(before) if item.pointer == pointer]
    assert len(references) == 1 and references[0].value == KEY_BODY["origin"]
    assert not references[0].held
    renamed = renamed_contract(before, {"sample.app.profile": "moved.profile"})
    selector = renamed.rules[0].allowed_positions[0]
    assert selector.key_alias_body.origin == "moved.profile:SexKey"
    assert selector.key_alias_body.shape == KEY_BODY["shape"]
    assert selector.alias_body == before.rules[0].allowed_positions[0].alias_body
    changed = parse_contract(
        _document(
            "3.1.0",
            alias_body={**body, "shape": body["shape"].replace("SexKey", "moved.profile.SexKey")},
            key_alias_body={**KEY_BODY, "origin": "moved.profile:SexKey"},
        )
    )
    assert len(contract_widenings(renamed, changed)) == 1
    raw = _document("3.1.0")
    first = raw["rules"][0]["allowed_positions"][0]
    raw["rules"][0]["allowed_positions"] = [
        {**first, "key_alias_body": {"origin": origin, "shape": shape}}
        for origin, shape in [("b", "a"), ("a", "b"), ("a", "a")]
    ] + [first]
    empty = replace(before, rules=(replace(before.rules[0], allowed_positions=()),))
    after = parse_contract(raw)
    changes = contract_widenings(empty, after)
    raw["rules"][0]["allowed_positions"].reverse()
    assert contract_widenings(empty, parse_contract(raw)) == changes
    assert "key_alias_body" not in changes[0]
    assert "origin='a', shape='a'" in changes[1]
    assert "origin='a', shape='b'" in changes[2]
    assert "origin='b', shape='a'" in changes[3]
