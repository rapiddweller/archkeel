# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The user vocabulary: what a machine word means in plain text (AD-432).

The JSON keeps the machine codes. The text names what happened in plain words and never prints an
internal code, an issue or decision number, or a path that the user did not type.
"""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import Path
from typing import Final

#: Why a rule is UNKNOWN, in the words of a reader.
UNKNOWN_CAUSES: Final = {
    "scope_incomplete": "the scan has gaps, so the rule cannot be proven",
    "no_receipt": "the core has no proof for the rule",
    "undecided": "the core does not decide this kind of rule yet",
    "ownership_blocker": "a module has no single owner",
    "no_decided_rule": "the contract has no rule that the core decides",
}
#: A gap of the collector, in the words of a reader. A kind that is not here is spelled out.
GAP_KINDS: Final = {
    "source_resolution_gap": "a name or import that the scan cannot resolve",
    "reexport_ambiguity": "a re-export that names more than one target",
    "import_system_change": "code that changes the import system while it runs",
    "dynamic_import": "an import that is computed while the code runs",
    "reflection": "code that reads or writes names while it runs",
    "rule_kind_not_ported": "a rule kind that the core does not decide yet",
    "boundary_type_position": "a type at a declared boundary that cannot be resolved",
    "contract_refused": "the contract file cannot be read",
    "producer_not_verified": "a scan result that the core cannot verify",
    "inside_contract_missing": "a contract file that the tree names and that is missing",
    "decision.open": "an open decision in the contract (a TODO)",
    "responsibility.missing": "a component without a written responsibility",
    "rationale.placeholder": "a rationale that is still a placeholder",
    "graph.drift": "a drawn component graph that differs from the imports",
    "door_reach.declared": "a door whose reach the contract declares (a premise, not a proof)",
    "door_reach.unmatched": "a declared door reach that matches no door of the scan",
    "door_reach.ambiguous": "a declared door reach that matches more than one door",
    "door_reach.repeated": "a door with more than one declared reach",
    "door_reach.invalid": "a declared door reach that cannot apply",
    "door_reach.inside": "a declared door reach in an inside contract",
    "baseline.invalid": "a baseline file that is not valid",
    "baseline.older_schema": "a baseline file from release 4.0.1",
}
#: What to do after a refusal, by the kind of the refusal (the JSON keeps the machine kind).
FIXES: Final = {
    "collection_refused": "read the problem above, correct that file or option, and run again.",
    "request_mismatch": "run again; a file or the Git state changed while the scan ran.",
    "invalid_input": "run `archkeel --help` or `archkeel <command> --help` for the options.",
    "io_error": "check that the path exists and that you may write there.",
    "core_binary_not_found": "install a build of archkeel that includes its core, or build it.",
    "not_on_this_development_line": "use the release named above, or leave this option out.",
    "core_error": "run again; if it repeats, keep the output and report it with the version.",
    "internal_error": "run again with --verbose and report what it prints; it is a fault.",
    "baseline_not_written": "fix the refused part named above, then write the baseline again.",
    "parse_work_limit": (
        "the file is larger or deeper than the scan reads; split it, or leave it out of the scan "
        "roots."
    ),
}


class _RefusedPart(StrEnum):
    """Each part of the scan that the collector refuses by name (`native/collect/src`, AD-735).

    A collector refusal reads `<part>: <reason>` once the machine prefix is removed. A test reads
    the Rust sources, so that each part that can reach the user is here.
    """

    BUILD = "build"
    COLLECTOR = "collector"
    CONFIG = "config"
    CONTRACT = "contract"
    DIRTY = "dirty"
    GIT_HEAD = "git head"
    PARSE_WORK = "parse work"
    PROFILE = "profile"
    REQUEST = "request"
    ROOT = "root"
    SCAN = "scan"
    SYSTEM = "system"
    WORK_BUDGET = "work budget"


def _refused_part(message: str) -> _RefusedPart | None:
    """The part that a collector refusal names before its first colon, or `None`."""
    head, colon, _ = message.partition(":")
    try:
        return _RefusedPart(head.strip().lower()) if colon else None
    except ValueError:
        return None


#: What to do for a refusal of a part of the scan.
PART_FIXES: Final = {
    _RefusedPart.CONFIG: "create archkeel.toml (`archkeel init` drafts one) or pass --config PATH.",
    _RefusedPart.ROOT: "run inside a Git work tree, or pass --root PATH to one.",
    _RefusedPart.CONTRACT: (
        "check `contract` under [scan] in archkeel.toml and that the file exists."
    ),
    _RefusedPart.SYSTEM: "check the system document that --config names, and its parts.",
}
#: What to do for a refusal whose message names a cause of the file system (first match wins).
CAUSE_WORD_FIXES: Final = (
    ("file or folder not found", "check the path and run again."),
    ("permission denied", "check the permissions of that path, or pass another path."),
)
#: A finding of the core and what to write to remove it (printed once for each cause).
CAUSE_FIXES: Final = {
    "module has no unique owner": (
        "add the package to the `packages` of one component in the contract; a root package "
        "such as `backend/__init__.py` needs that too, or a component of its own."
    ),
}
_OS_ERRORS: Final = (
    (re.compile(r"\s*\(os error \d+\)"), ""),
    (re.compile(r"\[Errno \d+\]\s*"), ""),
    (re.compile(r"No such file or directory", re.I), "file or folder not found"),
    (re.compile(r"Permission denied", re.I), "permission denied"),
    (re.compile(r"Is a directory", re.I), "it is a folder"),
    (re.compile(r"Not a directory", re.I), "a part of the path is not a folder"),
)


def fix_for(kind: str, message: str) -> str | None:
    """What to do after a refusal: a refused scan by the part its message names, else by kind."""
    if kind == "collection_refused":
        if (part := _refused_part(message)) in PART_FIXES:
            return PART_FIXES[part]
        lowered = message.lower()
        for words, fix in CAUSE_WORD_FIXES:
            if words in lowered:
                return fix
    return FIXES.get(kind)


#: Machine words inside a reason of the core, in the words of a reader.
REASON_WORDS: Final = {
    "unresolved_name": "name not resolved",
    "external_type": "type from outside the scan",
    "scope_incomplete": "the scan has gaps",
    # AD-802 (#1523): the remedy of a late class annotation, in the words of a Python project.
    "lazy_class_namespace": "lazy class annotation",
    "narrow the version range of the project, make the annotations strings": (
        "narrow requires-python below 3.14, add `from __future__ import annotations`"
    ),
}
_NOT_FOUND: Final = re.compile(r"project_module_not_found: (\S+)")
NOT_FOUND_PREFIX: Final = "project_module_not_found: "
_HYGIENE: Final = re.compile(r"contract hygiene [a-z_.]+: ")
_NUMBERS: Final = re.compile(r"\s*\((?:#|AD-)\d+(?:[^)]*)\)|\bAD-\d+\b|\s#\d+\b")
_PREFIXES: Final = ("collect: unsupported: ", "unsupported: ")


_REQUIRES: Final = '{"component": "model", "rationale": "why this part uses the other"}'
_SCHEMA: Final = "schema/architecture-contract.schema.json"
_JSON_AT: Final = re.compile(r"line (\d+) column (\d+)")
_SHAPES: Final = re.compile(r"^(?P<path>\S+) must be (?P<what>.+)$")


def contract_fix(message: str) -> str:
    """What to write in a contract file to remove the error that the core named (display only)."""
    if message.startswith("invalid JSON"):
        place = _JSON_AT.search(message)
        at = f" at line {place[1]}, column {place[2]}" if place else ""
        return f"fix the JSON syntax{at}; every key is a quoted text, and commas separate entries."
    shape = _SHAPES.match(message)
    if shape and re.search(r"requires\[\d+\]$", shape["path"]):
        return f"write {shape['what']} there, for example {_REQUIRES}."
    if shape:
        return f"write {shape['what']} at {shape['path']}; the fields are in {_SCHEMA}."
    if message.endswith("fields mismatch") or message.endswith("is missing"):
        return f"give that object exactly the fields that {_SCHEMA} lists, no other."
    return f"correct that part of the contract; its form is in {_SCHEMA}."


_ESCAPE: Final = re.compile(r"_x([0-9a-f]{1,6})_")


def readable(text: str) -> str:
    """A module identity with its real characters (#1617): the collector writes a character of a
    TypeScript path segment that is no ASCII letter or digit as `_x<hex>_`. Only such an escape is
    read back; the JSON keeps the identity."""

    def back(found: re.Match[str]) -> str:
        code = int(found[1], 16)
        char = chr(code) if code <= 0x10FFFF else ""
        return char if char.isprintable() and not (char.isascii() and char.isalnum()) else found[0]

    return _ESCAPE.sub(back, text)


def kind_label(kind: str) -> str:
    """A gap or cause kind as words: the plain label, or the kind with spaces for dots and bars."""
    return GAP_KINDS.get(kind) or UNKNOWN_CAUSES.get(kind) or re.sub(r"[_.]+", " ", kind)


def plain(text: str, typed_root: Path | None = None, resolved_root: Path | None = None) -> str:
    """A message for a user: no issue or decision number, no machine prefix, the path as typed."""
    for prefix in _PREFIXES:
        text = text.replace(prefix, "")
    for pattern, words in _OS_ERRORS:
        text = pattern.sub(words, text)
    text = _HYGIENE.sub("", _NUMBERS.sub("", text)).strip()
    text = _NOT_FOUND.sub(r"imported module \1 has no file in the scan", text)
    for word, words in REASON_WORDS.items():
        text = re.sub(rf"\b{word}\b", words, text)
    if typed_root is not None and resolved_root is not None:
        text = text.replace(str(resolved_root), str(typed_root))
    return text
