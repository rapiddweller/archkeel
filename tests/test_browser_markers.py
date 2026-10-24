# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Keep Chromium tests out of the default Python test selection."""

import ast
from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

ROOT = Path(__file__).parents[1]


def test_remaining_browser_smokes_are_marked_before_fixture_setup():
    for path in ROOT.glob("tests/test_*.py"):
        functions = [
            node for node in ast.parse(path.read_text()).body if isinstance(node, ast.FunctionDef)
        ]
        browser_entries = {
            function.name
            for function in functions
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "importorskip"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "playwright.sync_api"
                for node in ast.walk(function)
            )
        }
        for function in functions:
            if not function.name.startswith("test_"):
                continue
            uses_browser = function.name in browser_entries or any(
                arg.arg in browser_entries for arg in function.args.args
            )
            if uses_browser:
                assert any(
                    isinstance(item, ast.Attribute) and item.attr == "browser"
                    for item in function.decorator_list
                ), (path.name, function.name)


def test_browser_marker_deselects_before_fixture_setup(pytester: pytest.Pytester):
    pytester.makepyprojecttoml((ROOT / "pyproject.toml").read_text())
    pytester.makepyfile("""
        import pytest

        @pytest.fixture
        def page():
            raise AssertionError("browser fixture ran")

        @pytest.mark.browser
        def test_browser(page):
            pass

        def test_logic():
            pass
    """)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, deselected=1)
