# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regenerate fixtures/D-self, the saved run tests/test_self.py compares every run with.

A change to Python code under src/, pyproject.toml, or an architecture contract moves the
self-observation; documentation does not. Run from the
repository root with:

    make self-observation
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

from archkeel.ir.codec import canonical_report_bytes, decode_canonical_model, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.model import Observation

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"
ARTIFACT = "fixtures/D-self/architecture.json"


def provenance(saved: Observation) -> dict[str, str]:
    """Keep an independent content baseline without incidental Git context."""
    normalized = replace(saved, source=replace(saved.source, git_head=None, dirty=False))
    return {
        "checker_digest": package_digest(),
        "observation_digest": sha256(canonical_report_bytes(normalized)).hexdigest(),
    }


def main() -> int:
    run = subprocess.run(
        [sys.executable, "-m", "archkeel.cli", "report", "--root", ".", "--output", ARTIFACT],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        sys.stderr.write(run.stdout + run.stderr)
        return run.returncode
    (FIXTURE / "result.json").write_text(run.stdout)
    artifact = (FIXTURE / "architecture.json").read_bytes()
    saved = parse_observation(decode_canonical_model(json.loads(artifact)))
    (FIXTURE / "provenance.json").write_text(json.dumps(provenance(saved), indent=4) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
