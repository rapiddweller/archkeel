# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Independent amendment intent, legacy bytes and native source mutations."""

import copy
import importlib
import json
from dataclasses import FrozenInstanceError, replace
from enum import StrEnum
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo
from test_dependency_api_target import _source_members

from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir import codec, codec_governance, model, widening
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.codec_result import result_payload
from archkeel.ir.report_graph import architecture_report
from archkeel.ir.trace import trace_valid_violations

ROOT = Path(__file__).parents[1]
OWNER = "archkeel.ir.amendment"
CODEC = "archkeel.ir.amendment_codec"
DOC = "docs/architecture/typed-amendment-artifact.md"


def _owner():
    assert (ROOT / "src/archkeel/ir/amendment.py").exists(), "Nominal artifact owner is missing"
    return importlib.import_module(OWNER)


@pytest.mark.parametrize("name", ["Amendment", "verify_amendment", "AMENDMENT_SCHEMA_VERSION"])
def test_existing_widening_ports_keep_exact_owned_identity(name):
    assert getattr(widening, name) is getattr(_owner(), name)


@pytest.mark.parametrize("name", ["parse_amendment", "amendment_bytes"])
def test_existing_codec_ports_keep_exact_owned_identity(name):
    owner = importlib.import_module(CODEC)
    assert getattr(codec, name) is getattr(codec_governance, name) is getattr(owner, name)


@pytest.mark.parametrize("version", ["1.0.0", "2.0.0"])
def test_nominal_version_keeps_valid_legacy_construction_frozen_value_and_exact_bytes(version):
    before, after = "a" * 64, "b" * 64
    value = widening.Amendment(
        before, after, "ake2l; agent or anyone", "理由", schema_version=version
    )
    assert type(value.schema_version) is _owner().AmendmentVersion
    assert isinstance(value.schema_version, StrEnum)
    baseline = '  "after_baseline_digest": null,\n' if version == "2.0.0" else ""
    baseline_before = '  "before_baseline_digest": null,\n' if version == "2.0.0" else ""
    expected = (
        "{\n"
        + baseline
        + f'  "after_digest": "{after}",\n'
        + baseline_before
        + f'  "before_digest": "{before}",\n'
        + '  "decided_by": "ake2l; agent or anyone",\n'
        + '  "rationale": "理由",\n'
        + f'  "schema_version": "{version}"\n'
        + "}\n"
    ).encode("utf-8")
    assert codec.amendment_bytes(value) == expected
    replay = codec.parse_amendment(json.loads(expected))
    assert replay == value and type(replay.schema_version) is _owner().AmendmentVersion
    with pytest.raises(FrozenInstanceError):
        value.schema_version = "2.0.0"


@pytest.mark.parametrize("version", [None, False, 7, [], {}, "3.0.0"])
def test_unsupported_wire_version_preserves_legacy_error(version):
    with pytest.raises(ValueError) as error:
        codec.parse_amendment({"schema_version": version})
    assert str(error.value) == f"unsupported amendment schema {version!r}"


def test_v1_cannot_authorize_baseline_binding_and_v2_binds_both_sides():
    before, after, policy_before, policy_after = (char * 64 for char in "abcd")
    actor = "a person; not an architect/agent role tag"
    old = widening.Amendment(before, after, actor, "reason", schema_version="1.0.0")
    assert widening.verify_amendment(old, before_digest=before, after_digest=after)
    assert not widening.verify_amendment(
        old, before_digest=before, after_digest=after, before_baseline_digest=policy_before
    )
    current = widening.Amendment(before, after, actor, "reason", policy_before, policy_after)
    arguments = dict(
        before_digest=before,
        after_digest=after,
        before_baseline_digest=policy_before,
        after_baseline_digest=policy_after,
    )
    assert widening.verify_amendment(current, **arguments)
    for key in arguments:
        assert not widening.verify_amendment(current, **{**arguments, key: "e" * 64})
    assert codec.parse_amendment(json.loads(codec.amendment_bytes(current))) == current
    assert replace(current, decided_by="agent").decided_by == "agent"


@pytest.mark.parametrize("status", ["valid", "stale", None])
def test_run_result_owns_only_the_existing_amendment_status_subset(status):
    value = model.RunResult("validate", 0, amendment_status=status)
    if status is not None:
        assert type(value.amendment_status) is _owner().AmendmentStatus
    else:
        assert value.amendment_status is None
    assert result_payload(value)["amendment_status"] == status


def _contract():
    contract = copy.deepcopy(json.loads((ROOT / "docs/architecture/contracts/ir.json").read_text()))
    contract.pop("$schema", None)
    contract["declarations"]["uml"]["entities"] = [
        row
        for row in contract["declarations"]["uml"]["entities"]
        if row["id"].startswith("IR-AMENDMENT-")
        or row["id"] in {"IR-DEPENDENCY-model", "IR-GRAPH-RunResult"}
    ]
    contract["declarations"]["uml"]["relationships"] = []
    contract["declarations"]["uml"]["scopes"] = []
    root = json.loads((ROOT / "architecture-contract.json").read_text())
    contract["rules"] = [
        row
        for row in root["rules"]
        if row["id"]
        in {
            "AMENDMENT-ARTIFACT-TYPED-CONTROL",
            "AMENDMENT-CODEC-TYPED-CONTROL",
            "TYPES-ENUM-IN-MODEL",
        }
    ]
    return contract


def _repository(tmp_path):
    files = {
        "archkeel/__init__.py": "",
        "archkeel/ir/__init__.py": "",
        "contract.json": json.dumps(_contract()),
        DOC: "Owned immutable amendment intent.\n",
        "archkeel/ir/model.py": (
            "from __future__ import annotations\nfrom dataclasses import dataclass\n"
            "from typing import Literal\n"
            + (
                "from .amendment import AmendmentStatus as AmendmentStatus\n"
                if (ROOT / "src/archkeel/ir/amendment.py").exists()
                else ""
            )
            + _source_members("src/archkeel/ir/model.py", {"RunResult"})
        ),
        "archkeel/ir/codec_wire.py": (ROOT / "src/archkeel/ir/codec_wire.py").read_text(),
    }
    for name in ("amendment", "amendment_codec"):
        source = ROOT / f"src/archkeel/ir/{name}.py"
        if source.exists():
            files[f"archkeel/ir/{name}.py"] = source.read_text()
    if not (ROOT / "src/archkeel/ir/amendment.py").exists():
        files["archkeel/ir/widening.py"] = (
            "from dataclasses import dataclass\nAMENDMENT_SCHEMA_VERSION = '2.0.0'\n"
            + _source_members("src/archkeel/ir/widening.py", {"Amendment", "verify_amendment"})
        )
    root = _prepare_repo(tmp_path, files)
    return root, ScanConfig(("archkeel",), "archkeel", "contract.json", "0" * 64)


def _observe(root, config):
    result, encoded = run_report(root, config=config, analyzer=observe)
    assert result.exit_code == 0 and encoded is not None, result.diagnostics
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _comparison(value):
    comparison = architecture_report(value).comparison
    assert comparison is not None
    return comparison


def _valid(value):
    assert _comparison(value).status == "PASS", _comparison(value)
    assert not trace_valid_violations(value)


def test_governance_legacy_value_and_version_names_keep_owned_identity():
    owner = _owner()
    assert codec_governance.Amendment is owner.Amendment
    assert codec_governance.AMENDMENT_SCHEMA_VERSION is owner.AMENDMENT_SCHEMA_VERSION
