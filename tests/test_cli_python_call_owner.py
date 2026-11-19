# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The call-owner rule uses a proved target, not a call candidate."""

import subprocess
import sys
from pathlib import Path

import pytest
from core_support import ROOT
from test_cli_native_python_imports import verdict

from tools.fixture_tree import fixture_tree

DEMO = ROOT / "fixtures/python-newer-syntax-demo"
RULE = "CALL-PURGE-MAINTENANCE-ONLY"


def test_nested_generator_keeps_the_forbidden_call_beside_open_calls(release_core: Path) -> None:
    result = verdict(release_core, DEMO, "report")
    frame = result["frame"]
    assert frame["rules"].get(RULE) == ["call_owner", "FAIL"], frame["gaps"]
    assert frame["rules"]["CONSTRUCT-EXACT-TYPE-IGNORE"] == ["forbidden_construct", "PASS"]
    assert frame["measures"]["unresolved_attribute"] == 1
    [detail] = frame["details"][RULE]
    assert detail["target"] == "sample.maintenance.purge"
    assert {"path": "sample/report.py", "line": 9} in [
        frame["locations"][site] for site in detail["evidence"]
    ]
    assert result["exit_code"] == 1


@pytest.mark.parametrize("case", ["allowed", "callback", "provider"])
def test_call_owner_distinguishes_allowed_and_open_origins(release_core: Path, case: str) -> None:
    with fixture_tree(DEMO) as root:
        provider = root / "sample/maintenance.py"
        with provider.open("a", encoding="utf-8") as stream:
            stream.write(
                "\n\ndef readable(cell): return True\n"
                "\n\ndef purge_owned(cell): return purge(cell)\n"
            )
        if case == "provider":
            (root / "sample/__init__.py").write_text(
                "from importlib import import_module\n"
                'key = "sample.maintenance"\n'
                'provider = import_module(key + "")\n'
                "provider.purge = lambda cell: False\n",
                encoding="utf-8",
            )
            witness = "assert m.purge.__name__ == '<lambda>'; assert summarize([[None]]) == [False]"
        else:
            legacy = root / "sample/legacy.py"
            legacy.write_bytes(
                legacy.read_bytes().replace(
                    b"handle.close()  # type: ignore[attr-defined]", b"return None"
                )
            )
            if case == "allowed":
                source = (
                    "from sample.maintenance import readable\n"
                    "def summarize(rows):\n"
                    "    return [[readable(cell) for cell in row] for row in rows]\n"
                )
                witness = "assert summarize([[None]]) == [[True]]; assert m.purge_owned(None)"
            else:
                source = "def summarize(rows, purge): return [purge(row[0]) for row in rows]\n"
                witness = (
                    "assert summarize([[1]], m.purge) == [False]; "
                    "assert summarize([[1]], m.readable) == [True]"
                )
            (root / "sample/report.py").write_text(source, encoding="utf-8")
        subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                "from sample import maintenance as m; from sample.report import summarize; "
                + witness,
            ],
            cwd=root,
            check=True,
        )
        frame = verdict(release_core, root, "report")["frame"]
    expected = "PASS" if case == "allowed" else "UNKNOWN"
    assert frame["rules"].get(RULE) == ["call_owner", expected], frame["gaps"]
    assert not frame["violations"].get(RULE)
