# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1615: imports of packages that are not installed are named in one line, with the fix."""

import pytest
from test_cli_gap_causes import _by_causes
from test_cli_text_output import _run, environment  # noqa: F401


def test_the_packages_that_are_not_installed_are_named_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = _by_causes(
        {
            "Unresolved module: react": 6,
            "Unresolved module: @tanstack/react-query/build": 3,
            "Unresolved module: ./local-file": 2,
            "dynamic_import: importlib.util": 1,
        }
    )
    _, text = _run(document, ["validate", "--text"], capsys)
    assert (
        "9 imports point to packages that could not be found (most likely not installed): "
        "react, @tanstack/react-query" in text
    )
    assert "Fix: if they are not installed, install them" in text


def test_many_packages_are_cut_after_five(capsys: pytest.CaptureFixture[str]) -> None:
    document = _by_causes({f"Unresolved module: pkg{n}": 2 for n in range(8)})
    _, text = _run(document, ["validate", "--text"], capsys)
    assert (
        "16 imports point to packages that could not be found (most likely not installed): " in text
    )
    assert "and 3 more" in text


def test_a_relative_import_is_not_called_a_package(capsys: pytest.CaptureFixture[str]) -> None:
    document = _by_causes({"Unresolved module: ../up": 4})
    _, text = _run(document, ["validate", "--text"], capsys)
    assert "could not be found" not in text
