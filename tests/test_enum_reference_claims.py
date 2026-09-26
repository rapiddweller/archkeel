# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #166: enum members in annotations and defaults are symbol references."""

from pathlib import Path

from test_analyzer import _observe

from archkeel.ir.decisions import review_claims
from archkeel.ir.references import unreferenced_symbols


def _enum_candidates(root: Path) -> set[str]:
    result = _observe(root)
    assert result.observation is not None
    claim = unreferenced_symbols(result.observation)
    assert claim.status == "SUPPORTED"
    assert review_claims(result.observation).unreferenced_symbols == len(claim.candidates)
    return {item.name for item in claim.candidates if item.kind == "class"}


def _write_enum_app(root: Path, facade: str) -> None:
    (root / "sample").mkdir(parents=True, exist_ok=True)
    (root / "sample/types.py").write_text(
        "from enum import Enum\n"
        "class State(Enum):\n"
        "    READY = 'ready'\n"
        "\n"
        "class Unused(Enum):\n"
        "    IDLE = 'idle'\n"
    )
    (root / "sample/facade.py").write_text(facade)


def test_literal_field_and_default_reference_the_enum(tmp_path: Path) -> None:
    _write_enum_app(
        tmp_path,
        "from typing import Literal\n"
        "from sample.types import State\n"
        "\n"
        "class Payload:\n"
        "    annotated: Literal[State.READY]\n"
        "    defaulted: State = State.READY\n",
    )

    candidates = _enum_candidates(tmp_path)

    assert "sample.types.State" not in candidates
    assert "sample.types.Unused" in candidates


def test_same_module_literal_field_and_default_reference_enum(tmp_path: Path) -> None:
    (tmp_path / "sample").mkdir(parents=True)
    (tmp_path / "sample/facade.py").write_text(
        "from enum import Enum\n"
        "from typing import Literal\n"
        "from pydantic import BaseModel\n"
        "\n"
        "class IntentRepairKind(str, Enum):\n"
        "    INVALID_DISCRIMINATOR = 'invalid_discriminator'\n"
        "\n"
        "class DefaultRepairKind(str, Enum):\n"
        "    OTHER = 'other'\n"
        "\n"
        "class UnusedRepairKind(str, Enum):\n"
        "    NEVER_USED = 'never_used'\n"
        "\n"
        "class IntentRepair(BaseModel):\n"
        "    kind: Literal[IntentRepairKind.INVALID_DISCRIMINATOR]\n"
        "    default_kind: str = DefaultRepairKind.OTHER\n"
    )

    candidates = _enum_candidates(tmp_path)

    assert "sample.facade.IntentRepairKind" not in candidates
    assert "sample.facade.DefaultRepairKind" not in candidates
    assert "sample.facade.UnusedRepairKind" in candidates


def test_aliased_imported_enum_member_references_its_source_class(tmp_path: Path) -> None:
    _write_enum_app(
        tmp_path,
        "from typing import Literal\n"
        "from sample.types import State as WorkflowState\n"
        "\n"
        "class Payload:\n"
        "    status: Literal[WorkflowState.READY] = WorkflowState.READY\n",
    )

    candidates = _enum_candidates(tmp_path)

    assert "sample.types.State" not in candidates
    assert "sample.types.Unused" in candidates


def test_namespace_qualified_enum_member_references_its_source_class(tmp_path: Path) -> None:
    _write_enum_app(
        tmp_path,
        "from typing import Literal\n"
        "import sample.types as types\n"
        "\n"
        "class Payload:\n"
        "    status: Literal[types.State.READY] = types.State.READY\n",
    )

    candidates = _enum_candidates(tmp_path)

    assert "sample.types.State" not in candidates
    assert "sample.types.Unused" in candidates


def test_shadowed_import_does_not_reference_the_shadowed_enum(tmp_path: Path) -> None:
    _write_enum_app(
        tmp_path,
        "from typing import Literal\n"
        "from sample.types import State\n"
        "\n"
        "class State:\n"
        "    READY = 'local'\n"
        "\n"
        "class Payload:\n"
        "    status: Literal[State.READY] = State.READY\n",
    )

    candidates = _enum_candidates(tmp_path)

    assert "sample.types.State" in candidates
    assert "sample.types.Unused" in candidates
    assert "sample.facade.State" not in candidates
