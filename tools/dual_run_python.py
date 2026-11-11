# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python engine as one side of the dual run (AD-360). Delete this file with the engine.

The adapter calls the `report` command in process and writes no HTML page. It returns the
architecture.json bytes and the rule assessments of the JSON result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from archkeel.check.report import render_result, run_report_with_observation
from archkeel.cli.config import load_config
from archkeel.cli.observe import configured_observer, observer_for


def run_python_engine(root: Path, config: str, baseline: str | None) -> dict[str, Any]:
    """Return the engine frame: `rules` (id to kind and status) and `architecture`."""
    scan = load_config(root, config)
    observer = configured_observer(scan, observer_for)
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
