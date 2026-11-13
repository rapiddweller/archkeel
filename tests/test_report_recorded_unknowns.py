# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Full reports preserve canonical UNKNOWN evidence for independent assessment."""

import json
from hashlib import sha256
from pathlib import Path

from test_result_schema import current_validator as current_validator

from tools.architecture_graph_schema import command_schema


def test_published_legacy_schemas_remain_byte_exact():
    root = Path(__file__).parents[1] / "schema"
    assert sha256((root / "architecture-command.schema.json").read_bytes()).hexdigest() == (
        "8c365e57e039b64ed8bde1061324a29742e28d20718aef181e8ac8f38eb8d8f6"
    )
    assert sha256((root / "command-result.schema.json").read_bytes()).hexdigest() == (
        "d71145ef1c7b9ec8b80b1446fe3ca6f1aa61efd94939a73a2031f6832f5ff975"
    )
    assert sha256((root / "command-result-10.0.schema.json").read_bytes()).hexdigest() == (
        "b3bf8fc8cd1b498726a7b2bebb5b9d0281ef2cc4520ac304e3027ee91ed674f5"
    )
    assert sha256((root / "command-result-11.0.schema.json").read_bytes()).hexdigest() == (
        "ee99af7026f8a93751e818497d78685e9e93128b3d9dc0132b431d23af25315d"
    )
    assert json.loads((root / "architecture-command-2.0.schema.json").read_bytes()) == (
        command_schema()
    )
