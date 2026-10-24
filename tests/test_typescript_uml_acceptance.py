# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""TypeScript inner facts stay separate from and comparable to declared Target."""

from __future__ import annotations

from test_uml_demo import _demo_report

from fixtures.architecture_demo import replay

VARIANTS = (
    ("uml-typescript-match", "PASS", 0),
    ("uml-typescript-mismatch", "FAIL", 2),
    ("uml-typescript-partial", "UNKNOWN", 0),
)


def test_typescript_match_and_changes_keep_one_independent_target(tmp_path, capsys):
    targets = []
    for variant, _, exit_code in VARIANTS:
        output = tmp_path / f"{variant}.json"
        assert replay(variant, output) == exit_code
        capsys.readouterr()
        targets.append(_demo_report(output).target)
    assert targets[0] == targets[1] == targets[2]
