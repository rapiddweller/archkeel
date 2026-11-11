# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The oracle of the dual run (AD-360): canonical rows, the stored form and the comparison.

A row is canonical when its JSON text has sorted keys, no spaces and the strings of the string
table expanded. L1 is the verdict map (rule id to kind and status); L2 is the rows of a section.
The sections and the rule families are data: `tools/dual_run_schema.json`.
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
SCHEMA = json.loads((Path(__file__).resolve().parent / "dual_run_schema.json").read_text())
SECTIONS: tuple[str, ...] = tuple(SCHEMA["sections"])
NOT_COMPARED = frozenset(SCHEMA["not_compared"])
# The rows of these sections belong to the rule families that their `rule_ids` name.
RULE_SECTIONS = frozenset(SCHEMA["rule_sections"])
RULE_KINDS = frozenset(SCHEMA["rule_kinds"])
FAMILIES: dict[str, tuple[str, ...]] = {k: tuple(v) for k, v in SCHEMA["families"].items()}
# A large section keeps these fields of each row, so a difference shows the expected content.
KEY_FIELDS: tuple[str, ...] = tuple(SCHEMA["key_fields"])
# A section with more canonical bytes keeps the id, digest, rule ids and key fields of each row.
FULL_ROWS_BYTES = 4096
# `--sections none` and `--families none`: the slice owns no section or no rule family.
NONE = "none"


@dataclass(frozen=True, slots=True)
class Row:
    """One canonical row: `row` is the full row, or `None` in a large section of an oracle."""

    id: str
    digest: str
    rule_ids: tuple[str, ...]
    row: dict[str, Any] | None
    keys: dict[str, Any]


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
    """What a slice owns: sections (L2) and rule kinds (L1); `None` kinds means every kind.
    `self_test` compares what the engine read (the rule ids and kinds of the contract, the
    reply), the wiring check of an engine that owns nothing yet (AD-363)."""

    sections: tuple[str, ...] = SECTIONS
    kinds: frozenset[str] | None = None
    self_test: bool = False

    def owns_nothing(self) -> bool:
        return not self.sections and self.kinds is not None and not self.kinds


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


def document_sections(architecture: Mapping[str, Any]) -> set[str]:
    """The names of the row sections that a columnar architecture.json declares."""
    return {*architecture["encoding"]["section_data_fields"], "evidence"}


def decode_sections(architecture: Mapping[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The rows of each compared section of a columnar architecture.json, strings expanded."""
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


def _keys(row: Mapping[str, Any]) -> dict[str, Any]:
    return {key: row[key] for key in KEY_FIELDS if key in row}


def to_rows(rows: Iterable[Mapping[str, Any]]) -> list[Row]:
    return [
        Row(str(r["id"]), _digest(row_text(r)), tuple(r.get("rule_ids") or ()), dict(r), _keys(r))
        for r in rows
    ]


def oracle_section(
    rows: list[dict[str, Any]], base: tuple[str, str, list[Row]] | None = None
) -> dict[str, Any]:
    """The rows of a section: full rows when the section is small, else the id, digest, rule ids
    and key fields of each row. With a base, a run of rows equal to the base is `[start, n]`."""
    texts = [row_text(row) for row in rows]
    entry: dict[str, Any] = {"count": len(rows), "digest": section_digest(texts)}
    full = sum(map(len, texts)) <= FULL_ROWS_BYTES
    items: list[Any] = [
        row if full else [row["id"], _digest(text), row.get("rule_ids") or [], _keys(row)]
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
            rows.append(Row(item[0], item[1], tuple(item[2]), None, item[3]))
    return rows


def section_rows(oracle: Mapping[str, Any], name: str, directory: Path = ORACLE_DIR) -> list[Row]:
    """The rows of one section of an oracle, with the rows of its base resolved."""
    entry = oracle["sections"][name]
    if "base" not in entry:
        return oracle_rows(entry)
    base = base_oracle(entry["base"], directory)
    if base["sections"][name]["digest"] != entry["base_digest"]:
        raise RuntimeError(
            f"{entry['base']} changed after its delta {name} was recorded: record again"
        )
    return oracle_rows(entry, section_rows(base, name, directory))


def oracle_file(directory: Path, case_id: str) -> Path:
    return directory / f"{case_id.replace('/', '--')}.json.gz"


@functools.cache
def base_oracle(case_id: str, directory: Path = ORACLE_DIR) -> dict[str, Any]:
    return read_oracle(oracle_file(directory, case_id))


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
            return want.id, f"row {index}: the candidate drops this row {_shown(want)}"
        if have.id not in {row.id for row in expected}:
            return have.id, f"row {index}: the candidate adds this row before {want.id}"
        return have.id, f"row {index}: the order differs: the candidate puts it before {want.id}"
    if want.row is None or have.row is None:
        keys = sorted(set(want.keys) | set(have.keys))
        changed = [key for key in keys if want.keys.get(key) != have.keys.get(key)]
        if changed:
            return want.id, _field(index, changed[0], want.keys, have.keys)
        return want.id, f"row {index}: a field outside {list(KEY_FIELDS)} differs {_shown(want)}"
    for key in sorted(set(want.row) | set(have.row)):
        if want.row.get(key) != have.row.get(key):
            return want.id, _field(index, key, want.row, have.row)
    return want.id, f"row {index}: the rows differ"


def _shown(row: Row) -> str:
    return json.dumps(row.keys if row.row is None else row.row, ensure_ascii=False)[:400]


def _field(index: int, key: str, want: Mapping[str, Any], have: Mapping[str, Any]) -> str:
    return (
        f"row {index}: field {key}: expected {json.dumps(want.get(key))[:300]}, "
        f"found {json.dumps(have.get(key))[:300]}"
    )


def first_difference(
    case: str, name: str, expected: list[Row], actual: list[Row]
) -> Difference | None:
    for index, (want, have) in enumerate(zip(expected, actual, strict=False)):
        if want.digest != have.digest:
            return Difference(case, name, *_explain(index, expected, actual))
    if len(expected) > len(actual):
        row = expected[len(actual)]
        detail = f"row {len(actual)}: the candidate drops this row {_shown(row)}"
        return Difference(case, name, row.id, detail)
    if len(actual) > len(expected):
        row = actual[len(expected)]
        return Difference(case, name, row.id, f"row {len(expected)}: the candidate adds this row")
    return None


def owned_rules(rules: Mapping[str, list[str]], kinds: frozenset[str] | None) -> set[str]:
    return {rule for rule, (kind, _) in rules.items() if kinds is None or kind in kinds}


def _owned_row(row: Row, owned: set[str]) -> bool:
    """A row without rule ids belongs to every family: no slice can drop it unseen."""
    return not row.rule_ids or bool(owned.intersection(row.rule_ids))


def compare_case(
    oracle: Mapping[str, Any],
    frame: Mapping[str, Any],
    selection: Selection,
    directory: Path = ORACLE_DIR,
) -> list[Difference]:
    """The verdict differences of the owned rules and the first differing row of each section.
    `directory` holds the base of a delta oracle."""
    case = oracle["case"]["id"]
    if frame.get("error"):
        return [Difference(case, "engine", "-", frame["error"])]
    expected_rules, actual_rules = oracle["rules"], frame["rules"]
    kinds = selection.kinds
    owned = owned_rules(expected_rules, kinds) | owned_rules(actual_rules, kinds)
    unsupported = frame.get("unsupported") or {}
    differences = [*_self_test(case, oracle, frame)] if selection.self_test else []
    owned, named = _unsupported_rules(case, owned, unsupported.get("rules"))
    differences += named
    differences += [
        Difference(
            case,
            "rules",
            rule,
            f"expected {expected_rules.get(rule)}, found {actual_rules.get(rule)}",
        )
        for rule in sorted(owned)
        if expected_rules.get(rule) != actual_rules.get(rule)
    ]
    not_ported = unsupported.get("sections") or {}
    differences += [
        Difference(case, name, "-", not_ported[name])
        for name in selection.sections
        if name in not_ported
    ]
    sections = tuple(name for name in selection.sections if name not in not_ported)
    if not sections:
        return differences
    selection = Selection(sections, kinds)
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
    actual_sections, names = frame_sections(frame)
    differences += [
        Difference(case, name, "-", "the candidate writes a section outside the known list")
        for name in sorted(names - set(SECTIONS) - NOT_COMPARED)
    ]
    for name in selection.sections:
        actual = actual_sections.get(name, [])
        if kinds is None or name not in RULE_SECTIONS:
            texts = (row_text(row.row) for row in actual if row.row is not None)
            if section_digest(texts) == oracle["sections"][name]["digest"]:
                continue
        expected = section_rows(oracle, name, directory)
        if kinds is not None and name in RULE_SECTIONS:
            expected = [row for row in expected if _owned_row(row, owned)]
            actual = [row for row in actual if _owned_row(row, owned)]
        difference = first_difference(case, name, expected, actual)
        if difference is not None:
            differences.append(difference)
    return differences


def _unsupported_rules(
    case: str, owned: set[str], reasons: str | Mapping[str, str] | None
) -> tuple[set[str], list[Difference]]:
    """The owned rules that the engine decides, and one difference for the owned rules that it
    names unsupported: a named part is never equal (AD-363)."""
    if not reasons or not owned:
        return owned, []
    if isinstance(reasons, str):
        return set(), [Difference(case, "rules", "-", f"{len(owned)} owned rules: {reasons}")]
    named = sorted(owned.intersection(reasons))
    if not named:
        return owned, []
    detail = f"{len(named)} owned rules are unsupported, first: {reasons[named[0]]}"
    return owned - set(named), [Difference(case, "rules", named[0], detail)]


def _self_test(case: str, oracle: Mapping[str, Any], frame: Mapping[str, Any]) -> list[Difference]:
    """The rule ids and kinds that the engine read from the contract bytes must equal the
    verdict map of the oracle, and the engine must accept the collector reply."""
    found = frame.get("self_test") or {}
    contract, reply = found.get("contract") or {}, found.get("reply") or {}
    differences = []
    if "rules" in contract:
        expected = {rule: kind for rule, (kind, _) in oracle["rules"].items()}
        differences += [
            Difference(
                case,
                "self_test",
                rule,
                f"kind {expected.get(rule)} expected, {contract['rules'].get(rule)} read",
            )
            for rule in sorted(set(expected) | set(contract["rules"]))
            if expected.get(rule) != contract["rules"].get(rule)
        ]
    else:
        detail = contract.get("unsupported") or f"refused: {contract.get('refused')}"
        differences.append(Difference(case, "self_test", "contract", detail))
    if "files" not in reply:
        detail = f"refused: {reply['refused']}" if "refused" in reply else f"absent: {reply}"
        differences.append(Difference(case, "self_test", "reply", detail))
    return differences


def frame_sections(frame: Mapping[str, Any]) -> tuple[dict[str, list[Row]], set[str]]:
    """The compared rows of an engine frame (a columnar `architecture` or the decoded
    `sections`) and the names of all sections that the frame writes."""
    if frame.get("architecture") is not None:
        sections = decode_sections(frame["architecture"])
        names = document_sections(frame["architecture"])
    else:
        sections = frame.get("sections") or {}
        names = set(sections)
    rows = {name: to_rows(sections[name]) for name in SECTIONS if name in sections}
    return rows, names


def selection_of(sections: str | None, families: str | None) -> Selection:
    """The owned sections and rule kinds. An unknown name is an error: a typo selects nothing."""
    chosen = SECTIONS if not sections else () if sections == NONE else tuple(sections.split(","))
    if unknown := sorted(set(chosen) - set(SECTIONS)):
        raise ValueError(f"unknown sections: {', '.join(unknown)}")
    if not families:
        return Selection(chosen, None)
    if families == NONE:
        return Selection(chosen, frozenset())
    names = families.split(",")
    if unknown := sorted(name for name in names if name not in FAMILIES and name not in RULE_KINDS):
        raise ValueError(f"unknown families or rule kinds: {', '.join(unknown)}")
    return Selection(chosen, frozenset(k for name in names for k in FAMILIES.get(name, (name,))))
