# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #314: filtered JSON opens recorded evidence and drops passing rule rows."""

from pathlib import Path

from test_architecture_demo import _prepare_repo
from test_result_schema import current_validator as current_validator

from fixtures.architecture_demo import CATALOG


def _root(tmp_path: Path, variant_id: str) -> Path:
    if variant_id == "mixed":
        unknown = next(
            item for item in CATALOG if item.id == "class-a-boundary-types-shadowed-dict-unknown"
        )
        failing = next(item for item in CATALOG if item.id == "class-a-forbidden-dependency-pair")
        return _prepare_repo(tmp_path, {**unknown.files, **failing.files})
    variant = next(item for item in CATALOG if item.id == variant_id)
    return _prepare_repo(tmp_path, dict(variant.files), variant.fixture)
