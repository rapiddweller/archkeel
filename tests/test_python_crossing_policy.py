# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Raw metrics and decoded change/ratchet reporting share Python crossing policy."""

from dataclasses import replace

import pytest
from test_delta import _model, _record
from test_source_evaluation import _facts

from archkeel.check.delta import _section
from archkeel.check.evaluation.evaluate import evaluate_source
from archkeel.check.observation import _metrics
from archkeel.check.python_profile import crossing_imports, is_crossing_import
from archkeel.check.ratchets import measure_python_ratchets
from archkeel.ir.codec import parse_contract, parse_observation
from archkeel.ir.measurements import RatchetError
from archkeel.ir.profiles import PROFILES, Language


@pytest.fixture(scope="module")
def scan_and_contract():
    contract = parse_contract({"schema_version": "2.1.0", "components": [], "rules": []})
    scan = evaluate_source(_facts(), contract, roots=("src",), namespace="project")
    return scan, contract


@pytest.mark.parametrize("symbol", ["public", "_private", "__dunder__", "", None, "annotations"])
@pytest.mark.parametrize("same_package", [False, True])
@pytest.mark.parametrize("target_module", ["other.api", "__future__"])
def test_raw_metric_decoded_ratchet_and_delta_agree(
    scan_and_contract, symbol, same_package, target_module
):
    scan, contract = scan_and_contract
    target_package = "project" if same_package else "other"
    record = _record(
        "crossing",
        kind="import",
        data={
            "symbol": symbol,
            "source_module": "project.app",
            "target_module": target_module,
            "source_package": "project",
            "target_package": target_package,
        },
    )
    expected_api = (
        bool(symbol)
        and not same_package
        and not (target_module == "__future__" and symbol == "annotations")
    )
    expected_private = expected_api and symbol.startswith("_")
    model = parse_observation(_model(git_head="a" * 40, imports=[record]))
    imports = model.records("imports")
    assert imports is not None
    metric = next(
        item
        for item in _metrics(replace(scan, imports=[record]), contract, PROFILES[Language.PYTHON])
        if item["kind"] == "private_crossings"
    )
    private_ids = ["crossing"] if expected_private else []
    api_ids = ["crossing"] if expected_api else []
    assert metric["fact_ids"] == private_ids
    assert metric["data"]["value"] == len(private_ids)
    assert measure_python_ratchets(model).scalars.private_crossings == len(private_ids)
    assert [item.id for item in _section(model, "private_crossings")] == private_ids
    assert [item.id for item in _section(model, "api_crossings")] == api_ids
    for private, expected in ((True, expected_private), (False, expected_api)):
        assert (
            is_crossing_import(symbol, "project", target_package, target_module, private=private)
            is expected
        )
        assert crossing_imports(imports, private=private) == (imports if expected else ())


@pytest.mark.parametrize(
    "change,message",
    [
        ({"symbol": 3}, "import.symbol must be a string or null"),
        ({"source_package": None}, "import packages must be non-empty strings"),
        ({"target_package": ""}, "import packages must be non-empty strings"),
    ],
)
def test_ratchet_boundary_still_rejects_invalid_import_fields(change, message):
    data = {"symbol": "_private", "source_package": "a", "target_package": "b"}
    data.update(change)
    model = parse_observation(
        _model(git_head="a" * 40, imports=[_record("i", kind="import", data=data)])
    )
    with pytest.raises(RatchetError, match=message):
        measure_python_ratchets(model)
