# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The base-versus-PR gate of the native self-check (AD-1061, AD-1064).

Run: `python tools/self_check_gate.py --result <result.json> --base <ref> --uv <uv>
[--report-only] [--no-compare]`. `make self-validate-native` calls it.

It condenses the result into `test-artifacts/selfcheck/result.json`: the result of this commit.
Main CI copies it to `base.json` and saves that file in a cache keyed by the sha. The PR gate
restores the cache to `base.json`, which nothing else writes. The gate reads `base.json` as the
base candidate only when it is for the merge base of `--base` and HEAD. The gate fails when git
tracks a file under `test-artifacts/selfcheck/`: a PR must not bring its own base. A miss computes
the base in a git worktree of that commit (the core of this tree is reused when `native/` is the
same). A v1 cached base uses the old comparison during migration. The gate refuses an incomplete
v2 scope or topology.
It never skips: when the base cannot be computed, the gate fails and names the reason. The
label and the PR text for growth come from RATCHET_LABELED (`true`) and RATCHET_BODY_FILE.
`BASE_RESULT=<file>` replaces the base. The base that it compares is kept in `compared-base.json`
for `make self-check`. All grown items go to `grown.txt` in the same directory
and the first ten to `GITHUB_STEP_SUMMARY`. The last line is `self-check gate: GREEN` or
`self-check gate: RED (exit N)`.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path
from typing import Any

from self_check_contract import normalize_contract
from self_check_diff import FORMAT, LABEL, Unusable, condense, load, scanned_scope
from self_check_diff import main as diff

KEPT = Path("test-artifacts/selfcheck/result.json")
GROWN = Path("test-artifacts/selfcheck/grown.txt")
BASE = Path("test-artifacts/selfcheck/base.json")
COMPARED = Path("test-artifacts/selfcheck/compared-base.json")
CONFIG = Path("native/archkeel.toml")
# Everything the saved result of a commit depends on: the scanned tree and its contract and
# config (`native`), the compiler drivers, the Python shell that runs the report, the locked
# tools, the recipe, and the code that condenses the result. A commit that differs from the
# saved one in any of them gets no reuse of that result.
INPUTS = (
    "native",
    "tools/rustc-facts",
    "src",
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    ":(glob)tools/self_check_*.py",
)
# The Rust walk of the scan reads the whole repository for Cargo settings (`registry_overrides.rs`):
# a `.cargo` directory, a link to a directory, a path deeper than its depth limit, or a tree
# larger than its entry limit changes the result wherever it stands. The margins stay below them.
MAX_DEPTH = 100
MAX_FILES = 250_000
FULL_SHA = re.compile(r"[0-9a-f]{40}")
BINARIES = ("archkeel-core", "archkeel-rust-collector", "archkeel-typescript-collector")


def git(*args: str, cwd: Path | None = None) -> str:
    done = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    if done.returncode != 0:
        raise Unusable(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def scan_table(root: Path) -> dict[str, Any] | None:
    """The `[scan]` table of the self-check config under `root`; None when it cannot be read."""
    try:
        found = tomllib.loads((root / CONFIG).read_text(encoding="utf-8")).get("scan")
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def complete_scope(result: dict[str, Any]) -> bool:
    inputs = result.get("contract_files")
    scope = result.get("scope")
    if not isinstance(scope, dict):
        return False
    files, components = scope.get("files"), scope.get("components")
    if not isinstance(files, list) or not isinstance(components, list):
        return False
    frame = {
        "contract_digest": scope.get("contract"),
        "topology": {
            "modules": files,
            "components": components,
            "total": {"modules": len(files), "components": len(components)},
        },
        "self_test": {"reply": {"files": result.get("files")}},
    }
    return (
        scanned_scope(frame) == scope
        and isinstance(inputs, dict)
        and bool(inputs)
        and all(
            isinstance(path, str) and isinstance(digest, str) for path, digest in inputs.items()
        )
    )


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
                "report",
                "--config",
                "native/archkeel.toml",
                "--json",
                "--topology",
            ],
            cwd=wt,
            env=env,
            capture_output=True,
            text=True,
        )
        try:
            result = condense(json.loads(run.stdout), sha, tree, scan_table(wt))
            if not complete_scope(result):
                raise Unusable("the base has no complete scanned scope")
            return result
        except (AttributeError, TypeError, KeyError, IndexError, ValueError) as error:
            raise Unusable(
                f"the check on the base commit gave no result ({error}): {run.stderr[-300:]}"
            ) from error
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(work / "tree")], capture_output=True
        )
        shutil.rmtree(work, ignore_errors=True)


def git_bytes(*args: str) -> list[str]:
    """The NUL-separated fields of a git command; a path need not be UTF-8."""
    done = subprocess.run(["git", *args], capture_output=True)
    if done.returncode != 0:
        raise Unusable(f"git {' '.join(args)} failed: {done.stderr.decode(errors='replace')}")
    return done.stdout.decode("utf-8", errors="surrogateescape").split("\0")


def repository_wide_change(earlier: str, sha: str) -> bool:
    """Whether a change outside INPUTS can change the scan: a `.cargo` path, a link, a deep path."""
    raw = git_bytes("diff", "--raw", "--no-renames", "-z", earlier, sha)
    for meta, path in zip(raw[0::2], raw[1::2], strict=False):
        modes = meta.lstrip(":").split()[:2]
        parts = path.split("/")
        if ".cargo" in parts or "120000" in modes or len(parts) > MAX_DEPTH:
            return True
    return any(
        len(git_bytes("ls-tree", "-r", "-z", "--name-only", rev)) > MAX_FILES
        for rev in (earlier, sha)
    )


def normal_path(text: str) -> bool:
    """The rule of `normal()` in `native/core/src/provenance.rs`: the strings the core may read.

    Mirrored, not shared (the core is Rust). A wider rule here only blocks more reuse.
    """
    return (
        bool(text)
        and not any(char in text for char in "\\:\0")
        and all(part not in ("", ".", "..") for part in text.split("/"))
    )


def path_strings(value: Any) -> set[str]:
    """Every string of a JSON value that the core could read as a cited path."""
    if isinstance(value, str):
        return {value} if normal_path(value) else set()
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else []
    return set().union(*(path_strings(item) for item in items)) if items else set()


def read_paths(found: dict[str, Any], sha: str) -> set[str]:
    """The repository paths that the cached result may have read: the files it bound
    (`contract_files`), and each string of those contracts that the core could read as a cited
    path (`native/core/src/provenance.rs`). A cited file that the core could not read is no bound
    file, so the contract names it here, with any spelling that `normal_path` accepts.
    """
    bound = {path for path in found["contract_files"] if isinstance(path, str)}
    cited = set(bound)
    for path in bound:
        if path.endswith(".json"):
            try:
                cited |= path_strings(json.loads(git("show", f"{sha}:{path}")))
            except (Unusable, ValueError):
                continue
    return cited


def same_paths(earlier: str, sha: str, paths: set[str]) -> bool:
    """Whether each path has the same object, or none, in both commits (a link or a file)."""

    def objects(rev: str) -> dict[str, str]:
        fields = git_bytes("ls-tree", "-r", "-z", rev)
        found = (field.split("\t", 1) for field in fields if "\t" in field)
        return {path: meta for meta, path in found if path in paths}

    return objects(earlier) == objects(sha)


def reuse_of_earlier(found: dict[str, Any], sha: str) -> dict[str, Any] | None:
    """The result of an earlier main commit as the base `sha`, only when no input differs.

    Main CI may not have saved `sha` yet (#2077). The result of an earlier commit stands for it
    when `git diff` shows no change in INPUTS between the two. Else the caller computes the base.
    """
    earlier, tree = found.get("sha"), found.get("tree")
    if not isinstance(earlier, str) or not FULL_SHA.fullmatch(earlier) or earlier == sha:
        return None
    try:
        if git("rev-parse", f"{earlier}:native") != tree:
            return None
    except Unusable:
        return None
    unchanged = subprocess.run(["git", "diff", "--quiet", earlier, sha, "--", *INPUTS])
    if unchanged.returncode != 0 or repository_wide_change(earlier, sha):
        return None
    # The documents that the core read are inputs too: a marked graph or a cited decision.
    try:
        if not same_paths(earlier, sha, read_paths(found, sha)):
            return None
    except Unusable:
        return None
    return {**found, "sha": sha, "tree": git("rev-parse", f"{sha}:native"), "reused_from": earlier}


def align_contract(base: dict[str, Any], own: dict[str, Any]) -> None:
    """Use recorded inputs for both sides when either contract cannot be normalized."""
    if base.get("contract_normalized") != own.get("contract_normalized"):
        normalize_contract(base, Path(), inputs_only=True)
        normalize_contract(own, Path(), inputs_only=True)
        KEPT.write_text(json.dumps(own), encoding="utf-8")


def base_file(ref: str, own: dict[str, Any], uv: list[str], candidate: str) -> tuple[Path, str]:
    """The file of the base result and the sha that it must be for ('' for BASE_RESULT)."""
    if os.environ.get("BASE_RESULT"):
        path = Path(os.environ["BASE_RESULT"])
        try:
            override = load(str(path))
            try:
                revision = override.get("sha") or git("merge-base", ref, "HEAD")
                normalize_contract(override, Path(), revision)
            except Unusable:
                normalize_contract(override, Path(), inputs_only=True)
            align_contract(override, own)
            COMPARED.parent.mkdir(parents=True, exist_ok=True)
            COMPARED.write_text(json.dumps(override), encoding="utf-8")
            return COMPARED, ""
        except (Unusable, OSError):
            return path, ""
    sha = git("merge-base", ref, "HEAD")
    COMPARED.parent.mkdir(parents=True, exist_ok=True)
    out = COMPARED
    if sha == own["sha"]:
        found = own
    else:
        found = None
        try:
            found = json.loads(candidate)
            legacy = (
                isinstance(found, dict)
                and found.get("sha") == sha
                and found.get("format") == "selfcheck-v1"
                and "scope" not in found
            )
            hit = (
                isinstance(found, dict)
                and found.get("sha") == sha
                and found.get("format") == FORMAT
                and complete_scope(found)
            )
        except ValueError:
            hit = legacy = False
        if legacy and isinstance(found, dict):
            message = (
                "scope comparison: base scope not in the v1 cache; "
                "it starts when main writes the v2 cache"
            )
            print(message)
            if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
                with Path(summary).open("a", encoding="utf-8") as output:
                    output.write(f"{message}\n")
            found["scope"] = own["scope"]
            found["contract_files"] = own["contract_files"]
            found["contract_normalized"] = own.get("contract_normalized", False)
            hit = True
        elif (
            isinstance(found, dict) and found.get("format") == FORMAT and not complete_scope(found)
        ):
            raise Unusable("the cached base has no complete scanned scope")
        reused = None
        if not hit and isinstance(found, dict) and found.get("format") == FORMAT:
            reused = reuse_of_earlier(found, sha)
        if reused is not None:
            found = reused
            print(
                f"base result: cache miss for {sha[:12]}; reusing the entry of "
                f"{reused['reused_from'][:12]}: no input differs",
                flush=True,
            )
        elif hit:
            print(f"base result: cache hit for {sha[:12]}", flush=True)
        else:
            print(f"base result: cache miss for {sha[:12]}; computing it in a worktree", flush=True)
            started = time.monotonic()
            try:
                found = compute_base(sha, uv)
            finally:
                print(f"base result: scan took {time.monotonic() - started:.0f} s", flush=True)
    if found is None:
        raise Unusable("the base result is unavailable")
    normalize_contract(found, Path(), sha)
    align_contract(found, own)
    out.write_text(json.dumps(found), encoding="utf-8")
    return out, sha


def gate(argv: list[str]) -> int:
    def option(name: str) -> str:
        return argv[argv.index(name) + 1] if name in argv else ""

    if KEPT.parent.resolve() != Path.cwd().resolve() / KEPT.parent:
        print(f"FAIL {KEPT.parent} is a symlink or lies behind one; the base would be planted")
        return 1
    candidate = BASE.read_text(encoding="utf-8") if BASE.is_file() else ""
    KEPT.unlink(missing_ok=True)
    GROWN.unlink(missing_ok=True)
    try:
        if tracked := git("ls-files", str(KEPT.parent)):
            print(f"FAIL git tracks files under {KEPT.parent}/, a PR must not bring a base:")
            print(tracked)
            return 1
        sha, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD:native")
        saved = json.loads(Path(option("--result")).read_text(encoding="utf-8"))
        own = condense(saved, sha, tree, scan_table(Path()))
        if not own["refusal"] and not complete_scope(own):
            raise Unusable("the result has no complete scanned scope")
        normalize_contract(own, Path())
    except (Unusable, OSError, IndexError, ValueError, TypeError, AttributeError) as error:
        print(f"FAIL the self-check result is unusable: {error}")
        return 1
    KEPT.parent.mkdir(parents=True, exist_ok=True)
    KEPT.write_text(json.dumps(own), encoding="utf-8")
    if own["refusal"]:
        return diff(["alone", str(KEPT)])
    if "--no-compare" in argv:
        return diff(["alone", str(KEPT)])
    try:
        path, wanted = base_file(
            option("--base"), own, shlex.split(option("--uv") or "uv"), candidate
        )
    except Unusable as error:
        print(f"base unavailable: {error}")
        return 1
    labels = LABEL if os.environ.get("RATCHET_LABELED") == "true" else ""
    args = [str(path), str(KEPT), "--labels", labels, "--base-sha", wanted]
    args += [
        "--grown-file",
        str(GROWN),
        "--summary-file",
        os.environ.get("GITHUB_STEP_SUMMARY", ""),
    ]
    args += ["--report-only"] if "--report-only" in argv else []
    if os.environ.get("RATCHET_BODY_FILE"):
        args += ["--body-file", os.environ["RATCHET_BODY_FILE"]]
    return diff(args)


def main(argv: list[str]) -> int:
    code = gate(argv)
    print("self-check gate: GREEN" if code == 0 else f"self-check gate: RED (exit {code})")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
