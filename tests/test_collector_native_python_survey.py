# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native import survey equals the survey of the Python collector (AD-334, slice 1c-2a).

The oracle is the unmodified `collect.collect` in the phase `imports`, encoded as the facts of
protocol 9. Slice 1c-2a compares the static imports, the file facts and their evidence. The
`stable_bindings` of a file fact follow in slice 1c-2b and are not compared yet; the binary still
refuses each request, so no reply can carry them. `ARCHKEEL_PYTHON_SCOPE_CORPORA` names more
trees, as in `test_collector_native_python_scope.py`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_collector_native_python_scope import _FIXTURES

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.analyzer.python.collect import collect
from archkeel.cli.config import load_config
from archkeel.ir import facts_codec
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    ProtocolVersion,
    PythonCollectionPhase,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

ROOT = Path(__file__).parents[1]


def _request(
    root: Path, roots: tuple[str, ...], namespace: str, exclude: bool
) -> CollectionRequest:
    return CollectionRequest(
        SnapshotInput(str(root.resolve()), "a" * 40, False),
        SourceScope(roots, namespace, exclude),
        PythonSettings(phase=PythonCollectionPhase.IMPORTS),
        ProtocolVersion.V9,
    )


def _without_stable_bindings(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {key: value for key, value in item.items() if key != "stable_bindings"} for item in files
    ]


def _python(request: CollectionRequest) -> dict[str, Any]:
    facts = collect(request)
    version = ProtocolVersion.V9
    payload = facts_codec._facts_payload(
        facts, version, facts_codec._runtime_payload(facts.runtime, version)
    )
    imports = next(item["records"] for item in payload["sections"] if item["name"] == "imports")
    cited = {item["evidence_id"] for item in payload["files"]}
    cited.update(evidence for item in imports for evidence in item["evidence_ids"])
    return {
        "files": _without_stable_bindings(payload["files"]),
        "imports": imports,
        "evidence": [item for item in payload["evidence"] if item["id"] in cited],
    }


def _native(binary: Path, request: CollectionRequest) -> dict[str, Any]:
    block = interpreter()
    assert not isinstance(block, CollectionError), block
    completed = subprocess.run(
        [str(binary), "--dump-survey"],
        input=python_request(request, block),
        capture_output=True,
        check=True,
    )
    found: dict[str, Any] = json.loads(completed.stdout)
    found["files"] = _without_stable_bindings(found["files"])
    return found


def _text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _equal(binary: Path, root: Path, roots: tuple[str, ...], namespace: str) -> None:
    for exclude in (False, True):
        request = _request(root, roots, namespace, exclude)
        expected, found = _python(request), _native(binary, request)
        for section in ("files", "imports", "evidence"):
            assert _text(found[section]) == _text(expected[section]), (root, exclude, section)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")
    return root


_EDGES = {
    "pyproject.toml": "[project]\nname = 'x'\n",
    "src/app/__init__.py": "from . import sub\nfrom .sub import f as g\n__all__ = ['sub']\n",
    "src/app/sub.py": "'''doc'''\nimport os, os.path as p\n__all__ = ('p',)\n",
    "src/app/guard.py": (
        "import typing\nif typing.TYPE_CHECKING:\n    from app import sub\n"
        "elif x:\n    import a.b\n"
        "else:\n    from .. import far\ndef f():\n    from m import *\nclass C:\n    import c\n"
    ),
    "src/app/lines.py": "x = 'é'; import os  \t\r\nfrom a import (b,\r    c)\nimport d \x0c\n",
    "src/app/empty.py": "",
    "src/app/blank/__init__.py": "\n\nimport os\n",
    "src/app/getattr/__init__.py": "def __getattr__(name): pass\nsub = 1\n",
    "src/app/getattr/sub.py": "from app.getattr import sub\nfrom . import sub as s2\n",
    "src/app/broken.py": "import os\ndef (:\n",
    "src/app/fmt.py": "import shadowed\n",
    "src/app/fmt/__init__.py": "from app.fmt import fmt\n",
    "src/app/test_x.py": "import os\n",
}


def test_the_edge_cases_have_the_python_survey(tmp_path: Path, python_dump_binary: Path) -> None:
    root = _tree(tmp_path / "repo", _EDGES)
    _equal(python_dump_binary, root, ("src",), "app")


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_each_fixture_has_the_python_survey(fixture: str, python_dump_binary: Path) -> None:
    root = ROOT / fixture
    config = load_config(root)
    _equal(python_dump_binary, root, config.roots, config.namespace)


def test_the_archkeel_source_has_the_python_survey(python_dump_binary: Path) -> None:
    _equal(python_dump_binary, ROOT, ("src",), "archkeel")


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PYTHON_SCOPE_CORPORA"), reason="no corpus is named"
)
def test_each_named_corpus_has_the_python_survey(python_dump_binary: Path) -> None:
    for entry in os.environ["ARCHKEEL_PYTHON_SCOPE_CORPORA"].split(";"):
        root, namespace, roots = entry.split("=")
        _equal(python_dump_binary, Path(root), tuple(roots.split(",")), namespace)
