# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Fresh-process acceptance probes for #720, not an Archkeel evidence producer.

These probes run only the synthetic project created by the test. They do not define a receipt
format or exercise a contract, evaluator, saved report, or arbitrary repository.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

PROBE = """
import importlib
import json
import sys

sys.path.insert(0, sys.argv[1])
importlib.import_module("sample.facade")
print(json.dumps({
    "executable": sys.executable,
    "version": list(sys.version_info[:3]),
    "modules": sorted(
        name for name in sys.modules if name == "sample" or name.startswith("sample.")
    ),
}))
"""


def project(root: Path, facade: str) -> str:
    sources = {
        "sample/__init__.py": "",
        "sample/facade.py": facade,
        "sample/core.py": "def plan(): return 1\n",
        "sample/drivers/__init__.py": "",
        "sample/drivers/sql.py": "def connect(): return 1\n",
    }
    for name, text in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return source_digest(root)


def source_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def probe(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", "-c", PROBE, str(root)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )


def test_pass_control_has_a_completed_fresh_import_without_the_driver(tmp_path: Path) -> None:
    before = project(
        tmp_path,
        "from sample.core import plan\n"
        "def run():\n"
        "    from sample.drivers.sql import connect\n"
        "    return connect()\n",
    )
    result = probe(tmp_path)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert Path(observation["executable"]).resolve() == Path(sys.executable).resolve()
    assert observation["version"] == list(sys.version_info[:3])
    assert observation["modules"] == ["sample", "sample.core", "sample.facade"]
    assert source_digest(tmp_path) == before


def test_fail_control_observes_the_driver_after_a_completed_fresh_import(tmp_path: Path) -> None:
    before = project(tmp_path, "from sample.drivers.sql import connect\n")
    result = probe(tmp_path)
    assert result.returncode == 0, result.stderr
    observation = json.loads(result.stdout)
    assert "sample.drivers.sql" in observation["modules"]
    assert source_digest(tmp_path) == before


@pytest.mark.parametrize(
    "facade",
    [
        "raise RuntimeError('probe failed')\n",
        "from sample.drivers.sql import connect\nraise RuntimeError('probe failed')\n",
    ],
)
def test_unknown_control_has_no_completed_observation_after_an_error(
    tmp_path: Path, facade: str
) -> None:
    project(tmp_path, facade)
    result = probe(tmp_path)
    assert result.returncode != 0
    assert result.stdout == ""
    assert "RuntimeError: probe failed" in result.stderr


def test_unknown_control_has_no_observation_when_the_process_exits_early(tmp_path: Path) -> None:
    project(tmp_path, "import os\nos._exit(0)\n")
    result = probe(tmp_path)
    assert result.returncode == 0
    assert result.stdout == ""


def test_source_change_invalidates_the_test_snapshot(tmp_path: Path) -> None:
    before = project(tmp_path, "from sample.core import plan\n")
    result = probe(tmp_path)
    assert result.returncode == 0, result.stderr
    (tmp_path / "sample/facade.py").write_text(
        "from sample.drivers.sql import connect\n", encoding="utf-8"
    )
    assert source_digest(tmp_path) != before
