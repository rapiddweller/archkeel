# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The guard `no_store_left` of `conftest.py` fails a test that leaves the Rust store open."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ("pytester",)

CONFTEST = Path(__file__).with_name("conftest.py")


def test_a_test_that_leaves_the_store_open_fails_and_the_next_test_sees_no_store(
    pytester: pytest.Pytester,
) -> None:
    # Only the guard of the suite conftest, so the run starts no session fixture of the suite.
    pytester.makeconftest(
        f"""
        import importlib.util

        spec = importlib.util.spec_from_file_location("suite_conftest", {str(CONFTEST)!r})
        suite = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(suite)
        no_store_left = suite.no_store_left
        """
    )
    pytester.makepyfile(
        """
        from archkeel.ir.store_seam import active_store, open_store

        CLOSED = []

        class Seam:
            def close(self):
                CLOSED.append(True)

        class Facts:
            pass

        FACTS = Facts()

        def test_leaks():
            open_store(Seam(), FACTS)

        def test_next():
            assert active_store() is None
            assert CLOSED == [True]
        """
    )
    result = pytester.runpytest("-p", "no:xdist")
    result.assert_outcomes(passed=2, errors=1)
    result.stdout.fnmatch_lines(["*the test left the Rust store open (AD-346)*"])
