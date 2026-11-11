# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""False-PASS probes (#880): crafted collector replies that the host must not turn into a PASS.

Consumer: `test_false_pass_probes_*.py`. A probe is a collector process for `[scan].collector_argv`.
It runs the real collector of the language, changes the reply in one way, and sends it. The host
then reads the changed reply like the reply of any external producer.

Run as a script: `false_pass_support.py <language> <tamper> [<argument>]`.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

Reply = dict[str, Any]
Tamper = Callable[[Reply, str], None]

SCRIPT = Path(__file__).resolve()
# A file path that no snapshot holds.
OUTSIDE = "../outside/ghost.ts"
GHOST = "src/not_in_the_snapshot.ts"
# A compressed reply starts with the zlib header byte; plain JSON never does.
ZLIB_HEADER = b"x"
# The environment variable that names the Rust collector binary for the `rust` probes.
RUST_COLLECTOR = "ARCHKEEL_PROBE_RUST_COLLECTOR"


def _section(reply: Reply, name: str) -> list[dict[str, Any]]:
    facts = reply["facts"]
    for section in facts["sections"]:
        if section["name"] == name:
            return section["records"]
    raise KeyError(name)


def drop_file_records(reply: Reply, _argument: str) -> None:
    """Remove each import record of one file, and keep the file in `files`."""
    evidence = {item["id"]: item["file"] for item in reply["facts"]["evidence"]}
    imports = _section(reply, "imports")
    first = evidence[imports[0]["evidence_ids"][0]]
    imports[:] = [
        record
        for record in imports
        if not any(evidence.get(ident) == first for ident in record["evidence_ids"])
    ]


def drop_file(reply: Reply, _argument: str) -> None:
    """Remove one file from `files`, and keep its records."""
    reply["facts"]["files"].pop()


def empty_section(reply: Reply, argument: str) -> None:
    """Empty one section and keep it claimed in `capabilities`."""
    _section(reply, argument or "imports").clear()
    if not argument or argument == "imports":
        reply["facts"]["imports"].clear()


def no_evidence(reply: Reply, _argument: str) -> None:
    """Remove the evidence ids of every import record."""
    for record in _section(reply, "imports"):
        record["evidence_ids"] = []


def evidence_outside(reply: Reply, argument: str) -> None:
    """Point the evidence of every import record at a file that the snapshot does not hold."""
    for item in reply["facts"]["evidence"]:
        item["file"] = argument or OUTSIDE


def duplicate_id(reply: Reply, _argument: str) -> None:
    """Send the first import record twice."""
    records = _section(reply, "imports")
    records.append(copy.deepcopy(records[0]))


def unsupported_claim(reply: Reply, argument: str) -> None:
    """Claim a section that the profile of the language marks as never produced."""
    reply["facts"]["sections"].append({"name": argument, "records": []})
    reply["facts"]["capabilities"]["sections"].append(argument)


def honest(_reply: Reply, _argument: str) -> None:
    """Change nothing: the reply of an external producer that is correct."""


TAMPERS: dict[str, Tamper] = {
    "drop-file-records": drop_file_records,
    "drop-file": drop_file,
    "empty-section": empty_section,
    "no-evidence": no_evidence,
    "evidence-outside": evidence_outside,
    "duplicate-id": duplicate_id,
    "unsupported-claim": unsupported_claim,
    "honest": honest,
}


def _reply(language: str) -> tuple[Reply, bool]:
    """The reply of the real collector, and whether its protocol compresses it (8.0.0, 9.0.0)."""
    from archkeel.ir.facts_codec import decode_request, encode_response
    from archkeel.ir.protocol import CollectionResponse

    payload = sys.stdin.buffer.read()
    if language == "rust":
        # The Rust collector is a binary: the test names its path (`RUST_COLLECTOR`).
        answer = subprocess.run(
            [os.environ[RUST_COLLECTOR]], input=payload, capture_output=True, check=True
        ).stdout
        compressed = answer[:1] == ZLIB_HEADER
        return json.loads(zlib.decompress(answer) if compressed else answer), compressed
    request = decode_request(payload)
    if language == "typescript":
        from archkeel.analyzer.typescript.collect import collect
    else:
        from archkeel.analyzer.python.collect import collect
    payload = encode_response(CollectionResponse(collect(request), request.protocol_version))
    compressed = payload[:1] == ZLIB_HEADER
    return json.loads(zlib.decompress(payload) if compressed else payload), compressed


def send(reply: Reply, compressed: bool) -> None:
    """Write the changed reply in the framing of the requested protocol."""
    text = json.dumps(reply).encode()
    sys.stdout.buffer.write(zlib.compress(text, 1) if compressed else text)


def main(argv: list[str]) -> None:
    language, tamper, *rest = argv
    reply, compressed = _reply(language)
    TAMPERS[tamper](reply, rest[0] if rest else "")
    send(reply, compressed)


def argv_for(language: str, tamper: str, argument: str = "") -> tuple[str, ...]:
    return (
        sys.executable,
        "-I",
        "-B",
        str(SCRIPT),
        language,
        tamper,
        *([argument] if argument else []),
    )


def copy_repository(source: Path, workspace: Path) -> Path:
    root = workspace / "repo"
    shutil.copytree(source, root, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    if (root / "resolver-inputs").is_dir():
        shutil.copytree(root / "resolver-inputs", root / "node_modules")
    from graph_report_support import commit_tree  # not in the collector process (python -I)

    commit_tree(root)
    if (root / "node_modules").is_dir():
        # A global ignore rule can hide `node_modules`; the resolver reads it from the snapshot.
        for args in (["add", "--force", "node_modules"], ["commit", "-q", "--amend", "--no-edit"]):
            subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True)
    return root


def verdict(
    root: Path, language: str, argv: tuple[str, ...] | None, *, pinned: bool = False
) -> dict[str, Any]:
    """The status of each rule, the completeness and the exit code of `run_report`.

    An unpinned `argv` is an external producer: the host caps it at UNKNOWN (AD-344). A pinned
    probe is a producer that the host trusts, so the check of its reply is what the test reads.
    """
    from collector_pin import pin_of

    from archkeel.check.report import run_report
    from archkeel.cli.config import load_config
    from archkeel.cli.observe import observer_for

    config = load_config(root)
    observer = observer_for(
        config.language,
        collector_argv=argv,
        tsconfig=config.tsconfig or "tsconfig.json",
        pinned_digest=pin_of(argv[0]) if pinned and argv else None,
    )
    result, _ = run_report(root, config=config, analyzer=observer)
    return {
        "rules": {item.id: str(item.status) for item in result.rule_assessments or ()},
        "kinds": {item.id: str(item.kind) for item in result.rule_assessments or ()},
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(str(item.kind.value) for item in result.diagnostics),
    }


CLOSED_BY_INVARIANT = (
    "closed by the in-collector invariant of the native collectors (4.3a-5 for TypeScript, "
    "#1003 for Rust) and by protocol 10 for the wire"
)


# Probe -> the reason that the host still gives PASS, or "" when it must not.
COMMON = {
    "drop-file-records": "",
    "drop-file": "",
    "no-evidence": "",
    "evidence-outside": "",
    "evidence-outside:/etc/passwd": "",
    "duplicate-id": "",
    # An honest reply of an unpinned producer gives no PASS: the host caps it (AD-344).
    "honest": "",
}
TYPESCRIPT = {
    **COMMON,
    "empty-section": CLOSED_BY_INVARIANT,
    "empty-section:symbols": "",
    "empty-section:bindings": "",
    # The profile of TypeScript never produces `typing_signals` (`absent_sections`).
    "unsupported-claim:typing_signals": "",
}
RUST = {
    **COMMON,
    # A tampered reply of a pinned producer gives PASS on both decode paths (AD-346); the honest
    # collector cannot drop an import silently (`unextracted`).
    "empty-section": CLOSED_BY_INVARIANT,
    # The profile of Rust never produces `typing_signals` (`absent_sections`).
    "unsupported-claim:typing_signals": "",
}
PYTHON = {
    **COMMON,
    "empty-section": "",
    "empty-section:symbols": "",
    "unsupported-claim:not_a_section": "",
}


def passing(result: dict[str, Any]) -> list[str]:
    return sorted(rule for rule, status in result["rules"].items() if status == "PASS")


def assert_not_pass(
    root: Path,
    language: str,
    tamper: str,
    argument: str = "",
    base_argv: tuple[str, ...] | None = None,
) -> None:
    """The probe fails when the host gives a PASS to the changed reply.

    The unchanged reply of the real collector must give a PASS first, so the probe is never empty.
    `base_argv` names that collector when it is not the bundled one; the base then pins it.
    """
    base = verdict(root, language, base_argv, pinned=base_argv is not None)
    assert base["complete"] == "PASS" and passing(base), "the unchanged scan must pass"
    # The honest probe is the external producer. Every other probe is a pinned producer.
    result = verdict(
        root, language, argv_for(language, tamper, argument), pinned=tamper != "honest"
    )
    assert result["complete"] != "PASS", (tamper, result["diagnostics"])
    assert result["exit"] != 0, (tamper, result["diagnostics"])
    assert not passing(result), (tamper, passing(result))


# No TypeScript rule reads `calls`, `references` or `constructs` today (profiles.py: they are
# optional sections, and the rules on them are unsupported). Emptying one must not change the
# verdict. The day a rule reads one, the probe fails and the rule needs a real probe.
UNREAD_SECTIONS = ("calls", "references", "constructs")


def assert_unchanged(root: Path, language: str, section: str) -> None:
    base = verdict(root, language, None)
    result = verdict(root, language, argv_for(language, "empty-section", section), pinned=True)
    assert passing(base), "the unchanged scan must pass"
    assert (result["rules"], result["complete"], result["exit"]) == (
        base["rules"],
        base["complete"],
        base["exit"],
    ), section


def probe_params(probes: dict[str, str]) -> list[Any]:
    """Pytest parameters: a probe that names a reason is a strict xfail until the host closes it."""
    import pytest

    params = []
    for name, reason in probes.items():
        tamper, _, argument = name.partition(":")
        marks = (
            [pytest.mark.xfail(strict=True, raises=AssertionError, reason=reason)] if reason else []
        )
        params.append(pytest.param(tamper, argument, id=name, marks=marks))
    return params


if __name__ == "__main__":
    main(sys.argv[1:])
