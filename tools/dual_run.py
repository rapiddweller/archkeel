# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dual run (AD-360): compare a second engine with the recorded result of the Python engine.

`record --reason TEXT` runs the Python engine on each case of the corpus, prints the differences
to the old oracles and writes one oracle per case to `tests/dual_run/`. `compare` runs a candidate
engine on the same cases and compares its result with the oracle: the verdict map of the owned
rule families (L1) and the canonical rows of the owned sections of architecture.json (L2). A
difference names the case, the section or `rules`, the row id and the first differing row. The
candidate is the Python engine in process, or a command that reads a request on standard input
and writes an engine frame (`--engine-command`).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any

from tools.dual_run_corpus import (
    REPOSITORY,
    Case,
    bench_case,
    corpus_cases,
    ensure_commits,
    materialized,
    oracle_path,
    supported_cases,
)
from tools.dual_run_oracle import (
    ORACLE_DIR,
    SECTIONS,
    Difference,
    Selection,
    base_oracle,
    compare_case,
    decode_sections,
    first_difference,
    oracle_file,
    oracle_section,
    owned_rules,
    read_oracle,
    section_rows,
    selection_of,
    to_rows,
    unexplained,
    write_oracle,
)
from tools.dual_run_tree import tree_frame

RECORDINGS = ORACLE_DIR / "RECORDINGS.md"
# Version 2 adds the settings of the shell: `namespace`, `profile` and `standard_library` (AD-372).
# Version 3 adds `insides`: the inside contracts that the shell read for the core (AD-379).
# Version 5 removes `pinned`: the core takes no trust statement from a request (AD-388). The pin
# of a case stays a fact of the Python engine run (`Case.pinned`).
# Version 4 adds `roots`: the scan roots of the configuration; the core binds them to the reply
# (AD-384).
PROTOCOL = "archkeel-dual-run-5"
ENGINE_TIMEOUT_SECONDS = 600
# The exit code of an engine frame that names an unsupported or refused part (AD-363).
NAMES_A_GAP = 3
# The paths whose change can change an oracle; `record` refuses them uncommitted.
RECORDED_SOURCES = ("src", "fixtures", "native", "tests/golden", "tests/false_pass_support.py")
RUST_COLLECTOR_VARIABLE = "ARCHKEEL_DUAL_RUN_RUST_COLLECTOR"
# The variable that names the Rust collector for a `rust` probe of `false_pass_support.py`.
PROBE_RUST_COLLECTOR = "ARCHKEEL_PROBE_RUST_COLLECTOR"


# --- Engines ---------------------------------------------------------------------------------


def rust_collector() -> str:
    default = REPOSITORY / "native/target/debug/archkeel-rust-collector"
    return os.environ.get(RUST_COLLECTOR_VARIABLE) or str(default)


def collector_argv(case: Case) -> tuple[str, ...] | None:
    if case.collector_argv is None:
        return None
    values = {"{python}": sys.executable, "{repository}": str(REPOSITORY)}
    values["{rust_collector}"] = rust_collector()
    return tuple(
        values.get(item, item.replace("{repository}", str(REPOSITORY)))
        for item in case.collector_argv
    )


def engine_request(case: Case, root: Path, selection: Selection) -> dict[str, Any]:
    """The request of a command engine (AD-360). `reply` stays `null` until the core ingests a
    collector reply; until then the engine reads the sources below `root`. The shell reads the
    namespace and the roots from the configuration (AD-372, AD-384): the core parses no
    configuration file."""
    scan = tomllib.loads((root / case.config).read_text())["scan"]
    contract = scan.get("contract")
    contracts = {} if contract is None else {contract: (root / contract).read_text()}
    return {
        "protocol": PROTOCOL,
        "case": case.id,
        "root": str(root),
        "config": case.config,
        "baseline": case.baseline,
        "contracts": contracts,
        "collector_argv": collector_argv(case),
        "reply": None,
        "sections": list(selection.sections),
        "namespace": scan["namespace"],
        "profile": "",
        "standard_library": [],
        "insides": [],
        "roots": [PurePosixPath(root).as_posix() for root in scan["roots"]],
    }


def python_frame(
    root: Path, request: Mapping[str, Any], pinned: bool, replies: list[bytes] | None = None
) -> dict[str, Any]:
    """The frame of the Python engine; `replies` gets the raw collector replies of the run. The
    Python engine trusts a pinned external collector (AD-344); the core never does (AD-388)."""
    from tools.dual_run_python import run_python_engine

    os.environ[PROBE_RUST_COLLECTOR] = rust_collector()
    baseline = request["baseline"] and str(root / request["baseline"])
    argv = request["collector_argv"]
    return run_python_engine(
        root,
        request["config"],
        baseline,
        argv and tuple(argv),
        pinned,
        rust_collector(),
        replies,
    )


def run_engine(
    case: Case,
    root: Path,
    command: str | None,
    selection: Selection,
    timeout: float = ENGINE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """The engine frame. A failed, slow or unreadable engine gives a frame with `error`."""
    return engine_and_reference(case, root, command, selection, timeout)[0]


def engine_and_reference(
    case: Case,
    root: Path,
    command: str | None,
    selection: Selection,
    timeout: float = ENGINE_TIMEOUT_SECONDS,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """The engine frame, and the frame of the Python engine that ran the collector for a
    command engine (`None` for the Python engine itself)."""
    request = engine_request(case, root, selection)
    if command is None:
        return python_frame(root, request, case.pinned), None
    # The shell runs the collector and sends its reply: the engine reads no file (AD-363).
    replies: list[bytes] = []
    reference = python_frame(root, request, case.pinned, replies)
    request["reply"] = {"hex": replies[-1].hex()} if replies else None
    from tools.dual_run_python import reply_profile

    request["profile"], request["standard_library"] = (
        reply_profile(replies[-1]) if replies else ("", [])
    )
    # AD-379: the core asks for the inside contracts that it needs; the shell reads them.
    frame = tree_frame(lambda sent: command_frame(command, sent, timeout), request, root)
    return frame, reference


def command_frame(command: str, request: Mapping[str, Any], timeout: float) -> dict[str, Any]:
    """The frame of a command engine for a request."""
    try:
        done = subprocess.run(
            command,
            shell=True,
            input=json.dumps(request),
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"error": f"the engine did not answer in {timeout:g} s"}
    if done.returncode not in (0, NAMES_A_GAP):
        return {"error": f"the engine exits with {done.returncode}: {done.stderr[-2000:]}"}
    try:
        frame: dict[str, Any] = json.loads(done.stdout)
    except ValueError as error:
        return {"error": f"the engine frame is not JSON: {error}"}
    # Exit 3 goes only with a frame that names its unsupported parts, and exit 0 only without:
    # an empty frame is never a plain success (AD-363).
    if (done.returncode == NAMES_A_GAP) != names_a_gap(frame):
        return {"error": f"the engine exits with {done.returncode} for this frame"}
    if (problem := unexplained(frame)) is not None:
        return {"error": f"the engine frame is inconsistent: {problem}"}
    return frame


def reference_edges(reference: Mapping[str, Any]) -> list[dict[str, Any]] | None:
    """The `dependency_edges` rows of the Python engine, or `None` without architecture.json."""
    architecture = reference.get("architecture")
    return None if architecture is None else decode_sections(architecture)["dependency_edges"]


def edge_differences(
    case: str, rows: list[dict[str, Any]] | None, frame: Mapping[str, Any]
) -> list[Difference]:
    """The first difference of the full `dependency_edges` rows of the engine, ranks included,
    to the rows of the Python engine on the same reply (AD-372, AD-374). The oracle keeps only
    the key fields of a large section, so this compares each field of each row. An engine that
    refuses the reply has no edges: its refusal is already a named difference."""
    actual = (frame.get("sections") or {}).get("dependency_edges")
    if actual is None:
        refused = "files" not in ((frame.get("self_test") or {}).get("reply") or {})
        if frame.get("error") or rows is None or refused:
            return []
        return [Difference(case, "edges", "-", "the engine writes no edge rows")]
    found = first_difference(case, "edges", to_rows(rows or []), to_rows(actual))
    return [] if found is None else [found]


def names_a_gap(frame: Mapping[str, Any]) -> bool:
    """True when the frame names an unsupported part or a refused input."""
    unsupported = frame.get("unsupported") or {}
    found = frame.get("self_test") or {}
    refused = bool(found) and (
        "rules" not in found.get("contract", {}) or "files" not in found.get("reply", {})
    )
    return refused or any(unsupported.get(part) for part in ("rules", "sections", "report"))


# --- Record ----------------------------------------------------------------------------------


def base_of(case: Case, directory: Path) -> str | None:
    """A demo variant is stored as a delta to the oracle of its fixture."""
    if not case.id.startswith("demo/"):
        return None
    base = f"fixture/{Path(case.fixture).name}"
    return base if oracle_file(directory, base).is_file() else None


def oracle_of(case: Case, frame: Mapping[str, Any], directory: Path) -> dict[str, Any]:
    if frame.get("error"):
        raise RuntimeError(f"{case.id}: {frame['error']}")
    base = base_of(case, directory)
    sections: dict[str, Any] | None = None
    if frame["architecture"] is not None:
        rows = decode_sections(frame["architecture"])
        sections = {}
        for name in SECTIONS:
            pair = None
            if base is not None and base_oracle(base, directory)["sections"] is not None:
                base_entry = base_oracle(base, directory)["sections"][name]
                pair = (
                    base,
                    base_entry["digest"],
                    section_rows(base_oracle(base, directory), name, directory),
                )
            sections[name] = oracle_section(rows[name], pair)
    return {
        "format": 2,
        "case": asdict(case) if not case.bench else {"id": case.id},
        "rules": frame["rules"],
        "sections": sections,
    }


def record_case(job: tuple[Case, Path, Path]) -> list[Difference]:
    """Record one oracle into `output`. The differences to the oracle in `previous` (a copy of
    the old oracles) are returned, so that `record` shows what it overwrites."""
    case, previous, output = job
    with materialized(case) as root:
        frame = run_engine(case, root, None, Selection())
    oracle = oracle_of(case, frame, output)
    old = oracle_file(previous, case.id)
    if case.bench:
        old = oracle_path(case)
    differences = [Difference(case.id, "oracle", "-", "a new case")]
    if old.is_file():
        old_oracle = read_oracle(old)
        try:
            differences = compare_case(old_oracle, frame, Selection(), previous)
        except (KeyError, RuntimeError, IndexError, TypeError) as error:
            differences = [
                Difference(case.id, "oracle", "-", f"the old oracle is unreadable: {error}")
            ]
    write_oracle(oracle_path(case) if case.bench else oracle_file(output, case.id), oracle)
    return differences


def dirty_sources() -> list[str]:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *RECORDED_SOURCES],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return [line[3:] for line in status.splitlines()]


def record(cases: list[Case], reason: str, jobs: int, allow_dirty: bool) -> int:
    if not reason.strip():
        print("record needs --reason: say why the Python result changes")
        return 2
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=REPOSITORY,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if changed := dirty_sources():
        if not allow_dirty:
            print(f"the source is not committed: {changed[:5]}. Commit it, or use --allow-dirty")
            return 2
        commit += "+dirty"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="archkeel-dual-old-") as temporary:
        previous = Path(temporary)
        for path in ORACLE_DIR.glob("*.json.gz"):
            shutil.copy2(path, previous / path.name)
        # The fixtures first: a demo variant is a delta to the oracle of its fixture.
        bases = [case for case in cases if case.id.startswith("fixture/")]
        rest = [case for case in cases if case not in bases]
        with ProcessPoolExecutor(max_workers=jobs) as pool:
            found = list(pool.map(record_case, [(c, previous, ORACLE_DIR) for c in bases]))
            found += pool.map(record_case, [(c, previous, ORACLE_DIR) for c in rest])
    differences = [d for items in found for d in items]
    for difference in differences:
        print(f"overwritten: {difference.line()}")
    today = datetime.now(UTC).date()
    line = f"| {today} | {len(cases)} | {commit} | {reason.strip()} |\n"
    head = "# Dual-run recordings\n\n| Date | Cases | Commit | Reason |\n|---|---|---|---|\n"
    if not any(case.bench for case in cases):
        RECORDINGS.write_text((RECORDINGS.read_text() if RECORDINGS.exists() else head) + line)
    seconds = time.perf_counter() - started
    print(f"recorded {len(cases)} oracles, {len(differences)} differences, {seconds:.1f} s")
    return 0


# --- Compare ---------------------------------------------------------------------------------


def compare_one(
    job: tuple[Case, str | None, Selection, float],
) -> tuple[Case, int, list[Difference]]:
    case, command, selection, timeout = job
    oracle = read_oracle(oracle_path(case))
    with materialized(case) as root:
        frame, reference = engine_and_reference(case, root, command, selection, timeout)
    owned = owned_rules(oracle["rules"], selection.kinds)
    differences = compare_case(oracle, frame, selection)
    # AD-378, L-35b: a core status PASS or FAIL must be the run status of the Python engine.
    if reference is not None and frame.get("status") in ("PASS", "FAIL"):
        if frame["status"] != reference.get("declared_rules"):
            found = f"core {frame['status']}, Python {reference.get('declared_rules')}"
            differences.append(Difference(case.id, "status", "-", found))
    # AD-372, AD-374: the full edge rows are compared with the Python engine on every case.
    if reference is not None and "dependency_edges" in selection.sections:
        differences += edge_differences(case.id, reference_edges(reference), frame)
    return case, len(owned), differences


def chosen_cases(patterns: list[str] | None, bench: list[str]) -> list[Case]:
    """The cases that the globs select. A glob that selects no case is an error."""
    cases = [*corpus_cases(), *map(bench_case, bench)]
    if not patterns:
        return cases
    if unknown := [p for p in patterns if not any(fnmatch.fnmatchcase(c.id, p) for c in cases)]:
        raise ValueError(f"no case matches {', '.join(unknown)}")
    return [c for c in cases if any(fnmatch.fnmatchcase(c.id, p) for p in patterns)]


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=("record", "compare", "serve-python", "list"))
    parser.add_argument("--case", action="append", help="Glob of case ids; repeat to add.")
    parser.add_argument("--bench", action="append", default=[], help="NAME=PATH[:CONFIG].")
    parser.add_argument("--sections", help="Comma list of owned sections. Default: all.")
    parser.add_argument("--families", help="Comma list of families or rule kinds. Default: all.")
    parser.add_argument("--engine-command", help="Candidate command; default: the Python engine.")
    parser.add_argument("--engine-timeout", type=float, default=ENGINE_TIMEOUT_SECONDS)
    parser.add_argument("--reason", default="", help="record: why the Python result changes.")
    parser.add_argument("--allow-dirty", action="store_true", help="record: log +dirty.")
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--self-test", action="store_true", help="Compare what the engine read (AD-363)."
    )
    args = parser.parse_args(argv)
    if args.action == "serve-python":
        return serve_python()
    try:
        cases = chosen_cases(args.case, args.bench)
        selection = selection_of(args.sections, args.families)
        if args.self_test:
            # The wiring check owns nothing unless the slice names what it owns.
            selection = selection_of(args.sections or "none", args.families or "none")
            selection = Selection(selection.sections, selection.kinds, self_test=True)
    except ValueError as error:
        print(error)
        return 2
    if not cases:
        print("the run selects 0 projects")
        return 2
    if selection.owns_nothing() and not selection.self_test:
        print("the run selects nothing: name the owned sections or families, or --self-test")
        return 2
    if args.action == "list":
        print("\n".join(case.id for case in cases))
        return 0
    ensure_commits(cases)
    cases, skipped = supported_cases(cases)
    if not cases:
        print(f"dual run: 0 supported projects; {skipped} skipped; no comparison")
        return 2
    if args.action == "record":
        return record(cases, args.reason, args.jobs, args.allow_dirty)
    if missing := [case.id for case in cases if not oracle_path(case).is_file()]:
        print(f"no oracle for {len(missing)} cases, first {missing[0]}: run `make dual-run-record`")
        return 2
    ensure_commits(cases)
    started = time.perf_counter()
    # The largest oracles first, so that no large case starts last.
    cases.sort(key=lambda case: -oracle_path(case).stat().st_size)
    jobs = [(case, args.engine_command, selection, args.engine_timeout) for case in cases]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(compare_one, jobs))
    return report(results, selection, args.engine_command, time.perf_counter() - started, skipped)


def report(
    results: list[tuple[Case, int, list[Difference]]],
    selection: Selection,
    command: str | None,
    seconds: float,
    skipped: int = 0,
) -> int:
    """One line per difference; a bench case shows only counts (a private project)."""
    differences = [d for case, _, found in results if not case.bench for d in found]
    for difference in differences:
        print(difference.line())
    bench = [found for case, _, found in results if case.bench]
    if bench:
        print(f"bench: {len(bench)} projects, {sum(map(len, bench))} differences")
    family = "all" if selection.kinds is None else ",".join(sorted(selection.kinds)) or "none"
    scope = "self-test" if selection.self_test else f"family {family}"
    rules = sum(count for _, count, _ in results)
    total = len(differences) + sum(map(len, bench))
    print(f"engine: {command or 'the Python engine in process'}")
    print(
        f"dual run: {scope}; {len(selection.sections)} sections; {len(results)} projects; "
        f"{rules} rules; {total} differences; {skipped} skipped; {seconds:.1f} s"
    )
    if not selection.sections and rules == 0 and not selection.self_test:
        print("the run compares nothing: 0 owned rules and 0 sections")
        return 2
    if selection.kinds and rules == 0:
        print("the families select 0 rules in these projects")
        return 2
    return 1 if total else 0


def serve_python() -> int:
    """The command interface served by the Python engine: request on stdin, frame on stdout."""
    request = json.load(sys.stdin)
    if request.get("protocol") != PROTOCOL:
        print(f"unknown protocol {request.get('protocol')}", file=sys.stderr)
        return 2
    pinned = any(case.pinned for case in corpus_cases() if case.id == request["case"])
    json.dump(python_frame(Path(request["root"]), request, pinned), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
