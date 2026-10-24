# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Execute the actual scene and layout modules without a DOM or Chromium."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ASSETS = Path(__file__).parents[1] / "src/archkeel/render/assets"


def evaluate_scene(expression: str, argument: object = None):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Scene logic tests require Node")
    script = f"""
        import {{readFileSync}} from 'node:fs';
        globalThis.window = globalThis;
        await import({json.dumps((ASSETS / "report-scene.js").as_uri())});
        await import({json.dumps((ASSETS / "report-layout.js").as_uri())});
        const argument = JSON.parse(readFileSync(0, 'utf8'));
        console.log(JSON.stringify(await ({expression})(argument)));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script],
        input=json.dumps(argument),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    return json.loads(result.stdout)
