# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-59: the type-fan-in claim needs its signals and never guesses without them."""

import json
from dataclasses import replace
from pathlib import Path

from archkeel.analyzer import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.type_fanin import type_fanin

ROOT = Path(__file__).resolve().parents[1]


def _self_observation():
    artifact = (ROOT / "fixtures/D-self/architecture.json").read_bytes()
    return parse_observation(decode_canonical_model(json.loads(artifact)))


def _observe(source: Path):
    metadata = source / "pyproject.toml"
    if not metadata.exists():
        metadata.write_text('[project]\nrequires-python = ">=3.11"\n')
    contract = source / "contract.json"
    if not contract.exists():
        contract.write_text('{"schema_version":"2.1.0","components":[],"rules":[]}')
    return observe(
        source,
        roots=(".",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=source,
    )


def test_the_claim_is_unknown_without_the_imports_signal() -> None:
    observation = _self_observation()
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "imports"),
    )

    result = type_fanin(without)

    assert result.status == "UNKNOWN"
    assert result.candidates == ()
    assert result.positions == 0


def test_the_claim_is_unknown_without_the_symbols_signal() -> None:
    observation = _self_observation()
    without = replace(
        observation,
        sections=tuple(item for item in observation.sections if item.name != "symbols"),
    )

    result = type_fanin(without)

    assert result.status == "UNKNOWN"


def test_a_type_crossing_two_component_pairs_is_named(tmp_path: Path) -> None:
    """One function two components both call names its annotation twice, not once each."""
    contract = {
        "schema_version": "2.1.0",
        "components": [
            {
                "id": "COMP-SHARED",
                "label": "shared",
                "role": "component",
                "packages": ["sample.shared"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/sample.md"],
            },
            {
                "id": "COMP-LEFT",
                "label": "left",
                "role": "component",
                "packages": ["sample.left"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/sample.md"],
            },
            {
                "id": "COMP-RIGHT",
                "label": "right",
                "role": "component",
                "packages": ["sample.right"],
                "responsibilities": [],
                "forbidden_responsibilities": [],
                "provenance": ["docs/architecture/sample.md"],
            },
        ],
        "rules": [],
    }
    (tmp_path / "contract.json").write_text(json.dumps(contract))
    (tmp_path / "sample/shared").mkdir(parents=True)
    (tmp_path / "sample/shared/__init__.py").write_text("")
    (tmp_path / "sample/shared/util.py").write_text(
        "class Money:\n    pass\n\n\ndef handle(value: Money) -> Money:\n    return value\n"
    )
    (tmp_path / "sample/left").mkdir(parents=True)
    (tmp_path / "sample/left/__init__.py").write_text("")
    (tmp_path / "sample/left/user.py").write_text(
        "from sample.shared.util import handle\n\nhandle(None)\n"
    )
    (tmp_path / "sample/right").mkdir(parents=True)
    (tmp_path / "sample/right/__init__.py").write_text("")
    (tmp_path / "sample/right/user.py").write_text(
        "from sample.shared.util import handle\n\nhandle(None)\n"
    )
    result = _observe(tmp_path)
    assert result.observation is not None

    claim = type_fanin(result.observation)

    assert claim.status == "SUPPORTED"
    assert [(item.annotation, item.crossings) for item in claim.candidates] == [("Money", 2)]


def test_archkeel_itself_names_its_own_shared_ir_types() -> None:
    """Archkeel's shared IR crossing widely is the architecture working as declared (AD-26)."""
    result = type_fanin(_self_observation())

    assert result.status == "SUPPORTED"
    assert result.positions > 0
    names = {item.annotation for item in result.candidates}
    assert "object" in names
