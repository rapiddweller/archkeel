# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The HTML executes a checked derivative of one authored Flow program."""

from hashlib import sha256
from pathlib import Path

from test_atlas_report import _page, _sample


def test_report_identifies_the_current_flow_source_derivative(tmp_path):
    source = Path(__file__).parents[1] / "src/archkeel/render/assets/flow.js"
    expected = f"// Generated from flow.js; source-sha256={sha256(source.read_bytes()).hexdigest()}"
    page = _page(_sample(tmp_path))
    assert expected in page
