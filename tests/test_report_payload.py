# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The report v2 payload and its Python oracle producer (AD-361)."""

from __future__ import annotations

import ast
import contextlib
import copy
import io
import json
import random
from dataclasses import replace
from functools import cache
from pathlib import Path

import jsonschema
import pytest

from archkeel.cli import main
from archkeel.report.payload import Evaluation, build_payload, codes, evaluation
from archkeel.report.payload.canonical import encode
from archkeel.report.payload.codes import GAP, MEASURE
from archkeel.report.payload.records import SECTIONS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schema" / "report-2.0.schema.json").read_text(encoding="utf-8"))
VALIDATOR = jsonschema.Draft202012Validator(SCHEMA)
CONFIGS = sorted(
    str(path.relative_to(ROOT))
    for pattern in ("fixtures/*/archkeel*.toml", "fixtures/*/*/archkeel*.toml")
    for path in ROOT.glob(pattern)
)
EXPLORE = "explore:fixtures/N-explore"
CASES = (*CONFIGS, EXPLORE)


@cache
def _run(case: str, workdir: str) -> tuple[bytes, str]:
    """Run the current report once per case and return architecture.json and its result line."""
    output = Path(workdir) / case.replace("/", "_").replace(":", "_") / "architecture.json"
    if case == EXPLORE:
        argv = ["explore", "--root", str(ROOT / case.split(":", 1)[1])]
    else:
        config = ROOT / case
        argv = ["report", "--root", str(config.parent), "--config", config.name]
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        main([*argv, "--output", str(output.parent if case == EXPLORE else output), "--json"])
    return output.read_bytes(), stdout.getvalue().splitlines()[-1]


CODE_LISTS = {
    "Level": codes.LEVEL,
    "Kind": codes.KIND,
    "Vis": codes.VIS,
    "MeasureState": codes.MEASURE_STATE,
    "Verdict": codes.VERDICT,
    "EdgeTarget": codes.EDGE_TARGET,
    "FindingKind": codes.FINDING_KIND,
    "Disposition": codes.DISPOSITION,
    "Reason": codes.REASON,
    "Measure": codes.MEASURE,
    "Gap": codes.GAP,
    "Relation": codes.RELATION,
    "Permission": codes.PERMISSION,
    "UnknownSource": codes.UNKNOWN_SOURCE,
    "UnknownReason": codes.UNKNOWN_REASON,
}


@pytest.fixture(scope="session")
def workdir(tmp_path_factory: pytest.TempPathFactory) -> str:
    return str(tmp_path_factory.mktemp("report-payload"))


def _shuffled(document: dict[str, object], seed: int) -> dict[str, object]:
    changed = copy.deepcopy(document)
    generator = random.Random(seed)
    for name in (*SECTIONS, "evidence"):
        rows = changed.get(name)
        if isinstance(rows, list):
            generator.shuffle(rows)
    return changed


def _reversed_rules(verdicts: Evaluation) -> Evaluation:
    return replace(verdicts, rules=tuple(reversed(verdicts.rules)))


@pytest.mark.parametrize("case", CASES)
def test_payload_is_valid_canonical_and_equals_the_printed_summary(case: str, workdir: str) -> None:
    raw, line = _run(case, workdir)
    document = json.loads(raw)
    result = json.loads(line)
    verdicts = evaluation(result)

    data = build_payload(document, verdicts)
    payload = json.loads(data)

    assert [error.message for error in VALIDATOR.iter_errors(payload)] == []
    assert data == encode(payload) and data.count(b"\n") == 1 and data.endswith(b"\n")
    assert build_payload(document, verdicts) == data
    assert build_payload(_shuffled(document, 7), _reversed_rules(verdicts)) == data
    summary, assessments = payload["summary"], result["rule_assessments"] or []
    statuses = [item["status"] for item in assessments]
    assert summary["status"] == result["declared_rules"]
    assert [
        summary["counts"][f"rules_{name}"] for name in ("pass", "fail", "unknown", "declaration")
    ] == [statuses.count(name) for name in ("PASS", "FAIL", "UNKNOWN", "DECLARATION")]
    assert [
        (r["id"], r["verdict"], r["violations"], r["evaluated"]) for r in payload["rules"]
    ] == sorted((a["id"], a["status"], a["count"], a["evaluation_proven"]) for a in assessments)
    coverage = result["coverage"]
    assert payload["run"]["coverage"] == {
        key: coverage[key] for key in ("files_discovered", "files_read", "files_parsed")
    }
    assert summary["counts"]["modules"] == len(document["modules"])
    assert (payload["run"]["contract"] is None) == (case == EXPLORE)


def test_the_schema_code_lists_and_catalogues_equal_the_producer() -> None:
    defs = SCHEMA["$defs"]

    assert {name: tuple(defs[name]["x-codes"]) for name in CODE_LISTS} == CODE_LISTS
    assert tuple(item["id"] for item in defs["Measure"]["x-measures"]) == MEASURE
    assert tuple(item["id"] for item in defs["Gap"]["x-gaps"]) == GAP


def test_the_producer_imports_no_other_archkeel_package() -> None:
    package = ROOT / "src" / "archkeel" / "report"
    imported = set()
    for path in package.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
            elif isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)

    assert {name for name in imported if name.startswith("archkeel")} <= {
        name for name in imported if name.startswith("archkeel.report")
    }
