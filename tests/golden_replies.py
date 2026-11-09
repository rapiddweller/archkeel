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
import re
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
_ROOT_MARK = "<root>"
# The parts of `facts` outside the sections that the digest counts.
_COUNTED = ("files", "imports", "evidence", "inputs")


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
    roots = {str(root), str(root.resolve())}
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


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def digest(value: dict[str, Any]) -> dict[str, Any]:
    """The hash of the whole reply, of each section and of the rest, with the counts."""
    facts = value["facts"]
    sections = {
        section["name"]: {
            "sha256": _sha(section),
            "records": len(section["records"]),
            "kinds": _kinds(section["records"]),
        }
        for section in facts["sections"]
    }
    rest = {key: item for key, item in facts.items() if key != "sections"}
    return {
        "sha256": _sha(value),
        "claimed": list(facts["capabilities"]["sections"]),
        "sections": sections,
        "rest": {"sha256": _sha(rest), "counts": {k: len(facts[k]) for k in _COUNTED}},
    }


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
        keep.write_text(json.dumps(digest(value), indent=2, sort_keys=True) + "\n")
    return keep


def load(language: str, case: str) -> Golden:
    full, short = paths(language, case)
    if full.exists() and short.exists():
        raise GoldenError(f"{case}: a golden reply has a full file or a digest, never both")
    if full.exists():
        value = json.loads(gzip.decompress(full.read_bytes()))
        return Golden(digest(value), value)
    if short.exists():
        return Golden(json.loads(short.read_text()), None)
    raise GoldenError(f"{case}: no golden reply under tests/golden/{language}; record it first")


@dataclass(frozen=True)
class Verdict:
    compared: tuple[str, ...]
    skipped: tuple[str, ...]
    mismatches: tuple[str, ...]


def compare(golden: Golden, actual: dict[str, Any]) -> Verdict:
    """Compare the canonical reply of a producer with the golden reply.

    A producer that claims fewer sections than the golden reply is compared on the sections that
    it claims. The verdict names each section and field that it did not compare.
    """
    got = digest(actual)
    want = golden.digest
    claimed, recorded = set(got["claimed"]), set(want["claimed"])
    mismatches = [
        f"claims {name}, which the golden reply does not hold" for name in claimed - recorded
    ]
    if claimed == recorded:
        names = tuple(want["sections"])
        skipped: tuple[str, ...] = ()
    else:
        names = tuple(name for name in want["sections"] if name in claimed)
        skipped = (*(n for n in want["sections"] if n not in claimed), "files, imports, evidence")
    for name in names:
        expected, seen = want["sections"][name], got["sections"].get(name)
        if seen is None or seen["sha256"] != expected["sha256"]:
            mismatches.append(_describe(name, expected, seen, golden.full, actual))
    if not skipped and got["rest"] != want["rest"]:
        mismatches.append(_describe("rest", want["rest"], got["rest"], golden.full, actual))
    return Verdict((*names, *(() if skipped else ("rest",))), skipped, tuple(mismatches))


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
        differences(_part(full["facts"], name), _part(actual["facts"], name), name)
    )


def _part(facts: dict[str, Any], name: str) -> Any:
    if name == "rest":
        return {key: item for key, item in facts.items() if key != "sections"}
    return next((s for s in facts["sections"] if s["name"] == name), None)


def differences(want: Any, got: Any, path: str = "reply", limit: int = 5) -> list[str]:
    """The first paths where two JSON values differ."""
    found: list[str] = []

    def walk(a: Any, b: Any, where: str) -> None:
        if len(found) >= limit or a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for key in sorted(set(a) | set(b)):
                walk(a.get(key, "<absent>"), b.get(key, "<absent>"), f"{where}.{key}")
        elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
            for index, (x, y) in enumerate(zip(a, b, strict=True)):
                walk(x, y, f"{where}[{index}]")
        else:
            found.append(f"{where}: {str(a)[:60]!r} != {str(b)[:60]!r}")

    walk(want, got, path)
    return found
