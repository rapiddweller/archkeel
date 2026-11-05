# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Windows process safety and ProcessCollector startup boundaries."""

import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from test_collection_protocol import _request

import archkeel.analyzer.process as process_module
from archkeel.analyzer.process import is_process_alive
from archkeel.ir.facts_codec import decode_request
from archkeel.ir.protocol import CollectionError


@pytest.mark.skipif(os.name != "posix", reason="simulates Windows helper startup on POSIX")
def test_windows_helper_does_not_import_project_sitecustomize_before_platform_guard(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "sitecustomize-ran"
    custom = tmp_path / "project-path"
    custom.mkdir()
    (custom / "sitecustomize.py").write_text(
        f"from pathlib import Path; Path({str(marker)!r}).write_text('imported')\n"
    )
    request = replace(
        decode_request(_request()),
        snapshot=replace(decode_request(_request()).snapshot, root=str(tmp_path)),
    )
    fake_os = SimpleNamespace(name="nt", pathsep=os.pathsep, environ=dict(os.environ))
    fake_os.environ["PYTHONPATH"] = str(custom)
    with (
        patch.object(process_module, "os", fake_os),
        patch.object(process_module.shutil, "which", return_value=sys.executable),
    ):
        result = process_module.ProcessCollector((sys.executable, "-B", "-c", "pass")).collect(
            request
        )
    assert isinstance(result, CollectionError)
    assert result.kind == "execution_error", result
    assert not marker.exists(), (
        "Windows helper imported project PYTHONPATH before checking the platform"
    )


@pytest.mark.skipif(os.name != "nt", reason="requires native Windows process handles")
def test_windows_pid_liveness_does_not_terminate_a_live_process() -> None:
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        assert is_process_alive(process.pid)
        time.sleep(0.2)
        assert process.poll() is None
        process.terminate()
        process.wait(timeout=5)
        assert not is_process_alive(process.pid)
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)
