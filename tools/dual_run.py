# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Dual run (AD-360): compare a second engine with the recorded result of the Python engine.

`record` runs the Python engine on each case of the corpus and writes one oracle per case to
`tests/dual_run/`. `compare` runs a candidate engine on the same cases and compares its result
with the oracle: the verdict map of the owned rule families (L1) and the canonical rows of the
owned sections of architecture.json (L2). A difference names the case, the section or `rules`,
the row id and the first differing row. The candidate is the Python engine in process, or a
command that reads a request on standard input and writes an engine frame (see `--help`).
"""

from __future__ import annotations

import argparse
import fnmatch
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator, Mapping
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from tools.dual_run_oracle import (
    ORACLE_DIR,
    SECTIONS,
    Difference,
    Selection,
    base_oracle,
    compare_case,
    decode_sections,
    oracle_section,
    owned_rules,
    read_oracle,
    section_rows,
    selection_of,
    write_oracle,
)

REPOSITORY = Path(__file__).resolve().parent.parent
BENCH_DIR = REPOSITORY / "test-artifacts" / "dual-run" / "bench"
PROTOCOL = "archkeel-dual-run-1"


@dataclass(frozen=True, slots=True)
class Case:
    """One project of the corpus: a fixture tree, its scan configuration and an overlay."""

    id: str
    fixture: str
    config: str = "archkeel.toml"
    baseline: str | None = None
    base_files: dict[str, str | None] = field(default_factory=dict)
    files: dict[str, str | None] = field(default_factory=dict)
    bench: bool = False


# --- Corpus ----------------------------------------------------------------------------------


def corpus_cases() -> list[Case]:
    """Every fixture with a scan configuration, every report variant of the demo catalog and
    every golden case root that is not a fixture. The oracle keeps each case's overlay."""
    catalog = importlib.import_module("fixtures.architecture_demo").CATALOG

    cases: list[Case] = []
    fixture_roots: set[str] = set()
    for directory in sorted((REPOSITORY / "fixtures").iterdir()):
        if (directory / "archkeel.toml").is_file():
            fixture_roots.add(f"fixtures/{directory.name}")
            cases.append(Case(f"fixture/{directory.name}", f"fixtures/{directory.name}"))
    for variant in catalog:
        if variant.evidence or variant.check or variant.view or variant.explore:
            continue
        against = variant.against
        if against is not None and against.root != ".":
            continue
        cases.append(
            Case(
                f"demo/{variant.id}",
                str(variant.fixture.resolve().relative_to(REPOSITORY)),
                variant.config,
                variant.baseline,
                dict(against.base_files) if against is not None else {},
                dict(variant.files),
            )
        )
    for language in ("python", "typescript"):
        for entry in json.loads((REPOSITORY / f"tests/golden/{language}/cases.json").read_text()):
            root = entry["root"]
            if root in fixture_roots or not (REPOSITORY / root / "archkeel.toml").is_file():
                continue
            fixture_roots.add(root)
            cases.append(Case(f"golden/{language}-{Path(root).name}", root))
    return cases


def bench_case(value: str) -> Case:
    """`NAME=PATH[:CONFIG]` of a local bench project; its oracle is never committed."""
    name, _, location = value.partition("=")
    path, _, config = location.partition(":")
    return Case(
        f"bench/{name}",
        str(Path(path).expanduser().resolve()),
        config or "archkeel.toml",
        bench=True,
    )


def oracle_path(case: Case) -> Path:
    base = BENCH_DIR if case.bench else ORACLE_DIR
    return base / f"{case.id.replace('/', '--')}.json.gz"


def _apply(root: Path, files: Mapping[str, str | None]) -> None:
    for relative, content in files.items():
        target = root / relative
        if content is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


@contextmanager
def materialized(case: Case) -> Iterator[Path]:
    """The fixture in a new Git repository: base files committed, then the overlay applied."""
    source = Path(case.fixture) if case.bench else REPOSITORY / case.fixture
    if case.bench:
        yield source
        return
    with tempfile.TemporaryDirectory(prefix="archkeel-dual-") as temporary:
        root = Path(temporary) / source.name
        shutil.copytree(source, root, ignore=shutil.ignore_patterns(".dart_tool", "build"))
        modules = (root / "resolver-inputs").is_dir()
        if modules:
            shutil.copytree(root / "resolver-inputs", root / "node_modules")
        _apply(root, case.base_files)
        git = ["git", "-c", "user.email=dual@example.invalid", "-c", "user.name=Dual"]
        git += ["-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]
        # A fixed date gives the same commit, so a binding to the source identity is stable.
        date = "2026-01-01T00:00:00+00:00"
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
        subprocess.run([*git, "init", "-q", "-b", "main"], cwd=root, check=True)
        subprocess.run([*git, "add", "-A"], cwd=root, check=True)
        if modules:
            subprocess.run([*git, "add", "--force", "node_modules"], cwd=root, check=True)
        subprocess.run([*git, "commit", "-q", "-m", case.id], cwd=root, check=True, env=env)
        _apply(root, case.files)
        yield root


# --- Engines ---------------------------------------------------------------------------------


def engine_request(case: Case, root: Path, selection: Selection) -> dict[str, Any]:
    """The request of a command engine (AD-360). `reply` stays `null` until the core ingests a
    collector reply; until then the engine reads the sources below `root`."""
    contract = tomllib.loads((root / case.config).read_text()).get("contract")
    contracts = {} if contract is None else {contract: (root / contract).read_text()}
    return {
        "protocol": PROTOCOL,
        "case": case.id,
        "root": str(root),
        "config": case.config,
        "baseline": case.baseline,
        "contracts": contracts,
        "reply": None,
        "sections": list(selection.sections),
    }


def run_engine(case: Case, root: Path, command: str | None, selection: Selection) -> dict[str, Any]:
    if command is None:
        from tools.dual_run_python import run_python_engine

        return run_python_engine(root, case.config, case.baseline and str(root / case.baseline))
    request = json.dumps(engine_request(case, root, selection))
    done = subprocess.run(
        command, shell=True, input=request, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(f"{case.id}: engine exit {done.returncode}: {done.stderr[-2000:]}")
    frame: dict[str, Any] = json.loads(done.stdout)
    return frame


def base_of(case: Case) -> str | None:
    """A demo variant is stored as a delta to the oracle of its fixture."""
    if not case.id.startswith("demo/"):
        return None
    base = f"fixture/{Path(case.fixture).name}"
    return base if (ORACLE_DIR / f"{base.replace('/', '--')}.json.gz").is_file() else None


def record_case(case: Case) -> str:
    with materialized(case) as root:
        frame = run_engine(case, root, None, Selection())
    base = base_of(case)
    sections: dict[str, Any] | None = None
    if frame["architecture"] is not None:
        rows = decode_sections(frame["architecture"])
        sections = {}
        for name in SECTIONS:
            pair = None
            if base is not None and base_oracle(base)["sections"] is not None:
                base_entry = base_oracle(base)["sections"][name]
                pair = (base, base_entry["digest"], section_rows(base_oracle(base), name))
            sections[name] = oracle_section(name, rows[name], pair)
    oracle = {
        "format": 1,
        "case": asdict(case) if not case.bench else {"id": case.id},
        "rules": frame["rules"],
        "sections": sections,
    }
    write_oracle(oracle_path(case), oracle)
    return case.id


def compare_one(job: tuple[Case, str | None, Selection]) -> tuple[Case, int, list[Difference]]:
    case, command, selection = job
    oracle = read_oracle(oracle_path(case))
    with materialized(case) as root:
        frame = run_engine(case, root, command, selection)
    owned = owned_rules(oracle["rules"], selection.kinds)
    return case, len(owned), compare_case(oracle, frame, selection)


def _pool(jobs: int) -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=jobs)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("action", choices=("record", "compare", "serve-python", "list"))
    parser.add_argument("--case", action="append", help="Glob of case ids; repeat to add.")
    parser.add_argument(
        "--bench", action="append", default=[], help="NAME=PATH[:CONFIG], local only."
    )
    parser.add_argument("--sections", help="Comma list of owned sections. Default: all.")
    parser.add_argument(
        "--families", help="Comma list of owned families or rule kinds. Default: all."
    )
    parser.add_argument("--engine-command", help="Candidate command; default: the Python engine.")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 4)
    args = parser.parse_args(argv)
    if args.action == "serve-python":
        return serve_python()
    cases = [*corpus_cases(), *map(bench_case, args.bench)]
    if args.case:
        cases = [c for c in cases if any(fnmatch.fnmatchcase(c.id, p) for p in args.case)]
    if args.action == "list":
        print("\n".join(case.id for case in cases))
        return 0
    started = time.perf_counter()
    if args.action == "record":
        # The fixtures first: a demo variant is a delta to the oracle of its fixture.
        bases = [case for case in cases if case.id.startswith("fixture/")]
        with _pool(args.jobs) as pool:
            recorded = list(pool.map(record_case, bases))
            recorded += pool.map(record_case, [case for case in cases if case not in bases])
        print(f"recorded {len(recorded)} oracles in {time.perf_counter() - started:.1f} s")
        return 0
    selection = selection_of(args.sections, args.families)
    missing = [case.id for case in cases if not oracle_path(case).is_file()]
    if missing:
        print(f"no oracle for {len(missing)} cases, first {missing[0]}: run `make dual-run-record`")
        return 2
    # The largest oracles first, so that no large case starts last.
    cases.sort(key=lambda case: -oracle_path(case).stat().st_size)
    with _pool(args.jobs) as pool:
        results = list(
            pool.map(compare_one, [(case, args.engine_command, selection) for case in cases])
        )
    return report(results, selection, time.perf_counter() - started)


def report(
    results: list[tuple[Case, int, list[Difference]]], selection: Selection, seconds: float
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
    print(
        f"dual run: family {family}; {len(selection.sections)} sections; {len(results)} projects; "
        f"{rules} rules; {total} differences; {seconds:.1f} s"
    )
    return 1 if total else 0


def serve_python() -> int:
    """The command interface served by the Python engine: request on stdin, frame on stdout."""
    request = json.load(sys.stdin)
    if request.get("protocol") != PROTOCOL:
        print(f"unknown protocol {request.get('protocol')}", file=sys.stderr)
        return 2
    from tools.dual_run_python import run_python_engine

    root = Path(request["root"])
    baseline = request["baseline"] and str(root / request["baseline"])
    json.dump(run_python_engine(root, request["config"], baseline), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
