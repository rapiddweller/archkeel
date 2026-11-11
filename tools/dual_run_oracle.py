# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The oracle of the dual run (AD-360): canonical rows, the stored form and the comparison.

A row is canonical when its JSON text has sorted keys, no spaces and the strings of the string
table expanded. L1 is the verdict map (rule id to kind and status); L2 is the rows of a section.
"""

from __future__ import annotations

import difflib
import functools
import gzip
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ORACLE_DIR = Path(__file__).resolve().parent.parent / "tests" / "dual_run"

# The compared sections of architecture.json (`CLASSIFIED_SECTIONS` without `transitive_paths`,
# which is not ported, plus `evidence`). Remove a line when the schema drops a section.
SECTIONS: tuple[str, ...] = (
    "metrics",
    "declarations",
    "scope_observations",
    "packages",
    "modules",
    "symbols",
    "imports",
    "dependency_edges",
    "path_observations",
    "cycles",
    "calls",
    "references",
    "bindings",
    "typing_signals",
    "constructs",
    "contexts",
    "context_evidence",
    "violations",
    "unknowns",
    "evidence",
)
# The rows of these sections belong to the rule families that their `rule_ids` name.
RULE_SECTIONS = frozenset({"violations", "unknowns"})
# The rule families of the WP6 slices (WP6-0, section C). A family name or a rule kind selects.
FAMILIES: dict[str, tuple[str, ...]] = {
    "direction": (
        "forbidden_dependency",
        "allowed_dependency",
        "sibling_isolation",
        "layer_order",
        "complete_requires",
    ),
    "completeness": (
        "complete_assignment",
        "root_layout",
        "external_dependency_scope",
        "complete_external_scope",
    ),
    "cycles": ("no_component_cycles",),
    "interface": ("interface_boundary",),
    "construct": ("forbidden_construct",),
}
# A section with more canonical bytes keeps only the id and a digest of each row.
FULL_ROWS_BYTES = 4096


@dataclass(frozen=True, slots=True)
class Row:
    """One canonical row of a section: the row itself is absent in a compact oracle."""

    id: str
    digest: str
    rule_ids: tuple[str, ...]
    row: dict[str, Any] | None


@dataclass(frozen=True, slots=True)
class Difference:
    case: str
    scope: str
    id: str
    detail: str

    def line(self) -> str:
        return f"{self.case}: {self.scope}: {self.id}: {self.detail}"


@dataclass(frozen=True, slots=True)
class Selection:
    """What a slice owns: sections (L2) and rule kinds (L1); `None` kinds means every kind."""

    sections: tuple[str, ...] = SECTIONS
    kinds: frozenset[str] | None = None


# --- Canonical rows -------------------------------------------------------------------------


def row_text(row: Mapping[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _digest(text: str, size: int = 12) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:size]


def section_digest(texts: Iterable[str]) -> str:
    return _digest("\n".join(texts), 32)


def _expand(value: Any, table: list[str]) -> Any:
    if isinstance(value, str):
        if value[:1] == "$" and value[1:].isdigit():
            return table[int(value[1:])]
        return value[1:] if value[:2] == "$$" else value
    if isinstance(value, list):
        return [_expand(item, table) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item, table) for key, item in value.items()}
    return value


def decode_sections(architecture: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The rows of each section of a columnar architecture.json, with the strings expanded."""
    table = architecture.get("string_table", [])
    encoding = architecture["encoding"]
    record_fields = encoding["record_fields"]
    sections: dict[str, list[dict[str, Any]]] = {}
    for name in SECTIONS:
        encoded = architecture.get(name) or []
        if name == "evidence":
            fields = encoding["evidence_fields"]
            sections[name] = [dict(zip(fields, _expand(r, table), strict=True)) for r in encoded]
            continue
        data_fields = encoding["section_data_fields"].get(name, [])
        rows = []
        for encoded_row in encoded:
            row = dict(zip(record_fields, encoded_row, strict=True))
            data = row.pop("data")
            row = {key: _expand(value, table) for key, value in row.items()}
            row["data"] = {
                key: _expand(value, table)
                for key, value in zip(data_fields, data, strict=True)
                if value != "$m"
            }
            rows.append(row)
        sections[name] = rows
    return sections


def to_rows(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    return [
        Row(str(r["id"]), _digest(row_text(r)), tuple(r.get("rule_ids", ())), dict(r)) for r in rows
    ]


def oracle_section(
    name: str, rows: list[dict[str, Any]], base: tuple[str, str, list[Row]] | None = None
) -> dict[str, Any]:
    """The rows of a section: a full row when the section is small, else its id, digest and
    rule ids. With a base, a run of rows equal to the base is stored as `[start, length]`."""
    texts = [row_text(row) for row in rows]
    entry: dict[str, Any] = {"count": len(rows), "digest": section_digest(texts)}
    full = sum(map(len, texts)) <= FULL_ROWS_BYTES
    items: list[Any] = [
        row
        if full
        else [row["id"], _digest(text), *([row["rule_ids"]] if name in RULE_SECTIONS else [])]
        for row, text in zip(rows, texts, strict=True)
    ]
    if base is None:
        entry["rows"] = items
        return entry
    matcher = difflib.SequenceMatcher(
        None, [row.digest for row in base[2]], [_digest(text) for text in texts], autojunk=False
    )
    entry["base"], entry["base_digest"], entry["rows"] = base[0], base[1], []
    for tag, start, end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            entry["rows"].append([start, end - start])
        elif tag != "delete":
            entry["rows"].extend(items[new_start:new_end])
    return entry


def oracle_rows(entry: Mapping[str, Any], base: list[Row] | None = None) -> list[Row]:
    rows: list[Row] = []
    for item in entry["rows"]:
        if isinstance(item, dict):
            rows.extend(to_rows([item]))
        elif isinstance(item[0], int) and base is not None:
            rows.extend(base[item[0] : item[0] + item[1]])
        else:
            rows.append(Row(item[0], item[1], tuple(item[2] if len(item) > 2 else ()), None))
    return rows


def section_rows(oracle: Mapping[str, Any], name: str) -> list[Row]:
    """The rows of one section of an oracle, with the rows of its base resolved."""
    entry = oracle["sections"][name]
    if "base" not in entry:
        return oracle_rows(entry)
    base = base_oracle(entry["base"])
    if base["sections"][name]["digest"] != entry["base_digest"]:
        raise RuntimeError(
            f"{entry['base']} changed after its delta {name} was recorded: record again"
        )
    return oracle_rows(entry, section_rows(base, name))


@functools.cache
def base_oracle(case_id: str) -> dict[str, Any]:
    return read_oracle(ORACLE_DIR / f"{case_id.replace('/', '--')}.json.gz")


def write_oracle(path: Path, oracle: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(oracle, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    path.write_bytes(gzip.compress(text.encode(), mtime=0))


def read_oracle(path: Path) -> dict[str, Any]:
    oracle: dict[str, Any] = json.loads(gzip.decompress(path.read_bytes()))
    return oracle


# --- Comparison ------------------------------------------------------------------------------


def _explain(index: int, expected: list[Row], actual: list[Row]) -> tuple[str, str]:
    want, have = expected[index], actual[index]
    if want.id != have.id:
        if want.id not in {row.id for row in actual}:
            return want.id, f"row {index}: the candidate drops this row (it has {have.id} here)"
        if have.id not in {row.id for row in expected}:
            return have.id, f"row {index}: the candidate adds this row before {want.id}"
        return have.id, f"row {index}: the order differs: the candidate puts it before {want.id}"
    if want.row is None or have.row is None:
        found = "" if have.row is None else f"; candidate row {row_text(have.row)[:400]}"
        return want.id, f"row {index}: digest {want.digest} expected, {have.digest} found{found}"
    for key in sorted(set(want.row) | set(have.row)):
        if want.row.get(key) != have.row.get(key):
            return want.id, (
                f"row {index}: field {key}: expected {json.dumps(want.row.get(key))[:300]}, "
                f"found {json.dumps(have.row.get(key))[:300]}"
            )
    return want.id, f"row {index}: the rows differ"


def first_difference(
    case: str, name: str, expected: list[Row], actual: list[Row]
) -> Difference | None:
    for index, (want, have) in enumerate(zip(expected, actual, strict=False)):
        if want.digest != have.digest:
            return Difference(case, name, *_explain(index, expected, actual))
    if len(expected) > len(actual):
        row = expected[len(actual)]
        return Difference(case, name, row.id, f"row {len(actual)}: the candidate drops this row")
    if len(actual) > len(expected):
        row = actual[len(expected)]
        return Difference(case, name, row.id, f"row {len(expected)}: the candidate adds this row")
    return None


def owned_rules(rules: Mapping[str, list[str]], kinds: frozenset[str] | None) -> set[str]:
    return {rule for rule, (kind, _) in rules.items() if kinds is None or kind in kinds}


def compare_case(
    oracle: Mapping[str, Any], frame: Mapping[str, Any], selection: Selection
) -> list[Difference]:
    """The verdict differences of the owned rules and the first differing row of each section."""
    case = oracle["case"]["id"]
    expected_rules, actual_rules = oracle["rules"], frame["rules"]
    owned = owned_rules(expected_rules, selection.kinds) | owned_rules(
        actual_rules, selection.kinds
    )
    differences = [
        Difference(
            case,
            "rules",
            rule,
            f"expected {expected_rules.get(rule)}, found {actual_rules.get(rule)}",
        )
        for rule in sorted(owned)
        if expected_rules.get(rule) != actual_rules.get(rule)
    ]
    if (oracle["sections"] is None) != (
        frame.get("architecture") is None and not frame.get("sections")
    ):
        found = "no architecture.json" if oracle["sections"] is not None else "an architecture.json"
        return [
            *differences,
            Difference(case, "architecture", "-", f"the candidate writes {found}"),
        ]
    if oracle["sections"] is None:
        return differences
    actual_sections = frame_sections(frame)
    for name in selection.sections:
        actual = actual_sections.get(name, [])
        if selection.kinds is None or name not in RULE_SECTIONS:
            texts = (row_text(row.row) for row in actual if row.row is not None)
            if section_digest(texts) == oracle["sections"][name]["digest"]:
                continue
        expected = section_rows(oracle, name)
        if selection.kinds is not None and name in RULE_SECTIONS:
            expected = [row for row in expected if owned.intersection(row.rule_ids)]
            actual = [row for row in actual if owned.intersection(row.rule_ids)]
        difference = first_difference(case, name, expected, actual)
        if difference is not None:
            differences.append(difference)
    return differences


def frame_sections(frame: Mapping[str, Any]) -> dict[str, list[Row]]:
    """An engine frame carries a columnar `architecture` or the decoded `sections`."""
    if frame.get("architecture") is not None:
        sections = decode_sections(frame["architecture"])
    else:
        sections = frame.get("sections") or {}
    return {name: to_rows(rows) for name, rows in sections.items()}


def selection_of(sections: str | None, families: str | None) -> Selection:
    chosen = SECTIONS if not sections else tuple(sections.split(","))
    unknown = sorted(set(chosen) - set(SECTIONS))
    if unknown:
        raise SystemExit(f"unknown sections: {', '.join(unknown)}")
    if not families:
        return Selection(chosen, None)
    kinds = frozenset(k for name in families.split(",") for k in FAMILIES.get(name, (name,)))
    return Selection(chosen, kinds)
