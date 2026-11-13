# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-408: replay frozen construct facts below, but never through, the refused store boundary."""

from __future__ import annotations

import copy
import gzip
import json
import os
import subprocess
from pathlib import Path

from archkeel.check.evaluation.rules import _construct_violations
from archkeel.ir.codec import parse_contract

ROOT = Path(__file__).resolve().parents[1]


def _cases() -> list[dict[str, object]]:
    reply = json.loads(
        gzip.decompress((ROOT / "tests/golden/python/synthetic-constructs.json.gz").read_bytes())
    )
    facts = reply["facts"]
    facts["adapter"].update(version="0", code_digest="0" * 64)
    facts["runtime"] = {
        "name": "python",
        "version": "3.11.12",
        "required": ">=3.11",
        "requirement_state": "declared",
    }
    facts["source"].update(git_head="a", dirty=False)
    # The model reads none of these tables. The production store still refuses their proofs.
    facts.update(
        type_shapes=[],
        provider_bindings=[],
        candidate_evidence=[],
        state={"classes": [], "functions": []},
    )
    facts["sections"] = [
        s
        for s in facts["sections"]
        if s["name"] in {"constructs", "typing_signals", "symbols", "imports", "unknowns"}
    ]
    template = json.loads((ROOT / "fixtures/H-typescript/architecture-contract.json").read_text())
    component = template["components"][0]
    component.update(packages=["app"], public=["app"], requires=[])
    contract = {"schema_version": "3.14.0", "components": [component], "rules": []}
    signals = [
        r
        for name in ("typing_signals", "constructs")
        for section in facts["sections"]
        if section["name"] == name
        for r in section["records"]
    ]
    cases = []
    for capability in facts["capabilities"]["constructs"]:
        rule = {
            "id": "CONSTRUCT",
            "kind": "forbidden_construct",
            "source": "app",
            "constructs": [capability["name"]],
            "rationale": "Replay original observations.",
            "provenance": ["p"],
            "decided_by": "architect",
        }
        for option in (
            {},
            {"allowed_sources": ["app.core.work.risky"]},
            {"exact_sources": ["app.core.work.risky"]},
        ):
            candidate = copy.deepcopy(contract)
            candidate["rules"] = [{**rule, **option}]
            parsed = parse_contract(candidate)
            expected = _construct_violations(signals, parsed.rules)
            cases.append(
                {
                    "name": f"{capability['name']}/{','.join(option)}",
                    "namespace": "app",
                    "facts": facts,
                    "contract": candidate,
                    "expected": expected,
                }
            )
    return cases


def test_frozen_construct_matching_and_rows_equal_python(tmp_path: Path) -> None:
    cases = _cases()
    path = tmp_path / "construct-replay.json"
    path.write_text(json.dumps(cases))
    env = {**os.environ, "ARCHKEEL_CONSTRUCT_REPLAY": str(path)}
    for package, test in (
        ("archkeel-model", "replay_frozen_construct_matching"),
        ("archkeel-report", "replay_frozen_construct_rows"),
    ):
        result = subprocess.run(
            ["cargo", "test", "--locked", "-p", package, test, "--", "--ignored", "--nocapture"],
            cwd=ROOT / "native",
            env=env,
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert "equal" in result.stdout, result.stdout
