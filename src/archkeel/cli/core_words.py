# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The user vocabulary: what a machine word means in plain text (AD-432).

The JSON keeps the machine codes. The text names what happened in plain words and never prints an
internal code, an issue or decision number, or a path that the user did not type.
"""

from __future__ import annotations

import re
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
}
#: What to do for a refusal whose message starts with a part of the scan (first match wins).
PART_FIXES: Final = (
    ("config:", "create archkeel.toml (`archkeel init` drafts one) or pass --config PATH."),
    ("root:", "run inside a Git work tree, or pass --root PATH to one."),
    ("contract:", "check `contract` under [scan] in archkeel.toml and that the file exists."),
    ("system:", "check the system document that --config names, and its parts."),
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
        lowered = message.lower()
        for start, fix in PART_FIXES:
            if lowered.startswith(start) or (not start.endswith(":") and start in lowered):
                return fix
    return FIXES.get(kind)


#: Machine words inside a reason of the core, in the words of a reader.
REASON_WORDS: Final = {
    "unresolved_name": "name not resolved",
    "external_type": "type from outside the scan",
    "scope_incomplete": "the scan has gaps",
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
