# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The base-versus-PR gate of the native self-check (AD-1061).

Run: `python tools/self_check_gate.py --result <result.json> --base <ref> --old-exit <N> --uv <uv>
[--report-only] [--no-compare]`. `make self-validate-native` calls it after the pin gate.

It condenses the result into `test-artifacts/selfcheck/result.json`: the result of this commit.
Main CI copies it to `base.json` and saves that file in a cache keyed by the sha. The PR gate
restores the cache to `base.json`, which nothing else writes. The gate reads `base.json` as the
base candidate only when it is for the merge base of `--base` and HEAD. The gate fails when git
tracks a file under `test-artifacts/selfcheck/`: a PR must not bring its own base. A miss computes
the base in a git worktree of that commit (the core of this tree is reused when `native/` is the
same). It never skips: when the base cannot be computed, the gate fails and names the reason. The
label and the PR text for growth come from RATCHET_LABELED (`true`) and RATCHET_BODY_FILE.
`BASE_RESULT=<file>` replaces the base. While the pin gate stays authoritative, a different verdict
of the two gates prints one line `GATE DISAGREEMENT`.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from self_check_diff import Unusable, condense
from self_check_diff import main as diff

KEPT = Path("test-artifacts/selfcheck/result.json")
BASE = Path("test-artifacts/selfcheck/base.json")
BINARIES = ("archkeel-core", "archkeel-rust-collector", "archkeel-typescript-collector")


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if done.returncode != 0:
        raise Unusable(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def compute_base(sha: str, uv: list[str]) -> dict[str, Any]:
    """Run the self-check on a git worktree of `sha`: the result that main CI would have saved."""
    tree = git("rev-parse", f"{sha}:native")
    work = Path(tempfile.mkdtemp(prefix="selfcheck-base-"))
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ARCHKEEL_NATIVE_TREE", "ARCHKEEL_CORE_SOURCE")
    }
    try:
        git("worktree", "add", "--detach", str(work / "tree"), sha)
        wt = work / "tree"
        built = Path("native/target/release")
        reuse = subprocess.run(
            ["git", "diff", "--quiet", sha, "--", "native"]
        ).returncode == 0 and all((built / name).is_file() for name in BINARIES)
        if reuse:
            (wt / built).mkdir(parents=True)
            for name in BINARIES:
                shutil.copy2(built / name, wt / built / name)
        elif subprocess.run(
            ["make", "core"], cwd=wt, env=env, capture_output=True, text=True
        ).returncode:
            raise Unusable("the core of the base commit does not build; run `make core` there")
        run = subprocess.run(
            [
                *uv,
                "run",
                "--locked",
                "archkeel",
                "validate",
                "--config",
                "native/archkeel.toml",
                "--json",
            ],
            cwd=wt,
            env=env,
            capture_output=True,
            text=True,
        )
        try:
            return condense(json.loads(run.stdout), sha, tree)
        except ValueError as error:
            raise Unusable(
                f"the check on the base commit gave no result ({error}): {run.stderr[-300:]}"
            ) from error
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(work / "tree")], capture_output=True
        )
        shutil.rmtree(work, ignore_errors=True)


def base_file(ref: str, own: dict[str, Any], uv: list[str], candidate: str) -> tuple[Path, str]:
    """The file of the base result and the sha that it must be for ('' for BASE_RESULT)."""
    if os.environ.get("BASE_RESULT"):
        return Path(os.environ["BASE_RESULT"]), ""
    sha = git("merge-base", ref, "HEAD")
    out = Path(tempfile.mkdtemp(prefix="selfcheck-")) / "base.json"
    if sha == own["sha"]:
        found = own
    else:
        try:
            found = json.loads(candidate)
            hit = found.get("sha") == sha and found.get("format") == "selfcheck-v1"
        except ValueError:
            hit = False
        if hit:
            print(f"base result: cache hit for {sha[:12]}")
        else:
            print(f"base result: cache miss for {sha[:12]}; computing it in a worktree")
            found = compute_base(sha, uv)
    out.write_text(json.dumps(found), encoding="utf-8")
    return out, sha


def main(argv: list[str]) -> int:
    def option(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv else ""

    old = int(option("--old-exit") or 0)
    candidate = BASE.read_text(encoding="utf-8") if BASE.is_file() else ""
    KEPT.unlink(missing_ok=True)
    try:
        if tracked := git("ls-files", str(KEPT.parent)):
            print(f"FAIL git tracks files under {KEPT.parent}/, a PR must not bring a base:")
            print(tracked)
            return 1
        sha, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD:native")
        own = condense(json.loads(Path(option("--result")).read_text(encoding="utf-8")), sha, tree)
    except (Unusable, OSError, ValueError) as error:
        print(f"FAIL the self-check result is unusable: {error}")
        return 1
    KEPT.parent.mkdir(parents=True, exist_ok=True)
    KEPT.write_text(json.dumps(own), encoding="utf-8")
    if "--no-compare" in argv:
        return old
    try:
        path, wanted = base_file(
            option("--base"), own, shlex.split(option("--uv") or "uv"), candidate
        )
    except Unusable as error:
        print(f"base unavailable: {error}")
        path, wanted = Path("missing-base-result.json"), ""
    labels = "ratchet-lead" if os.environ.get("RATCHET_LABELED") == "true" else ""
    args = [str(path), str(KEPT), "--labels", labels, "--base-sha", wanted]
    args += (
        ["--body-file", os.environ["RATCHET_BODY_FILE"]]
        if os.environ.get("RATCHET_BODY_FILE")
        else []
    )
    new = diff(args)
    if (old == 0) != (new == 0):
        line = f"GATE DISAGREEMENT: the pin gate exits {old}, the base comparison exits {new}"
        print(line)
        if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
            Path(summary).open("a", encoding="utf-8").write(line + "\n")
    return old if "--report-only" in argv else (old or new)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
