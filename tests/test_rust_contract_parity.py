# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-359: the Rust contract parser decides each contract as the Python parser does.

The corpus is each contract of the repository, the invalid contracts of `tests/contracts/invalid`
and mutations of the smallest contract that holds each part of the grammar. For each contract the
accept or reject decision and the error kind must be equal. For an accepted contract the canonical
bytes, the digest of the bytes and the canonical digest must be equal. The Rust parser can stop
with `unsupported` only at a part of slice 0c-2: a `declarations` object or a Python-only rule.
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
STRUCTURAL = {
    "forbidden_dependency",
    "allowed_dependency",
    "sibling_isolation",
    "layer_order",
    "complete_requires",
    "complete_assignment",
    "root_layout",
    "external_dependency_scope",
    "complete_external_scope",
    "no_component_cycles",
    "interface_boundary",
    "forbidden_construct",
}
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
]
# The optional keys of each role, so that each one is tested absent, null and present, also when
# the smallest contract of the role does not write it.
OPTIONAL_KEYS: dict[str, tuple[str, ...]] = {
    "root": ("$schema", "declarations"),
    "component": (
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
    "requires": ("through", "decided_by"),
    "rule:forbidden_dependency": (
        "target_symbol",
        "allowed_sources",
        "source_match",
        "target_match",
        "target_kind",
    ),
    "rule:forbidden_construct": (
        "allowed_sources",
        "exact_sources",
        "allowed_type_ignores",
        "selector",
    ),
    "rule:external_dependency_scope": ("allowed_sources", "exact_sources"),
    "rule:complete_requires": ("include_type_checking",),
    "rule:layer_order": ("components",),
    "rule:no_component_cycles": ("level", "components"),
    "rule:interface_boundary": ("include_type_checking", "module_object_grants"),
    "rule:sibling_isolation": ("include_type_checking",),
    "selector": ("member", "literal"),
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


def _probe() -> Path:
    """Build the parity probe of the contract crate under the native build lock."""
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native contract parity test.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [cargo, "build", "--locked", "-p", "archkeel-contract", "--example", "contract_dump"]
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
    lines = done.stdout.decode().splitlines()
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


def _unported(value: object) -> bool:
    """Whether a contract holds a part of slice 0c-2."""
    if not isinstance(value, dict):
        return False
    rules = value.get("rules")
    kinds = (
        {rule.get("kind") for rule in rules if isinstance(rule, dict)}
        if isinstance(rules, list)
        else set()
    )
    return value.get("declarations") is not None or bool(kinds - STRUCTURAL)


def _encode(value: object) -> bytes:
    return json.dumps(value, indent=2).encode()


def _objects(contract: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Each object of the grammar in a contract, named by its role."""
    yield "root", contract
    for component in contract["components"]:
        yield "component", component
        for entry in component.get("requires") or []:
            yield "requires", entry
    for rule in contract["rules"]:
        yield f"rule:{rule['kind']}", rule
        if isinstance(rule.get("selector"), dict):
            yield "selector", rule["selector"]
        for nested in ("allowed_type_ignores", "module_object_grants"):
            for entry in rule.get(nested) or []:
                yield nested, entry


def _paths(contract: dict[str, Any]) -> Iterator[tuple[str, list[str | int]]]:
    """The role and the path of each object, so a mutation can find it in a copy."""
    yield "root", []
    for index, component in enumerate(contract["components"]):
        yield "component", ["components", index]
        for position, _ in enumerate(component.get("requires") or []):
            yield "requires", ["components", index, "requires", position]
    for index, rule in enumerate(contract["rules"]):
        yield f"rule:{rule['kind']}", ["rules", index]
        if isinstance(rule.get("selector"), dict):
            yield "selector", ["rules", index, "selector"]
        for nested in ("allowed_type_ignores", "module_object_grants"):
            for position, _ in enumerate(rule.get(nested) or []):
                yield nested, ["rules", index, nested, position]


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
        for role, path in _paths(source):
            if role in done:
                continue
            done.add(role)
            keys = dict.fromkeys([*_at(source, path), *OPTIONAL_KEYS.get(role, ()), "zz_unknown"])
            for key in keys:
                for value in ["<delete>", *VALUES]:
                    for version in (source["schema_version"], "3.14.0"):
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


def special_cases(base: bytes) -> list[Case]:
    text = base.decode()
    return [
        ("not UTF-8", b"\xff" + base),
        ("not an object", b"[]"),
        ("trailing text", base + b"x"),
        ("BOM", b"\xef\xbb\xbf" + base),
        (
            "escaped text",
            text.replace('"rationale": "', '"rationale": "\\t\\u0001\\"\xe9 ', 1).encode(),
        ),
    ]


def test_the_rust_parser_decides_each_contract_as_python_does() -> None:
    repository = repository_contracts()
    comparable = []
    for _, raw in repository:
        value = json.loads(raw)
        if _is_contract(value) and not _unported(value) and _python(raw)["kind"] == "accept":
            comparable.append(value)
    generated = mutations(comparable)
    special = special_cases(_encode(comparable[0]))
    cases = repository + generated + special
    outcomes = _rust(cases)
    tally: Counter[str] = Counter()
    unsupported: Counter[str] = Counter()
    for index, ((name, raw), rust) in enumerate(zip(cases, outcomes, strict=True)):
        python = _python(raw)
        group = "repository" if index < len(repository) else "generated"
        if rust["kind"] == "unsupported":
            assert _unported(json.loads(raw)), (name, rust)
            unsupported[rust["part"].split(":")[0]] += 1
            tally[f"{group} unsupported"] += 1
            continue
        assert rust["kind"] == python["kind"], (name, rust, python)
        if python["kind"] == "accept":
            assert rust == python, name
        tally[f"{group} {'accepted' if python['kind'] == 'accept' else 'rejected'}"] += 1
    print(dict(tally), dict(unsupported))
    assert tally["repository accepted"] >= 38
    assert tally["repository rejected"] >= 17
    assert tally["generated rejected"] >= 1000
    assert tally["generated accepted"] >= 100


def test_a_repeated_key_is_refused_in_rust_and_kept_last_in_python() -> None:
    raw = b'{"schema_version": "2.1.0", "components": [], "rules": [], "rules": []}'
    assert _python(raw)["kind"] == "accept"
    assert _rust([("repeated key", raw)])[0]["kind"] == "duplicate_key"


def test_a_declarations_object_and_a_python_only_rule_are_unsupported_by_name() -> None:
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
    outcomes = _rust([("declarations", declared), ("call_owner", python_only)])
    assert [(item["kind"], item["part"]) for item in outcomes] == [
        ("unsupported", "declarations"),
        ("unsupported", "rule:CallOwner"),
    ]
