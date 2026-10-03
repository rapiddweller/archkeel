# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import json
from pathlib import Path

import pytest

from archkeel.ir.identity import module_identity

_IDENTITY_FIXTURES = json.loads(
    (Path(__file__).parents[1] / "fixtures/language-module-identities.json").read_text(
        encoding="utf-8"
    )
)


@pytest.mark.parametrize("fixture", _IDENTITY_FIXTURES)
def test_module_identity_conformance_fixtures(fixture):
    assert (
        module_identity(fixture["namespace"], fixture["path"], fixture["language"])
        == fixture["module"]
    )


def test_typescript_identity_rejects_unsafe_paths():
    for path in ("/src/a.ts", "../src/a.ts", "src\\a.ts", "src//a.ts", ""):
        with pytest.raises(ValueError):
            module_identity("app", path, "typescript")
