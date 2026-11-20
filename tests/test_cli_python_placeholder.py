# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""An empty function body is visible even when another form remains unread."""

import subprocess
import sys
from pathlib import Path

import pytest
from test_cli_boundary_types import use_standard_library_premise
from test_cli_native_python_imports import project, rows, verdict
from test_cli_python_profile_limits import CONSTRUCT, Plant, scanned

PLACEHOLDER = {**CONSTRUCT, "id": "NO-PLACEHOLDER", "constructs": ["placeholder_body"]}


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("def check():\n    return 1\n", "PASS"),
        ("def check():\n    pass\n", "FAIL"),
        ("def check():\n    ...\n", "FAIL"),
        ("def check():\n    'documentation'\n", "FAIL"),
        ("def check():\n    'documentation'\n    pass\n", "FAIL"),
        ("def check():\n    'documentation'\n    ...\n", "FAIL"),
        ("def check():\n    raise UnknownError\n", "UNKNOWN"),
        ("class P:\n    def check(self): ...\n", "FAIL"),
        (
            "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
            "class C(P):\n    pass\n",
            "PASS",
        ),
        ("from typing import Protocol as P\nclass C(P):\n    def check(self): ...\n", "PASS"),
        ("import typing as t\nclass C(t.Protocol):\n    def check(self): pass\n", "PASS"),
        (
            "from typing import Protocol\nclass C(Protocol):\n    def check(self): 'doc'\n",
            "PASS",
        ),
        (
            "from typing import Protocol\nclass C(Protocol):\n    def check(self): ...\n"
            "    def check(self): return 1\n",
            "UNKNOWN",
        ),
        (
            "import typing\ntyping.Protocol = object\nfrom typing import Protocol\n"
            "class C(Protocol):\n    def check(self): ...\n",
            "UNKNOWN",
        ),
        (
            "import foreign\nfrom typing import Protocol\n"
            "class C(Protocol):\n    def check(self): ...\n",
            "UNKNOWN",
        ),
        (
            "class C(Protocol):\n    def check(self): ...\nfrom typing import Protocol\n",
            "UNKNOWN",
        ),
        ("from other import Base\nclass C(Base):\n    def check(self): ...\n", "UNKNOWN"),
        ("from abc import abstractmethod\n@abstractmethod\ndef check(): ...\n", "UNKNOWN"),
        ("from typing import overload\n@overload\ndef check(): ...\n", "UNKNOWN"),
        ("class C:\n    @staticmethod\n    def check(): ...\n", "FAIL"),
        ("def check(): ...\ndef check(): return 1\n", "UNKNOWN"),
        ("from other import deco\n@deco\ndef check(): ...\n", "UNKNOWN"),
    ],
)
def test_placeholder_bodies_require_complete_candidate_evidence(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    path = project(tmp_path, {"src/app/client/page.py": source}, contract_rules=[PLACEHOLDER])
    use_standard_library_premise(path)
    result = verdict(release_core, path)
    assert rows(result)["NO-PLACEHOLDER"] == expected, result["frame"]


@pytest.mark.parametrize(
    ("prefix", "additional"),
    [
        ("", {"src/typing.py": "Protocol = object\n"}),
        ("", {"src/app/unread.py": "def (:\n"}),
        (
            "from app.helper import patch\npatch()\n",
            {"src/app/helper.py": "import typing\ndef patch(): typing.Protocol = object\n"},
        ),
        (
            "from colorsys import patch\npatch()\n",
            {"src/colorsys.py": "import typing\ndef patch(): typing.Protocol = object\n"},
        ),
    ],
)
def test_unread_or_shadowed_inputs_hold_placeholder_absence(
    release_core: Path, tmp_path: Path, prefix: str, additional: dict[str, str]
) -> None:
    source = prefix + "from typing import Protocol\nclass C(Protocol):\n    def check(self): ...\n"
    path = project(
        tmp_path,
        {"src/app/client/page.py": source, **additional},
        contract_rules=[PLACEHOLDER],
    )
    if prefix:
        witness = (
            "import sys; sys.path.insert(0, 'src'); import app.client.page; "
            "import typing; print(typing.Protocol is object)"
        )
        live = subprocess.run(
            [sys.executable, "-I", "-c", witness],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        assert live.stdout.strip() == "True"
    use_standard_library_premise(path)
    result = verdict(release_core, path)
    assert rows(result)["NO-PLACEHOLDER"] == "UNKNOWN", result["frame"]


def test_protocol_exemption_requires_and_reports_the_standard_library_premise(
    release_core: Path, tmp_path: Path
) -> None:
    source = "from typing import Protocol\nclass C(Protocol):\n    def check(self): ...\n"
    path = project(tmp_path, {"src/app/client/page.py": source}, contract_rules=[PLACEHOLDER])
    held = verdict(release_core, path)
    assert rows(held)["NO-PLACEHOLDER"] == "UNKNOWN"
    assert "standard_library_unchanged" in held["frame"]["explained"]["NO-PLACEHOLDER"]
    use_standard_library_premise(path)
    decided = verdict(release_core, path)
    assert rows(decided)["NO-PLACEHOLDER"] == "PASS"
    assert decided["frame"]["premises"]["NO-PLACEHOLDER"] == [
        {"kind": "standard_library_unchanged", "subject": "app"}
    ]


def test_a_protocol_body_is_a_declaration() -> None:
    source = (
        "from typing import Protocol\nclass P(Protocol):\n    def check(self): ...\n"
        "class C(P):\n    pass\nprint(P._is_protocol)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", source], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "True"


@pytest.mark.parametrize(
    ("prefix", "is_builtin"),
    [
        ("", True),
        ("class NotImplementedError(ValueError): pass\n", False),
        ("NotImplementedError = ValueError\n", False),
        ("import builtins\nbuiltins.NotImplementedError = ValueError\n", False),
    ],
)
def test_raise_name_needs_builtin_identity(
    release_core: Path, tmp_path: Path, prefix: str, is_builtin: bool
) -> None:
    source = prefix + "def check():\n    raise NotImplementedError\n"
    witness = (
        "import builtins\noriginal = builtins.NotImplementedError\n"
        + source
        + "try:\n    check()\nexcept Exception as error:\n"
        + "    print(type(error) is original)\n"
    )
    done = subprocess.run(
        [sys.executable, "-c", witness], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == str(is_builtin)
    rule = {**CONSTRUCT, "id": "NO-PLACEHOLDER", "constructs": ["placeholder_body"]}
    result = scanned(
        release_core, tmp_path, Plant({"src/app/client/page.py": source}, [rule], [], {}, {})
    )
    assert rows(result)["NO-PLACEHOLDER"] == "UNKNOWN", result["frame"]
