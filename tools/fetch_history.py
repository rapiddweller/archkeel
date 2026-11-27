# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Fetch the history that a PR job reads after a checkout of depth 1, or fail (AD-1222).

`python tools/fetch_history.py <base-sha>` fetches `main`, the base commit and the checked-out
commit without blobs and without tags, with a growing depth. It stops when the base commit is an
ancestor of `HEAD`. Then the merge base of the two is the base commit, exactly: a missing edge of a
shallow history can only hide an ancestor, never invent one. When no depth shows the ancestry, it
fetches the whole commit graph, so the merge base is exact. A base that has no merge base with
`HEAD` or with `origin/main` fails with exit 1: the gate would read a wrong base.

A shallow merge base with `origin/main` can be older than the true one. A diff from it only holds
more paths, never fewer, so the selection of areas and the new-file check stay safe.
"""

from __future__ import annotations

import subprocess
import sys

# 20 commits hold the 8 first-parent ancestors that the base-result reuse reads (`pr-gate.yml`).
DEPTHS: tuple[int | None, ...] = (20, 100, 500, None)
MAIN = "+refs/heads/main:refs/remotes/origin/main"


def git(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *arguments], capture_output=True, text=True, check=False)


def shallow() -> bool:
    return git("rev-parse", "--is-shallow-repository").stdout.strip() == "true"


def related(ref: str) -> bool:
    return git("merge-base", ref, "HEAD").returncode == 0


def settled(base: str) -> bool:
    """True when the merge base with `base` is exact and `origin/main` has one with `HEAD`."""
    exact = not shallow() or git("merge-base", "--is-ancestor", base, "HEAD").returncode == 0
    return exact and related(base) and related("origin/main")


def fetch(base: str, depth: int | None) -> None:
    head = git("rev-parse", "HEAD").stdout.strip()
    # A complete clone has nothing to deepen: the fetch only brings the refs.
    mode = (
        []
        if depth is None and not shallow()
        else ["--unshallow" if depth is None else f"--depth={depth}"]
    )
    done = git("fetch", "--no-tags", "--filter=blob:none", *mode, "origin", MAIN, base, head)
    if done.returncode != 0:
        sys.exit(f"fetch_history: git fetch failed ({' '.join(mode)}):\n{done.stderr.strip()}")


def main(argv: list[str], depths: tuple[int | None, ...] = DEPTHS) -> int:
    if len(argv) != 1 or len(argv[0]) != 40:
        print("usage: fetch_history.py <full base sha>", file=sys.stderr)
        return 2
    base = argv[0]
    for depth in depths:
        fetch(base, depth)
        if settled(base):
            print(f"fetch_history: merge base found ({'whole graph' if depth is None else depth})")
            return 0
    print(
        f"fetch_history: no exact merge base of HEAD with {base} and origin/main. "
        "The job would use a wrong base. Deepen the fetch or run the job again.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
