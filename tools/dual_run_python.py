# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python engine as one side of the dual run (AD-360). Delete this file with the engine.

The adapter calls the `report` command in process and writes no HTML page. It returns the
architecture.json bytes and the rule assessments of the JSON result. A case can name its own
collector; a Rust case without one uses the Rust collector of the workspace. A pinned collector
gets the digest of its program, as the tests pin it (AD-344).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from archkeel.check.ports import Language
from archkeel.check.report import render_result, run_report_with_observation
from archkeel.cli.config import load_config
from archkeel.cli.observe import configured_observer, observer_for


def run_python_engine(
    root: Path,
    config: str,
    baseline: str | None,
    collector_argv: tuple[str, ...] | None = None,
    pinned: bool = False,
    rust_collector: str | None = None,
) -> dict[str, Any]:
    """Return the engine frame: `rules` (id to kind and status) and `architecture`."""
    scan = load_config(root, config)
    argv = collector_argv
    if argv is None and scan.language == Language.RUST and scan.collector_argv is None:
        argv, pinned = (rust_collector or "archkeel-rust-collector",), True
    factory: Callable[..., Any] = observer_for
    if argv is not None:
        if not Path(argv[0]).is_file():
            return {"error": f"the collector {argv[0]} is missing: build it (`make dual-run`)"}
        digest = "sha256:" + hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest()

        def factory(*args: Any, **options: Any) -> Any:
            options["collector_argv"] = argv
            options["pinned_digest"] = digest if pinned else None
            return observer_for(*args, **options)

    observer = configured_observer(scan, factory)
    result, architecture, _ = run_report_with_observation(
        root,
        config=scan,
        analyzer=observer,
        baseline=None if baseline is None else Path(baseline),
    )
    assessments = json.loads(render_result(result))["rule_assessments"] or []
    return {
        "rules": {row["id"]: [row["kind"], row["status"]] for row in assessments},
        "architecture": None if architecture is None else json.loads(architecture),
    }
