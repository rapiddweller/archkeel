# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regenerate fixtures/D-self, the saved run tests/test_self.py compares every run with.

A change to Python code under src/ or to an architecture contract (architecture-contract.json or
an inside under src/) moves the self-observation; documentation does not. Run from the
repository root with:

    make self-observation
"""

from __future__ import annotations

import json
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.digest import package_digest
from archkeel.ir.model import Observation

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures/D-self"
ARTIFACT = "fixtures/D-self/architecture.json"
COMMAND = f"archkeel report --root . --output {ARTIFACT}"


def provenance(saved: Observation, artifact: bytes) -> dict[str, str | int]:
    """The digests that bind the saved artifact to the source, contract and tool that made it."""
    return {
        "analyzer_digest": saved.analyzer.code_digest,
        "checker_digest": package_digest(),
        "source_digest": saved.source.source_digest,
        "contract_digest": saved.contract.digest,
        "artifact_digest": sha256(artifact).hexdigest(),
        "command": COMMAND,
        "exit_code": 0,
        "python_version": saved.python_version,
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
    (FIXTURE / "provenance.json").write_text(
        json.dumps(provenance(saved, artifact), indent=4) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
