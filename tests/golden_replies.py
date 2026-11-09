# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Golden replies of a source collector (AD-343): the canonical form, the storage and the compare.

A golden reply is the reply of a collector, frozen before its Python code is deleted. The test
compares a producer (the Python collector now, the native binary later) with it. The module does
not depend on a language: a reply is a JSON value with `facts.sections`.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import platform
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

GOLDEN = Path(__file__).parent / "golden"

# A reply is stored in full when its gzip form is at most this many bytes. A larger reply is stored
# as a digest with counts. The limit keeps the whole golden set small for the CI budget (AD-343).
FULL_REPLY_LIMIT = 64 * 1024

# The fields of a reply that describe the run and not the source. The canonical form drops them.
# Each field is a path of keys with the reason that the path changes without a change of the facts.
PROVENANCE: dict[tuple[str, ...], str] = {
    ("protocol_version",): "the framing of the reply, not a fact",
    ("facts", "adapter", "code_digest"): "the digest of the code of the producer",
    ("facts", "adapter", "version"): "the version of the package of the producer",
    ("facts", "runtime"): "the interpreter or binary that ran the producer",
    ("facts", "source", "git_head"): "an echo of the request",
    ("facts", "source", "dirty"): "an echo of the request",
}
# A key like these in a reply means a run id or a timing: the recorder fails and names the key.
_VOLATILE_KEY = re.compile(r"run_id|elapsed|duration|timestamp|_seconds$|_ms$", re.IGNORECASE)
# The recorder and the test name the phase and the mode with these variables. A phase gives nothing
# alone: the table `allowances.json` of the language must hold it (AD-343).
PHASE_VARIABLE = "ARCHKEEL_GOLDEN_PHASE"
GATE_VARIABLE = "ARCHKEEL_GOLDEN_GATE"
GATE_DELETE = "delete"
PIN_FILE = "interpreter.json"
_ROOT_MARK = "<root>"
# The lists of `facts` outside the sections that the digest always counts.
_COUNTED = (
    "files",
    "imports",
    "evidence",
    "inputs",
    "type_shapes",
    "uncertain_reexports",
    "candidate_evidence",
)


class GoldenError(Exception):
    """A reply cannot be a golden reply, or a golden file is not valid."""


def canonical(reply: dict[str, Any], root: Path) -> dict[str, Any]:
    """The reply without provenance. A path under `root` becomes `<root>`."""
    value = json.loads(json.dumps(reply))
    for path in PROVENANCE:
        holder = value
        for key in path[:-1]:
            holder = holder.get(key, {})
        holder.pop(path[-1], None)
    # A real reply holds no absolute path today. The replacement guards a future field, and it
    # covers the native and the POSIX spelling of the root.
    roots = {str(root), str(root.resolve()), root.as_posix(), root.resolve().as_posix()}
    return _scrub(value, roots, "reply")


def _scrub(value: Any, roots: set[str], where: str) -> Any:
    if isinstance(value, dict):
        for key in value:
            if _VOLATILE_KEY.search(key):
                raise GoldenError(f"{where}.{key}: a run id or a timing is not a golden field")
        return {key: _scrub(item, roots, f"{where}.{key}") for key, item in value.items()}
    if isinstance(value, list):
        return [_scrub(item, roots, where) for item in value]
    if isinstance(value, str):
        for root in sorted(roots, key=len, reverse=True):
            value = value.replace(root, _ROOT_MARK)
    return value


@dataclass(frozen=True)
class Pin:
    """The parts of a reply that depend on the interpreter that ran the collector (AD-343).

    `tests/golden/<language>/interpreter.json` holds it. `recorded` names the interpreter of the
    recording. `sections`, `facts` and `top` name the parts that another interpreter changes: a
    section, a key of `facts` and a key beside `facts`.
    """

    recorded: dict[str, Any]
    sections: tuple[str, ...]
    facts: tuple[str, ...]
    top: tuple[str, ...]
    reason: str


def interpreter() -> dict[str, Any]:
    """The interpreter that runs the test: its kind, its version and the size of its built-ins."""
    return {
        "implementation": sys.implementation.name,
        "version": platform.python_version(),
        "builtin_modules": len(sys.builtin_module_names),
    }


def pin_for(language: str) -> Pin | None:
    path = GOLDEN / language / PIN_FILE
    if not path.exists():
        return None
    table = json.loads(path.read_text())
    bound = table["bound"]
    return Pin(
        table["recorded_with"],
        tuple(bound["sections"]),
        tuple(bound["facts"]),
        tuple(bound["top"]),
        bound["reason"],
    )


def portable(value: dict[str, Any], pin: Pin) -> dict[str, Any]:
    """The reply without the parts that depend on the interpreter."""
    kept = json.loads(json.dumps(value))
    facts = kept["facts"]
    facts["sections"] = [s for s in facts["sections"] if s["name"] not in pin.sections]
    claimed = facts["capabilities"]["sections"]
    facts["capabilities"]["sections"] = [name for name in claimed if name not in pin.sections]
    for key in pin.facts:
        facts.pop(key, None)
    for key in pin.top:
        kept.pop(key, None)
    return kept


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _rest(facts: dict[str, Any]) -> dict[str, Any]:
    """`facts` without its sections. Protocol 4.0.0 and later write `provider_bindings`, an empty
    list for a TypeScript scan, and the replies of 3.0.0 do not have the key. The golden replies
    were recorded at 3.0.0 and the native collector answers with 8.0.0 or 9.0.0, so an empty list
    is the same as no key."""
    rest = {key: item for key, item in facts.items() if key != "sections"}
    if rest.get("provider_bindings") == []:
        del rest["provider_bindings"]
    return rest


def _beside(reply: dict[str, Any]) -> dict[str, Any]:
    """The keys beside `facts`. Like `provider_bindings`, an empty `provider_sources` is no key."""
    return {key: item for key, item in reply.items() if key != "facts" and item != []}


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(value: dict[str, Any], pin: Pin | None = None) -> dict[str, Any]:
    """The hash of the whole reply, of each section and of the rest, with the counts.

    The rest is `facts` without its sections and without `capabilities.sections`, which `claimed`
    and `order` describe. It also holds each key beside `facts`. With a `pin`, the digest of the
    portable reply is part of it.
    """
    facts = value["facts"]
    order = [section["name"] for section in facts["sections"]]
    if duplicates := sorted({name for name in order if order.count(name) > 1}):
        raise GoldenError(f"duplicate section name in a reply: {duplicates}")
    sections = {
        section["name"]: {
            "sha256": _sha(section),
            "records": len(section["records"]),
            "kinds": _kinds(section["records"]),
        }
        for section in facts["sections"]
    }
    rest = _rest(facts)
    rest["capabilities"] = {k: v for k, v in rest["capabilities"].items() if k != "sections"}
    beside = _beside(value)
    counts = {key: len(facts[key]) for key in _COUNTED if key in facts}
    # Any other list that holds records is a counted part too, so that a test can see it.
    for source in (facts, beside):
        counts.update(
            {k: len(v) for k, v in source.items() if k != "sections" and isinstance(v, list) and v}
        )
    result = {
        "sha256": _sha(value),
        "claimed": list(facts["capabilities"]["sections"]),
        "order": order,
        "features": list(facts["capabilities"].get("resolution_features", [])),
        "sections": sections,
        "rest": {"sha256": _sha({**rest, "_beside": beside} if beside else rest), "counts": counts},
    }
    if pin:
        result["portable"] = digest(portable(value, pin))
    return result


def _kinds(records: list[dict[str, Any]]) -> dict[str, int]:
    kinds: dict[str, int] = {}
    for record in records:
        kind = str(record.get("kind"))
        kinds[kind] = kinds.get(kind, 0) + 1
    return dict(sorted(kinds.items()))


@dataclass(frozen=True)
class Golden:
    digest: dict[str, Any]
    full: dict[str, Any] | None  # the canonical reply, when it is small enough to keep

    def portable(self, pin: Pin) -> Golden:
        """The golden reply without the parts that depend on the interpreter."""
        if self.full is None:
            return Golden(self.digest["portable"], None)
        part = portable(self.full, pin)
        return Golden(digest(part), part)


def paths(language: str, case: str) -> tuple[Path, Path]:
    folder = GOLDEN / language
    return folder / f"{case}.json.gz", folder / f"{case}.digest.json"


def store(language: str, case: str, value: dict[str, Any]) -> Path:
    """Write the full reply when it is small, else the digest. Remove the file of the other form."""
    full, short = paths(language, case)
    packed = gzip.compress(canonical_bytes(value), 9, mtime=0)
    keep, drop = (full, short) if len(packed) <= FULL_REPLY_LIMIT else (short, full)
    drop.unlink(missing_ok=True)
    keep.parent.mkdir(parents=True, exist_ok=True)
    if keep is full:
        keep.write_bytes(packed)
    else:
        pin = pin_for(language)
        keep.write_text(json.dumps(digest(value, pin), indent=2, sort_keys=True) + "\n")
    return keep


def load(language: str, case: str) -> Golden:
    full, short = paths(language, case)
    if full.exists() and short.exists():
        raise GoldenError(f"{case}: a golden reply has a full file or a digest, never both")
    if full.exists():
        value = json.loads(gzip.decompress(full.read_bytes()))
        return Golden(digest(value, pin_for(language)), value)
    if short.exists():
        return Golden(json.loads(short.read_text()), None)
    raise GoldenError(f"{case}: no golden reply under tests/golden/{language}; record it first")


@dataclass(frozen=True)
class Allowance:
    """The sections that a producer may lack in one phase, and why."""

    sections: tuple[str, ...]
    reason: str


def allowance_for(language: str, environ: Mapping[str, str]) -> Allowance | None:
    """The allowance of the phase that `environ` names, or none.

    The deletion gate (`ARCHKEEL_GOLDEN_GATE=delete`) has no allowance. A phase that the table
    `tests/golden/<language>/allowances.json` does not hold is an error.
    """
    mode = environ.get(GATE_VARIABLE)
    if mode not in (None, "", GATE_DELETE):
        raise GoldenError(f"{GATE_VARIABLE} must be empty or {GATE_DELETE!r}, not {mode!r}")
    phase = environ.get(PHASE_VARIABLE)
    if mode == GATE_DELETE or not phase:
        return None
    table = json.loads((GOLDEN / language / "allowances.json").read_text())
    if phase not in table:
        raise GoldenError(f"phase {phase} has no entry in tests/golden/{language}/allowances.json")
    return Allowance(tuple(table[phase]["sections"]), table[phase]["reason"])


@dataclass(frozen=True)
class Verdict:
    compared: tuple[str, ...]
    skipped: tuple[str, ...]
    mismatches: tuple[str, ...]
    reason: str = ""
    # The interpreter differs from the recording: this note names the parts that were not compared.
    unpinned: str = ""


def require_recorded_interpreter(pin: Pin | None, environ: Mapping[str, str]) -> None:
    """The deletion gate needs the interpreter of the recording. A phase can run on another one."""
    if environ.get(GATE_VARIABLE) == GATE_DELETE and pin and pin.recorded != interpreter():
        raise GoldenError(
            f"the deletion gate needs {_name(pin.recorded)} (the interpreter of the recording), "
            f"not {_name(interpreter())}"
        )


def _name(value: Mapping[str, Any]) -> str:
    return f"{value['implementation']} {value['version']} with {value['builtin_modules']} built-ins"


def compare_on_interpreter(
    golden: Golden,
    actual: dict[str, Any],
    allowed: Allowance | None = None,
    pin: Pin | None = None,
) -> Verdict:
    """Compare the whole reply on the interpreter of the recording, else the portable part only."""
    if pin is None or pin.recorded == interpreter():
        return compare(golden, actual, allowed)
    verdict = compare(golden.portable(pin), portable(actual, pin), allowed)
    parts = [*pin.sections, *pin.facts, *pin.top]
    note = (
        f"recorded with {_name(pin.recorded)}, run with {_name(interpreter())}: "
        f"not compared: {parts}. {pin.reason}"
    )
    return Verdict(verdict.compared, verdict.skipped, verdict.mismatches, verdict.reason, note)


def compare(golden: Golden, actual: dict[str, Any], allowed: Allowance | None = None) -> Verdict:
    """Compare the canonical reply of a producer with the golden reply.

    The whole reply must be equal, with its sections in the same order. A section that the
    producer lacks is a mismatch, unless `allowed` names it. Then the verdict lists it as skipped,
    and the rest of the reply (files, evidence, coverage, ...) is still compared.
    """
    got, want = digest(actual), golden.digest
    problems = [
        f"has section {name}, which the golden reply does not hold"
        for name in got["order"]
        if name not in want["order"]
    ]
    missing = [name for name in want["order"] if name not in got["order"]]
    if missing:
        granted = allowed.sections if allowed else ()
        if refused := [name for name in missing if name not in granted]:
            hint = "no allowance for this phase" if not allowed else "not in the allowance"
            problems.append(f"missing sections {refused}: {hint}")
        if set(got["claimed"]) != set(got["order"]):
            problems.append(f"claims {got['claimed']} but holds {got['order']}")
    shared = [name for name in want["order"] if name in got["order"]]
    if [name for name in got["order"] if name in want["order"]] != shared:
        problems.append(f"section order {got['order']} differs from {want['order']}")
    names = tuple(shared)
    for name in names:
        if got["sections"][name]["sha256"] != want["sections"][name]["sha256"]:
            problems.append(
                _describe(name, want["sections"][name], got["sections"][name], golden.full, actual)
            )
    if got["rest"] != want["rest"]:
        problems.append(_describe("rest", want["rest"], got["rest"], golden.full, actual))
    if not missing and not problems and got["sha256"] != want["sha256"]:
        problems.append(
            "the whole reply differs in a field that no part covers (capabilities.sections)"
        )
    skipped = tuple(missing)
    return Verdict(
        (*names, "rest"), skipped, tuple(problems), allowed.reason if allowed and skipped else ""
    )


def _describe(
    name: str, want: dict[str, Any], got: dict[str, Any] | None, full: Any, actual: Any
) -> str:
    if got is None:
        return f"{name}: the reply has no such section"
    head = f"{name}: golden {want.get('records', want.get('counts'))}"
    head += f" records or counts, reply {got.get('records', got.get('counts'))}"
    if full is None:
        return f"{head}; the golden reply is a digest, so there is no field diff"
    return f"{head}; first differences: " + "; ".join(
        differences(_part(full, name), _part(actual, name), name)
    )


def _part(reply: dict[str, Any], name: str) -> Any:
    facts = reply["facts"]
    if name == "rest":
        return {**_rest(facts), **_beside(reply)}
    return next((s for s in facts["sections"] if s["name"] == name), None)


def differences(want: Any, got: Any, path: str = "reply", limit: int = 5) -> list[str]:
    """The first paths where two JSON values differ. A list of other length shows one element."""
    found: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if len(found) >= limit or a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key, "<absent>"), b.get(key, "<absent>"), f"{where}.{key}")
        elif isinstance(a, list) and isinstance(b, list):
            index = next((i for i, (x, y) in enumerate(zip(a, b, strict=False)) if x != y), None)
            if len(a) == len(b) and index is not None:
                walk(a[index], b[index], f"{where}[{index}]")
            elif len(a) != len(b):
                at = min(len(a), len(b)) if index is None else index
                found.append(
                    f"{where}: length {len(a)} != {len(b)}; first differing element [{at}]: "
                    f"{str(a[at] if at < len(a) else '<absent>')[:60]!r} != "
                    f"{str(b[at] if at < len(b) else '<absent>')[:60]!r}"
                )
        else:
            found.append(f"{where}: {str(a)[:60]!r} != {str(b)[:60]!r}")

    walk(want, got, path)
    return found
