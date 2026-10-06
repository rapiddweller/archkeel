# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run both TypeScript collectors on an already cloned repository and compare their shares.

Nothing is cloned or installed here. The comparison is the corpus differential's own: the same
request, the same classification, so the numbers are comparable with the acceptance report.
"""

from __future__ import annotations

import argparse
import time
from collections import Counter
from pathlib import Path

from fixtures.typescript_differential import (
    FRONTEND,
    ORACLE,
    Summary,
    collect,
    compare,
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
    summaries = []
    for label, argv_ in (("oracle  ", ORACLE), ("frontend", FRONTEND)):
        started = time.monotonic()
        summaries.append(summarize(collect(argv_, request), str(root)))
        print(_share(label, summaries[-1], time.monotonic() - started))
    findings = compare(*summaries)
    classes = Counter(item.klass for item in findings if item.subject != "gap reasons")
    print("differences by class:", dict(sorted(classes.items())))
    for item in findings:
        if item.klass in ("suspicious", "defect"):
            print(f"  {item.klass}: {item.subject}: {item.old} -> {item.new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
