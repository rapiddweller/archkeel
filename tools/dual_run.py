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
from pathlib import Path
from typing import Any

from tools.dual_run_corpus import (
    REPOSITORY,
    Case,
    bench_case,
    corpus_cases,
    materialized,
    oracle_path,
)
from tools.dual_run_oracle import (
    ORACLE_DIR,
    SECTIONS,
    Difference,
    Selection,
    base_oracle,
    compare_case,
    decode_sections,
    oracle_file,
    oracle_section,
    owned_rules,
    read_oracle,
    section_rows,
    selection_of,
    write_oracle,
)

RECORDINGS = ORACLE_DIR / "RECORDINGS.md"
PROTOCOL = "archkeel-dual-run-1"
ENGINE_TIMEOUT_SECONDS = 600
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
    collector reply; until then the engine reads the sources below `root`."""
    contract = tomllib.loads((root / case.config).read_text())["scan"].get("contract")
    contracts = {} if contract is None else {contract: (root / contract).read_text()}
    return {
        "protocol": PROTOCOL,
        "case": case.id,
        "root": str(root),
        "config": case.config,
        "baseline": case.baseline,
        "contracts": contracts,
        "collector_argv": collector_argv(case),
        "pinned": case.pinned,
        "reply": None,
        "sections": list(selection.sections),
    }


def python_frame(root: Path, request: Mapping[str, Any]) -> dict[str, Any]:
    from tools.dual_run_python import run_python_engine

    os.environ[PROBE_RUST_COLLECTOR] = rust_collector()
    baseline = request["baseline"] and str(root / request["baseline"])
    argv = request["collector_argv"]
    return run_python_engine(
        root, request["config"], baseline, argv and tuple(argv), request["pinned"], rust_collector()
    )


def run_engine(
    case: Case,
    root: Path,
    command: str | None,
    selection: Selection,
    timeout: float = ENGINE_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """The engine frame. A failed, slow or unreadable engine gives a frame with `error`."""
    request = engine_request(case, root, selection)
    if command is None:
        return python_frame(root, request)
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
    if done.returncode != 0:
        return {"error": f"the engine exits with {done.returncode}: {done.stderr[-2000:]}"}
    try:
        frame: dict[str, Any] = json.loads(done.stdout)
    except ValueError as error:
        return {"error": f"the engine frame is not JSON: {error}"}
    return frame


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
        frame = run_engine(case, root, command, selection, timeout)
    owned = owned_rules(oracle["rules"], selection.kinds)
    return case, len(owned), compare_case(oracle, frame, selection)


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
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args(argv)
    if args.action == "serve-python":
        return serve_python()
    try:
        cases = chosen_cases(args.case, args.bench)
        selection = selection_of(args.sections, args.families)
    except ValueError as error:
        print(error)
        return 2
    if not cases:
        print("the run selects 0 projects")
        return 2
    if args.action == "list":
        print("\n".join(case.id for case in cases))
        return 0
    if args.action == "record":
        return record(cases, args.reason, args.jobs, args.allow_dirty)
    if missing := [case.id for case in cases if not oracle_path(case).is_file()]:
        print(f"no oracle for {len(missing)} cases, first {missing[0]}: run `make dual-run-record`")
        return 2
    started = time.perf_counter()
    # The largest oracles first, so that no large case starts last.
    cases.sort(key=lambda case: -oracle_path(case).stat().st_size)
    jobs = [(case, args.engine_command, selection, args.engine_timeout) for case in cases]
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        results = list(pool.map(compare_one, jobs))
    return report(results, selection, args.engine_command, time.perf_counter() - started)


def report(
    results: list[tuple[Case, int, list[Difference]]],
    selection: Selection,
    command: str | None,
    seconds: float,
) -> int:
    """One line per difference; a bench case shows only counts (a private project)."""
    differences = [d for case, _, found in results if not case.bench for d in found]
    for difference in differences:
        print(difference.line())
    bench = [found for case, _, found in results if case.bench]
    if bench:
        print(f"bench: {len(bench)} projects, {sum(map(len, bench))} differences")
    family = "all" if selection.kinds is None else ",".join(sorted(selection.kinds))
    rules = sum(count for _, count, _ in results)
    total = len(differences) + sum(map(len, bench))
    print(f"engine: {command or 'the Python engine in process'}")
    print(
        f"dual run: family {family}; {len(selection.sections)} sections; {len(results)} projects; "
        f"{rules} rules; {total} differences; {seconds:.1f} s"
    )
    if selection.kinds is not None and rules == 0:
        print("the families select 0 rules in these projects")
        return 2
    return 1 if total else 0


def serve_python() -> int:
    """The command interface served by the Python engine: request on stdin, frame on stdout."""
    request = json.load(sys.stdin)
    if request.get("protocol") != PROTOCOL:
        print(f"unknown protocol {request.get('protocol')}", file=sys.stderr)
        return 2
    json.dump(python_frame(Path(request["root"]), request), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
