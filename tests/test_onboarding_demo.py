# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The onboarding demo prints what the commands actually answer, or it prints nothing."""

from pathlib import Path

import pytest

from fixtures.reproduce_onboarding import Step, run_onboarding_demo


@pytest.fixture(scope="module")
def steps(tmp_path_factory: pytest.TempPathFactory) -> tuple[Step, ...]:
    return run_onboarding_demo(tmp_path_factory.mktemp("onboarding"))


def test_the_demo_module_is_runnable_from_the_repository_root() -> None:
    assert (Path(__file__).parents[1] / "fixtures/reproduce_onboarding.py").is_file()
