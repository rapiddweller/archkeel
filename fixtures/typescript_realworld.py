# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Measure the in-package TypeScript collector on an already cloned repository.

Nothing is cloned or installed here.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from fixtures.typescript_differential import (
    FRONTEND,
    Summary,
    collect,
    request_for,
    summarize,
)

_RESOLVED = ("LocalTarget", "ExternalPackageTarget", "BuiltinTarget")


def _share(label: str, summary: Summary, seconds: float) -> str:
    kinds = Counter(edge.kind for edge in summary.edges.values())
    total = sum(kinds.values())
    resolved = sum(kinds[kind] for kind in _RESOLVED)
    percent = 100 * resolved / total if total else 0.0
    return (
        f"{label}: {seconds:.1f}s, {len(summary.files)} files, {total} import edges, "
        f"{resolved} resolved ({percent:.1f}%), {kinds['UnresolvedTarget']} unresolved, "
        f"{len(summary.reasons)} distinct gap reasons, full_scope={summary.complete}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path)
    parser.add_argument("--roots", default="src", help="comma-separated source roots")
    parser.add_argument("--namespace", default="repo")
    parser.add_argument("--tsconfig", default="tsconfig.json")
    args = parser.parse_args(argv)
    root = args.repository.resolve()
    request = request_for(root, tuple(args.roots.split(",")), args.namespace, args.tsconfig)
    started = time.monotonic()
    summary = summarize(collect(FRONTEND, request), str(root))
    print(_share("frontend", summary, time.monotonic() - started))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
