# ArchKeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run the experimental TypeScript SQLite snapshot command."""

from __future__ import annotations

import json
import sys
from typing import Literal

from archkeel.analyzer.process import ProcessCollector
from archkeel.check.git import GitError, git_bytes
from archkeel.check.onboarding import scan_scope
from archkeel.check.ports import Language
from archkeel.check.snapshot import SnapshotError, resolve_commit
from archkeel.ir.protocol import (
    CollectionRequest,
    SnapshotInput,
    SourceScope,
    TypeScriptSettings,
)

from ..analyzer.typescript.stream import (
    StreamContractEvaluation,
    StreamCoverage,
    StreamSnapshotError,
    page,
)
from .arguments import StreamAction, StreamArguments

_CHILD_TIMEOUT_SECONDS = 300
_CHILD_STDOUT_LIMIT = 64 * 1024


def run_stream(args: StreamArguments) -> int:
    """Dispatch an explicit build or bounded page request. Output is always JSON."""
    if args.stream_action is StreamAction.BUILD:
        result = _build(args)
    else:
        if args.snapshot is None or args.section is None:
            raise ValueError("stream page requires a snapshot and section")
        result = page(
            args.snapshot,
            section=args.section,
            limit=args.limit,
            cursor=args.cursor,
        )
    sys.stdout.write(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n")
    return 0


def _build(args: StreamArguments) -> dict[str, object]:
    if args.root is None or args.output is None:
        raise ValueError("stream build requires --root and --output")
    if not args.source or not args.namespace or not args.tsconfig:
        raise ValueError("stream build requires --source, --namespace, and --tsconfig")
    root = args.root.resolve()
    tsconfig = args.tsconfig
    roots, namespace = scan_scope(
        root,
        source=tuple(args.source),
        namespace=args.namespace,
        language=Language.TYPESCRIPT,
        tsconfig=tsconfig,
    )
    try:
        git_head = resolve_commit(root, "HEAD")
        dirty: bool | Literal["unknown"] = bool(
            git_bytes(root, "status", "--porcelain", "--untracked-files=all")
        )
    except (GitError, SnapshotError):
        git_head, dirty = "unknown", "unknown"
    request = CollectionRequest(
        SnapshotInput(str(root), git_head, dirty),
        SourceScope(roots, namespace),
        TypeScriptSettings(tsconfig, args.bundler),
    )
    output = args.output.resolve()
    command = (
        sys.executable,
        "-I",
        "-B",
        "-m",
        "archkeel.analyzer.typescript.entry",
        "--stream-snapshot",
        str(output),
    )
    child = ProcessCollector(
        command,
        timeout_seconds=_CHILD_TIMEOUT_SECONDS,
        output_limit_bytes=_CHILD_STDOUT_LIMIT,
        stderr_limit_bytes=8 * 1024,
    ).run_control(request)
    if child.error is not None:
        raise StreamSnapshotError(f"TypeScript stream failed: {child.error.message}")
    if child.stdout is None:
        raise StreamSnapshotError("TypeScript stream returned no bounded control response")
    try:
        summary = json.loads(child.stdout)
    except (ValueError, UnicodeDecodeError) as error:
        raise StreamSnapshotError("TypeScript stream returned an invalid summary") from error
    expected_keys = {
        "snapshot_id",
        "coverage",
        "coverage_reason",
        "source_revision",
        "source_digest",
        "contract_identity",
        "selected_file_count",
        "files_read",
        "files_parsed",
        "symbol_count",
        "unknown_count",
        "output",
    }
    if not isinstance(summary, dict) or set(summary) != expected_keys:
        raise StreamSnapshotError("TypeScript stream returned an invalid summary shape")
    try:
        coverage = StreamCoverage(summary["coverage"])
        contract_evaluation = StreamContractEvaluation(summary["contract_identity"])
    except (TypeError, ValueError) as error:
        raise StreamSnapshotError("TypeScript stream returned an unknown status") from error
    if coverage is not StreamCoverage.INCOMPLETE:
        raise StreamSnapshotError("TypeScript stream did not publish an INCOMPLETE snapshot")
    if contract_evaluation is not StreamContractEvaluation.NOT_EVALUATED:
        raise StreamSnapshotError("TypeScript stream returned an evaluated contract identity")
    for key in (
        "selected_file_count",
        "files_read",
        "files_parsed",
        "symbol_count",
        "unknown_count",
    ):
        if type(summary[key]) is not int or summary[key] < 0:
            raise StreamSnapshotError(f"TypeScript stream returned an invalid {key}")
    if summary.get("output") != str(output):
        raise StreamSnapshotError("TypeScript stream published an unexpected output path")
    verified = page(output, section="symbols", limit=1)
    identity = verified.get("snapshot")
    if not isinstance(identity, dict):
        raise StreamSnapshotError("TypeScript stream published invalid snapshot metadata")
    comparisons = {
        "snapshot_id": "snapshot_id",
        "source_revision": "source_git_head",
        "source_digest": "source_digest",
        "contract_identity": "contract_identity",
        "selected_file_count": "selected_file_count",
        "files_read": "files_read",
        "files_parsed": "files_parsed",
        "coverage": "coverage",
        "coverage_reason": "coverage_reason",
    }
    if any(summary[key] != identity.get(field) for key, field in comparisons.items()):
        raise StreamSnapshotError("TypeScript stream summary does not match the published file")
    counts = identity.get("record_counts")
    if not isinstance(counts, dict) or (
        summary["symbol_count"] != counts.get("symbols")
        or summary["unknown_count"] != counts.get("unknowns")
    ):
        raise StreamSnapshotError("TypeScript stream counts do not match the published file")
    return summary
