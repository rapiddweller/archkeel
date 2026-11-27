# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the steps of the PR gate one by one and report all failures at the end (AD-756).

`make pr-gate` stops at the first failure, so an author who has four problems needs four runs.
`make pr-precheck` runs only the cheap static checks (under 30 s); `make pr-gate-report` runs every
step of the gate, cheap ones first, and prints one summary table with the first lines of each
failure and the fix hint. The CI gate stays fail-fast (AD-674: at most 3 minutes).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

UV = ("uv", "run", "--locked")
PYTEST = (*UV, "python", "-m", "pytest", "-q", "-p", "no:cacheprovider", "-n", "0")
CHEAP = "cheap"
HEAVY = "heavy"
LINES = 6


@dataclass(frozen=True, slots=True)
class Step:
    name: str
    command: tuple[str, ...]
    hint: str
    kind: str = CHEAP


@dataclass(frozen=True, slots=True)
class Result:
    step: Step
    code: int
    seconds: float
    output: str


def steps(base: str) -> list[Step]:
    """The steps in order: the cheap static checks first, then the gate steps that take minutes."""
    return [
        Step(
            "format",
            (*UV, "ruff", "format", "--check", "src", "tests", "tools"),
            "run `uv run ruff format` on the files named",
        ),
        Step(
            "lint",
            (*UV, "ruff", "check", "src", "tests", "tools"),
            "fix each finding; never add a blanket ignore",
        ),
        Step(
            "rust-api-baseline",
            (*UV, "python", "tools/rust_api.py", "--check"),
            "a public Rust name changed: run `python tools/rust_api.py`, review api_baseline.json",
        ),
        Step(
            "contract-sort-and-rules",
            (*PYTEST, "tests/test_native_contract_rules.py"),
            "sort the ports, the public lists and the rules of native/architecture-contract.json",
        ),
        Step(
            "hygiene",
            (*PYTEST, "tests/test_repository_hygiene.py"),
            "fix the finding of the repository hygiene test: read its message",
        ),
        Step(
            "rust-format",
            ("cargo", "fmt", "--manifest-path", "native/Cargo.toml", "--all", "--", "--check"),
            "run `cd native && cargo fmt --all`",
        ),
        Step(
            "rust-api",
            (*PYTEST, "tests/test_rust_api.py"),
            "the public Rust API changed: update native/api_baseline.json with the tool",
        ),
        Step("types", ("make", "typecheck"), "fix the mypy findings", HEAVY),
        Step(
            "self-validate",
            ("make", "self-validate"),
            "the architecture of the Python source breaks a rule: read the named rule",
            HEAVY,
        ),
        Step(
            "native-lint",
            ("make", "pr-native-lint", f"PR_BASE={base}"),
            "clippy `-D warnings` for the touched crates, then the API gate",
            HEAVY,
        ),
        Step(
            "selected-tests",
            ("make", "pr-selected-test", f"PR_BASE={base}"),
            "the fast tests of the areas that the change touches",
            HEAVY,
        ),
    ]


def first_lines(output: str) -> list[str]:
    """The lines of a failure that say what is wrong: error lines first, else the tail."""
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    marked = [line for line in lines if line.lstrip().startswith(("E ", "error", "FAILED", "-->"))]
    return (marked or lines[-LINES:])[:LINES]


def run_step(step: Step, runner: Callable[[Sequence[str]], tuple[int, str]]) -> Result:
    started = time.monotonic()
    code, output = runner(step.command)
    return Result(step, code, time.monotonic() - started, output)


def shell(command: Sequence[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        return 127, str(error)
    return done.returncode, done.stdout + done.stderr


def summary(results: Sequence[Result]) -> str:
    """One table, then the failures with their first lines and fix hints."""
    rows = ["step | result | seconds", "--- | --- | ---"]
    for item in results:
        verdict = "pass" if item.code == 0 else "FAIL"
        rows.append(f"{item.step.name} | {verdict} | {item.seconds:.1f}")
    failed = [item for item in results if item.code != 0]
    out = [*rows, ""]
    for item in failed:
        out.append(f"FAIL {item.step.name} (exit {item.code})")
        out.extend(f"    {line}" for line in first_lines(item.output))
        out.append(f"    fix: {item.step.hint}")
        out.append("")
    total = f"{len(failed)} of {len(results)} steps failed" if failed else "all steps passed"
    return "\n".join([*out, total])


def main(
    argv: Sequence[str] | None = None,
    runner: Callable[[Sequence[str]], tuple[int, str]] = shell,
) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["precheck", "report"], default="report")
    parser.add_argument("--base", default="origin/main")
    args = parser.parse_args(argv)
    chosen = [s for s in steps(args.base) if args.mode == "report" or s.kind == CHEAP]
    results: list[Result] = []
    for step in chosen:
        print(f"running {step.name} ...", file=sys.stderr, flush=True)
        results.append(run_step(step, runner))
    print(summary(results))
    return 1 if any(item.code for item in results) else 0


if __name__ == "__main__":
    sys.exit(main())
