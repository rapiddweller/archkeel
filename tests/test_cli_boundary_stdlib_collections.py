# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""#1718 (AD-782): a collection or a special form that the shape reader reads by its qualified
name (`typing.List`, `typing.Optional`) counts only under the premise `standard_library_unchanged`,
with the same check for a change in the repository as a type of the standard library.

Before #1718 the reader counted these names with no premise: a scanned `typing.List = Secret` and
`def f(a: List[int])` gave PASS, while Python binds `Secret` (the truth test below). A builtin of
the language (`list[int]`, `int | None`) reads no name of a module and needs no premise.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from boundary_types_plants import PLANTS as BOUNDARY_PLANTS
from boundary_types_plants import Plant, facade
from boundary_types_sources import RULE, project
from test_cli_boundary_types import use_standard_library_premise
from test_cli_core_only_scan import command

SECRET = {"model.py": "class Secret:\n    pass\n"}
PATCH_LIST = {
    **SECRET,
    "patch.py": "import typing\nfrom app.model import Secret\ntyping.List = Secret\n",
}

# name: (api source, extra files, row without the premise, row with it, a text that the frame holds)
PLANTS: dict[str, tuple[str, dict[str, str], str, str, str]] = {
    "typing-list": (
        facade("def f(a: List[int]) -> int:\n    return 1\n", "'f'", "from typing import List\n"),
        {},
        "UNKNOWN",
        "PASS",
        "typing.List",
    ),
    "typing-optional": (
        facade(
            "def f(a: Optional[int]) -> int:\n    return 1\n",
            "'f'",
            "from typing import Optional\n",
        ),
        {},
        "UNKNOWN",
        "PASS",
        "typing.Optional",
    ),
    "dotted-collections-abc": (
        facade(
            "def f(a: abc.Sequence[str]) -> int:\n    return 1\n",
            "'f'",
            "import collections.abc as abc\n",
        ),
        {},
        "UNKNOWN",
        "PASS",
        "collections.abc.Sequence",
    ),
    "builtin-collection-and-union": (
        facade("def f(a: list[int], b: int | None) -> dict[str, int] | None:\n    pass\n", "'f'"),
        {},
        "FAIL",
        "FAIL",
        "",
    ),
    "builtin-sequence": (
        facade("def f(a: list[int], b: int | None) -> tuple[int, ...]:\n    pass\n", "'f'"),
        {},
        "PASS",
        "PASS",
        "",
    ),
    # The false PASS of #1718: a scanned module replaces `typing.List`.
    "changed-typing-list": (
        facade("def f(a: List[int]) -> int:\n    return 1\n", "'f'", "from typing import List\n"),
        PATCH_LIST,
        "UNKNOWN",
        "UNKNOWN",
        "may change the standard library name typing.List",
    ),
    "changed-typing-optional": (
        facade(
            "def f(a: Optional[int]) -> int:\n    return 1\n",
            "'f'",
            "from typing import Optional\n",
        ),
        {"patch.py": "import typing\ntyping.Optional = dict\n"},
        "UNKNOWN",
        "UNKNOWN",
        "may change the standard library name typing.Optional",
    ),
    "list-of-a-secret": (
        facade(
            "def f(a: List[Secret]) -> int:\n    return 1\n",
            "'f'",
            "from typing import List\nfrom app.model import Secret\n",
        ),
        SECRET,
        "UNKNOWN",
        "FAIL",
        "",
    ),
}


def run(
    tmp_path: Path, core: Path, api: str, files: dict[str, str], premise: bool
) -> tuple[str, str]:
    root = project(tmp_path / "p", Plant(api, "OPEN", files=files))
    if premise:
        use_standard_library_premise(root)
    result = json.loads(command(core, root, "--json").stdout)
    assert "refusal" not in result, result
    return result["frame"]["rules"][RULE][1], json.dumps(result)


@pytest.mark.parametrize("premise", [False, True])
@pytest.mark.parametrize("name", sorted(PLANTS))
def test_a_named_collection_or_form_counts_only_under_the_premise(
    release_core: Path, tmp_path: Path, name: str, premise: bool
) -> None:
    api, files, without, with_premise, text = PLANTS[name]
    row, frame = run(tmp_path, release_core, api, files, premise)
    assert row == (with_premise if premise else without), frame
    if row == "UNKNOWN":
        assert text in frame, frame
    if row == "UNKNOWN" and not premise and not text.startswith("may change"):
        assert "standard_library_unchanged" in frame, frame
    if row == "PASS" and premise and without == "UNKNOWN":
        assert "the premise that outside code leaves the standard library unchanged" in frame, frame


# The plants of the shape reader that read a collection or a form by name keep their row under
# the premise; without it each is UNKNOWN (tests/boundary_types_rows.json).
UNDER_PREMISE = {
    "collections": "PASS",
    "dict-in-optional": "FAIL",
    "optional-and-union": "PASS",
    "literal-and-annotated": "PASS",
    "literal-of-a-member": "UNKNOWN",
}


@pytest.mark.parametrize("name", sorted(UNDER_PREMISE))
def test_the_shape_plants_keep_their_row_under_the_premise(
    release_core: Path, tmp_path: Path, name: str
) -> None:
    plant = BOUNDARY_PLANTS[name]
    row, frame = run(tmp_path, release_core, plant.api, plant.files, premise=True)
    assert row == UNDER_PREMISE[name], frame


TRUTH = """
import typing
class Secret:
    __class_getitem__ = classmethod(lambda cls, item: cls)
typing.List = Secret
from typing import List
def f(a: List[int]) -> int: return 1
print(f.__annotations__['a'] is Secret)
"""


@pytest.mark.skipif(shutil.which("python3.12") is None, reason="needs python3.12 as the truth")
def test_a_replaced_typing_list_binds_the_replacement_in_cpython() -> None:
    done = subprocess.run(
        ["python3.12", "-I", "-c", TRUTH], capture_output=True, text=True, check=True
    )
    assert done.stdout.strip() == "True"
