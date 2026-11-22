# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-764: a PASS that rests on a premise of the contract is never the bare word PASS."""

from __future__ import annotations

import json

import pytest
from test_cli_core_only_boundary import frame
from test_cli_text_output import _run
from test_cli_text_output import environment as environment

from archkeel.cli.core_frame import Status


def test_a_pass_under_a_premise_is_never_the_bare_word(capsys: pytest.CaptureFixture[str]) -> None:
    """#1549: a PASS run whose rule rests on a stated external user reads "PASS under"."""
    document = json.loads(frame(Status.PASS))
    rule = next(iter(document["rules"]))
    document["premises"] = {rule: [{"kind": "external_user", "subject": "app.api:serve"}]}
    document["assuming"] = "1 stated external user"
    done, text = _run(document, ["validate", "--text"], capsys)
    first = text.splitlines()[0]
    assert done == 0
    assert first.startswith("validate: PASS under 1 stated external user -> exit 0 ("), first
    assert "1 pass under 1 stated external user" in first
    assert "  stated external users: app.api:serve" in text
    # Without a premise the word stays PASS.
    done, text = _run(json.loads(frame(Status.PASS)), ["validate", "--text"], capsys)
    assert text.splitlines()[0].startswith("validate: PASS -> exit 0 (")
