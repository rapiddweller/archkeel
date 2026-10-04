# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A faster gate must still reject worker crashes and accept healthy runs."""

import shutil
import subprocess
import sys
from pathlib import Path
from xml.etree import ElementTree

import pytest

ROOT = Path(__file__).parents[1]
PARALLEL = ["-n", "2", "--dist=loadfile", "--max-worker-restart=0"]


@pytest.mark.parametrize("phase", ["collection", "body"])
def test_parallel_worker_crash_fails_the_command(tmp_path: Path, phase: str) -> None:
    configuration = tmp_path / "conftest.py"
    shutil.copyfile(ROOT / "tests/conftest.py", configuration)
    if phase == "collection":
        # Crash after another worker's collection reaches the controller: xdist can
        # otherwise report success without having executed a single test.
        with configuration.open("a") as file:
            file.write(
                "\nfrom pathlib import Path\n"
                "def pytest_xdist_node_collection_finished(node, ids):\n"
                "    if node.gateway.id == 'gw0':\n"
                "        Path(__file__).with_name('collected').touch()\n"
            )
        code = (
            "import os, time\nfrom pathlib import Path\n"
            "if os.environ['PYTEST_XDIST_WORKER'] == 'gw1':\n"
            "    deadline = time.monotonic() + 10\n"
            "    while not Path(__file__).with_name('collected').exists():\n"
            "        if time.monotonic() > deadline:\n"
            "            raise RuntimeError('controller did not receive collection')\n"
            "        time.sleep(0.01)\n"
            "    os._exit(17)\n"
            "def test_would_pass():\n    assert True\n"
        )
    else:
        code = "import os\ndef test_crashes():\n    os._exit(17)\n"
    (tmp_path / "test_crash.py").write_text(code)
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *PARALLEL, "test_crash.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if phase == "collection":
        assert (tmp_path / "collected").is_file(), (run.stdout, run.stderr)
    assert run.returncode != 0, (run.stdout, run.stderr)


@pytest.mark.parametrize("options", [PARALLEL, ["-n", "0"], ["-p", "no:xdist"]])
def test_healthy_runner_finishes_without_a_false_failure(
    tmp_path: Path, options: list[str]
) -> None:
    shutil.copyfile(ROOT / "tests/conftest.py", tmp_path / "conftest.py")
    (tmp_path / "test_healthy.py").write_text("def test_passes():\n    assert True\n")
    run = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *options, "--junitxml=result.xml"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert run.returncode == 0, (run.stdout, run.stderr)
    cases = ElementTree.parse(tmp_path / "result.xml").findall(".//testcase")
    assert len(cases) == 1
    assert cases[0].find("failure") is None
    assert cases[0].find("error") is None
    assert cases[0].find("skipped") is None
