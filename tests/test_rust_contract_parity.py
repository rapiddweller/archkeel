# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-359: the Rust contract parser decides each contract as the Python parser does.

The corpus is each contract of the repository, the invalid contracts of `tests/contracts/invalid`
and mutations of the smallest contract that holds each part of the grammar. For each contract the
accept or reject decision and the error kind must be equal. For an accepted contract the canonical
bytes, the digest of the bytes and the canonical digest must be equal.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock
from rust_contract_declaration_cases import declaration_cases, full
from rust_contract_graph_cases import base, graph_cases

from archkeel.ir.codec import (
    ContractInputError,
    ContractVersionError,
    contract_bytes,
    contract_digest,
    decode_json,
    parse_contract,
)

ROOT = Path(__file__).parents[1]
NATIVE = ROOT / "native"
VALUES: list[Any] = [
    None,
    0,
    1,
    -1,
    1.5,
    True,
    "",
    " ",
    "\x1c",
    "x",
    "a.b",
    "prefix",
    "exact",
    "module",
    "component",
    "planned",
    "architect",
    "\u00e9t\u00e9.x",
    "1a",
    "a..b",
    "a:B",
    "@s/p-1",
    [],
    ["x"],
    ["x", "x"],
    ["a.b", "a.c"],
    ["a:B", "a.b:C"],
    [1],
    {},
    "call",
    "equality",
    "constructor",
    "import_namespace",
    [{"source_module": "a.b", "target_module": "a.c"}],
    [{"qualified_name": "a.b", "line": 1, "statement": "s", "tag": "t"}],
    {"receiver": "a.b", "role": "call", "member": "m"},
    {"receiver": "a", "role": "equality", "member": "m", "literal": ""},
    [{"component": "x", "rationale": "r"}],
    "referenced",
    "method",
    "symbol",
    "inherits",
    "requires",
    "1.0.0",
    "1.3.0",
    "closed",
    "read",
    "permanent",
    "cycle_edges",
    "src/a.py",
    "a/../b.py",
    "a//b.py",
    "dict",
    "Mapping",
    "python",
    "body",
]
# The optional keys of each role, so that each one is tested absent, null and present, also when
# the smallest contract of the role does not write it.
_SOURCES = ("allowed_sources", "exact_sources")
OPTIONAL_KEYS: dict[str, tuple[str, ...]] = {
    "root": ("$schema", "declarations"),
    "components": (
        "capability_id",
        "decided_by",
        "inside",
        "planned",
        "public",
        "requires",
        "namespace",
        "exact_modules",
        "layer",
        "lifecycle",
    ),
    "components.requires": ("through", "decided_by"),
    "rule:forbidden_dependency": (
        "target_symbol",
        "allowed_sources",
        "source_match",
        "target_match",
        "target_kind",
    ),
    "rule:forbidden_construct": (*_SOURCES, "allowed_type_ignores", "selector"),
    "rule:forbidden_construct.selector": ("member", "literal"),
    "rule:external_dependency_scope": _SOURCES,
    "rule:complete_requires": ("include_type_checking",),
    "rule:layer_order": ("components",),
    "rule:no_component_cycles": ("level", "components"),
    "rule:interface_boundary": ("include_type_checking", "module_object_grants"),
    "rule:sibling_isolation": ("include_type_checking",),
    "rule:symbol_placement": _SOURCES,
    "rule:source_ownership": ("symbols", "parameters", "owner", "value_owner"),
    "rule:boundary_types": (*_SOURCES, "allowed_positions"),
    "rule:boundary_types.allowed_positions": (
        "field_path",
        "container_depth",
        "mapping_depth",
        "alias_body",
        "key_alias_body",
        "literal_mapping_arm",
        "native_mapping",
    ),
    "rule:call_owner": _SOURCES,
    "rule:catalog_argument": ("overlays", "source_match"),
    "rule:catalog_use": ("overlays", "member", "source_match", "target", "parameter"),
    "rule:protocol_declarations.selectors": ("optional",),
    "declarations": (
        "capabilities",
        "review_scopes",
        "public_api",
        "public_api_provenance",
        "public_commands",
        "context_roots",
        "context_roots_provenance",
        "paths",
        "spot_owners",
        "compat",
        "measurement_budgets",
        "facade_budgets",
        "coupling_budgets",
        "modules",
        "uml",
    ),
    "declarations.uml": ("entities", "relationships", "scopes"),
    "declarations.uml.entities": (
        "parent_id",
        "visibility",
        "signature",
        "annotation",
        "modifiers",
        "presence",
        "responsibilities",
        "evidence_ids",
        "provenance",
        "record_ids",
        "definition_contexts",
        "initializer",
        "file_path",
    ),
    "declarations.uml.entities.visibility": ("kind", "basis", "spelling"),
    "declarations.uml.entities.signature": ("parameters", "returns"),
    "declarations.uml.entities.signature.parameters": (
        "annotation",
        "kind",
        "default",
        "default_known",
    ),
    "declarations.uml.relationships": (
        "target_id",
        "resolution",
        "candidate_ids",
        "expression",
        "evidence_ids",
        "provenance",
        "record_ids",
        "candidate_count",
        "candidates_truncated",
        "reason",
        "through",
        "decided_by",
    ),
    "declarations.uml.scopes": ("entity_kinds", "relationship_kinds"),
}
VERSIONS = [
    "2.1.0",
    "2.2.0",
    "2.3.0",
    "2.4.0",
    "3.3.0",
    "3.4.0",
    "3.5.0",
    "3.6.0",
    "3.11.0",
    "3.14.0",
    "9.9.9",
    "",
    2,
    None,
]
Case = tuple[str, bytes]
# The keys that a contract version gates: a mutation of one of them runs under 3.14.0 too.
GATED = frozenset(
    {
        "source_match",
        "target_match",
        "target_kind",
        "selector",
        "module_object_grants",
        "layer",
        "lifecycle",
        "uml",
        "alias_body",
        "key_alias_body",
        "literal_mapping_arm",
        "native_mapping",
        "container_depth",
        "declarations",
        "kind",
        "schema_version",
    }
)


def _probe() -> Path:
    """Build the parity probe of the contract crate under the native build lock.

    `ARCHKEEL_CONTRACT_PROBE` names another probe binary: the fault proof of AD-364 builds one
    from a scratch copy with one check disabled.
    """
    planted = os.environ.get("ARCHKEEL_CONTRACT_PROBE")
    if planted:
        return Path(planted)
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native contract parity test.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [
        cargo,
        "build",
        "--locked",
        "--profile",
        "parity",
        "-p",
        "archkeel-contract",
        "--example",
        "contract_dump",
    ]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        built = subprocess.run(command, cwd=NATIVE, capture_output=True, text=True, check=False)
    assert built.returncode == 0, built.stderr
    return (
        NATIVE / "target/debug/examples" / ("contract_dump" + (".exe" if os.name == "nt" else ""))
    )


def _rust(cases: list[Case]) -> list[dict[str, Any]]:
    frames = b"".join(str(len(raw)).encode() + b"\n" + raw for _, raw in cases)
    done = subprocess.run([_probe()], input=frames, capture_output=True, check=False)
    assert done.returncode == 0, done.stderr.decode()
    # A line ends at a line feed only: an accepted text can hold U+2028 or U+0085.
    lines = done.stdout.decode().split("\n")[:-1]
    assert len(lines) == len(cases)
    return [json.loads(line) for line in lines]


def _python(raw: bytes) -> dict[str, Any]:
    try:
        contract = parse_contract(decode_json(raw))
    except ContractVersionError:
        return {"kind": "version"}
    except ContractInputError:
        return {"kind": "input"}
    except ValueError:
        return {"kind": "invalid"}
    return {
        "kind": "accept",
        "canonical": contract_bytes(contract).decode(),
        "digest": hashlib.sha256(raw).hexdigest(),
        "canonical_digest": contract_digest(contract),
    }


def _is_contract(value: object) -> bool:
    return isinstance(value, dict) and {"schema_version", "components", "rules"} <= set(value)


def repository_contracts() -> list[Case]:
    names = subprocess.run(
        ["git", "ls-files", "*.json"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    cases = []
    for name in sorted(names):
        raw = (ROOT / name).read_bytes()
        try:
            value = json.loads(raw)
        except ValueError:
            continue
        if _is_contract(value) or name.startswith("tests/contracts/"):
            cases.append((name, raw))
    return cases


def _encode(value: object) -> bytes:
    return json.dumps(value, indent=2).encode()


def _role(document: dict[str, Any], path: list[str | int]) -> str:
    """The role of an object: the keys of its path, with a rule named by its kind."""
    if not path:
        return "root"
    if path[0] == "rules" and len(path) > 1:
        kind = _at(document, path[:2]).get("kind")
        rest = [str(step) for step in path[2:] if isinstance(step, str)]
        return ".".join([f"rule:{kind}", *rest])
    return ".".join(str(step) for step in path if isinstance(step, str))


def _paths(document: Any, path: list[str | int] | None = None) -> Iterator[list[str | int]]:
    """The path of each JSON object of a contract, so a mutation can find it in a copy."""
    path = path or []
    if isinstance(document, dict):
        yield path
        for key, value in document.items():
            yield from _paths(value, [*path, key])
    elif isinstance(document, list):
        for index, value in enumerate(document):
            yield from _paths(value, [*path, index])


def _at(document: Any, path: list[str | int]) -> Any:
    for step in path:
        document = document[step]
    return document


def mutations(sources: list[dict[str, Any]]) -> list[Case]:
    """Delete, replace and add keys of the first object of each role in the smallest contract."""
    done: set[str] = set()
    cases: list[Case] = []
    for source in sorted(sources, key=lambda value: len(_encode(value))):
        for version in VERSIONS:
            cases.append((f"version {version!r}", _encode({**source, "schema_version": version})))
        for path in _paths(source):
            role = _role(source, path)
            if role in done:
                continue
            done.add(role)
            keys = dict.fromkeys([*_at(source, path), *OPTIONAL_KEYS.get(role, ()), "zz_unknown"])
            for key in keys:
                for value in ["<delete>", *VALUES]:
                    versions = (source["schema_version"], "3.14.0") if key in GATED else ()
                    for version in versions or (source["schema_version"],):
                        mutated = copy.deepcopy(source)
                        mutated["schema_version"] = version
                        target = _at(mutated, path)
                        if value == "<delete>":
                            target.pop(key, None)
                        else:
                            target[key] = value
                        cases.append((f"{role}.{key}={value!r}@{version}", _encode(mutated)))
        cases.extend(_semantic(source))
    return cases


def _semantic(source: dict[str, Any]) -> list[Case]:
    """Repeated labels and ids and unknown references."""
    cases = []
    components, rules = source["components"], source["rules"]
    if components:
        twin = {**components[0], "id": "TWIN-ID"}
        cases.append(("repeated label", _encode({**source, "components": [*components, twin]})))
        cases.append(("repeated component", _encode({**source, "components": components * 2})))
        stray = {**components[0], "requires": [{"component": "nope", "rationale": "r"}]}
        cases.append(
            ("unknown requires", _encode({**source, "components": [stray, *components[1:]]}))
        )
    if rules:
        cases.append(("repeated rule", _encode({**source, "rules": [*rules, rules[0]]})))
    return cases


def _separators() -> bytes:
    """A contract whose accepted text holds U+2028 and U+0085 as raw characters."""
    rule = {
        "id": "R",
        "kind": "complete_requires",
        "rationale": "one\u2028two\u0085three",
        "provenance": ["p"],
        "decided_by": "agent",
    }
    document = {"schema_version": "2.1.0", "components": [], "rules": [rule]}
    return json.dumps(document, ensure_ascii=False).encode()


def special_cases(base: bytes) -> list[Case]:
    text = base.decode()
    return [
        ("not UTF-8", b"\xff" + base),
        ("not an object", b"[]"),
        ("trailing text", base + b"x"),
        ("BOM", b"\xef\xbb\xbf" + base),
        ("line separators", _separators()),
        (
            "escaped text",
            text.replace('"rationale": "', '"rationale": "\\t\\u0001\\"\xe9 ', 1).encode(),
        ),
    ]


def test_the_rust_parser_decides_each_contract_as_python_does() -> None:
    repository = repository_contracts()
    accepted = [json.loads(raw) for _, raw in repository if _python(raw)["kind"] == "accept"]
    generated = mutations([*accepted, base(), full()])
    special = special_cases(_encode(min(accepted, key=lambda value: len(_encode(value)))))
    cases = repository + generated + special
    outcomes = _rust(cases)
    tally: Counter[str] = Counter()
    for index, ((name, raw), rust) in enumerate(zip(cases, outcomes, strict=True)):
        python = _python(raw)
        group = "repository" if index < len(repository) else "generated"
        assert rust["kind"] == python["kind"], (name, rust, python)
        if python["kind"] == "accept":
            assert rust == python, name
        tally[f"{group} {'accepted' if python['kind'] == 'accept' else 'rejected'}"] += 1
    print(dict(tally))
    # AD-394 removes the Python TypeScript collector's nested contract.
    assert tally["repository accepted"] >= 89
    assert tally["repository rejected"] >= 20
    assert tally["generated rejected"] >= 10000
    assert tally["generated accepted"] >= 2000


def _assert_equal(cases: list[Case]) -> Counter[str]:
    tally: Counter[str] = Counter()
    for (name, raw), rust in zip(cases, _rust(cases), strict=True):
        python = _python(raw)
        assert rust["kind"] == python["kind"], (name, rust, python)
        if python["kind"] == "accept":
            assert rust == python, name
        tally[python["kind"]] += 1
    return tally


def test_hand_written_cases_decide_as_python() -> None:
    """The UML graph faults and the declaration faults that a single-key mutation cannot build."""
    tally = _assert_equal(graph_cases(_encode) + declaration_cases(_encode))
    assert tally["invalid"] >= 80
    assert tally["accept"] >= 15


def test_a_repeated_key_is_refused_in_rust_and_kept_last_in_python() -> None:
    raw = b'{"schema_version": "2.1.0", "components": [], "rules": [], "rules": []}'
    assert _python(raw)["kind"] == "accept"
    assert _rust([("repeated key", raw)])[0]["kind"] == "duplicate_key"


def test_a_declarations_object_and_a_python_only_rule_parse_as_in_python() -> None:
    declared = b'{"schema_version": "2.1.0", "components": [], "rules": [], "declarations": {}}'
    rule = {
        "id": "R",
        "kind": "call_owner",
        "source": "a",
        "target": "b",
        "rationale": "r",
        "provenance": ["p"],
        "decided_by": "agent",
    }
    python_only = _encode({"schema_version": "3.7.0", "components": [], "rules": [rule]})
    cases = [("declarations", declared), ("call_owner", python_only)]
    assert _rust(cases) == [_python(raw) for _, raw in cases]
