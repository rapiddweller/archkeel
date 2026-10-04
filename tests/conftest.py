# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import pytest


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(error: object | None) -> None:
    # xdist can return success after a worker crashes during collection.
    if error is not None:
        pytest.exit(f"Test worker crashed: {error}", returncode=1)
