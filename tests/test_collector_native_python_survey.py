# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native import survey equals the survey of the Python collector (AD-334, slice 1c-2a).

The oracle is the unmodified `collect.collect` in the phase `imports`, encoded as the facts of
protocol 9. The test compares the static imports, the file facts, their evidence, the import
targets, the UNKNOWN records and the coverage. A syntax failure is compared on its file and its
class only (AD-365 point 1). The `stable_bindings` of a file fact follow in slice 1c-2c and are
not compared yet; the binary still refuses each request, so no reply can carry them.
`ARCHKEEL_PYTHON_SCOPE_CORPORA` names more trees, as in `test_collector_native_python_scope.py`.
"""

from __future__ import annotations

import builtins
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from first_difference import same
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
    unknowns = next(item["records"] for item in payload["sections"] if item["name"] == "unknowns")
    return {
        "files": _without_stable_bindings(payload["files"]),
        "imports": imports,
        "evidence": [item for item in payload["evidence"] if item["id"] in cited],
        "targets": payload["imports"],
        "unknowns": unknowns,
        "coverage": payload["coverage"],
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


_PARSE_FAILURES = {"SyntaxError", "IndentationError", "TabError", "TooDeepError"}


def _closed(value: Any) -> Any:
    """Keep the file and the class of a syntax failure only (AD-365 point 1)."""
    if isinstance(value, list):
        return [_closed(item) for item in value]
    if isinstance(value, dict) and value.get("kind") in _PARSE_FAILURES and "data" in value:
        return {"kind": value["kind"], "file": value["data"]["file"]}
    if isinstance(value, dict):
        return {key: _closed(item) for key, item in value.items()}
    return value


def _text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _equal(binary: Path, root: Path, roots: tuple[str, ...], namespace: str) -> None:
    for exclude in (False, True):
        request = _request(root, roots, namespace, exclude)
        expected, found = _python(request), _native(binary, request)
        for section in ("files", "imports", "evidence", "targets", "unknowns", "coverage"):
            same(
                _text(_closed(found[section])),
                _text(_closed(expected[section])),
                (root, exclude, section),
            )


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
    "src/app/guard_elif.py": (
        "import typing\nif x:\n    import a\nelif typing.TYPE_CHECKING:\n    import b\n"
        "else:\n    import c\n"
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
    "src/app/tests/__init__.py": "",
    "src/app/tests/helpers.py": "",
    "src/app/uses_tests.py": (
        "from app.tests import helpers\nfrom app import test_x\nimport app.tests\n"
    ),
    "src/app/nul.py": "x = 1\0\n",
    "src/app/dir.py/inner.py": "import json\n",
    "src/other/outside.py": "import app\n",
}


def test_the_edge_cases_have_the_python_survey(tmp_path: Path, python_dump_binary: Path) -> None:
    root = _tree(tmp_path / "repo", _EDGES)
    (root / "src/app/latin.py").write_bytes(b"x = '\\xff'\n\xff\n")
    if os.name != "nt":
        (root / "src/app/dangling.py").symlink_to("nowhere.py")
        (root / "src/app/tests/gone_test.py").symlink_to("nowhere.py")
    _equal(python_dump_binary, root, ("src",), "app")


def test_a_scope_of_only_tests_has_the_python_gap(tmp_path: Path, python_dump_binary: Path) -> None:
    root = _tree(tmp_path / "repo", {"src/app/tests/test_a.py": "import os\n"})
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


def _gap_files(found: dict[str, Any]) -> dict[str, str]:
    return {
        item["data"]["file"]: item["kind"] for item in found["unknowns"] if "file" in item["data"]
    }


def test_a_file_over_4_mib_is_a_named_gap(tmp_path: Path, python_dump_binary: Path) -> None:
    """AD-365 point 4: the snapshot does not read the file, and the survey names it."""
    root = _tree(tmp_path / "repo", {"src/app/__init__.py": "", "src/app/big.py": "#" * (5 << 20)})
    found = _native(python_dump_binary, _request(root, ("src",), "app", False))
    assert _gap_files(found) == {"src/app/big.py": "collection_gap"}
    assert not found["coverage"]["full_scope"]


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX modes")
def _without_file(found: dict[str, Any], rel: str) -> dict[str, Any]:
    def kept(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [item for item in records if item["data"].get("file") != rel]

    coverage = {**found["coverage"], "gaps": kept(found["coverage"]["gaps"])}
    return {**found, "unknowns": kept(found["unknowns"]), "coverage": coverage}


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0, reason="needs POSIX modes")
def test_an_unreadable_file_is_a_gap_in_both_producers(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """AD-365 point 10: the file and its gap are present in both producers, and the class may
    be the base class `OSError`. The rest of the survey is equal."""
    rel = "src/app/secret.py"
    root = _tree(tmp_path / "repo", {"src/app/__init__.py": "import os\n", rel: "x = 1\n"})
    secret = root / rel
    secret.chmod(0)
    try:
        request = _request(root, ("src",), "app", False)
        expected, found = _python(request), _native(python_dump_binary, request)
    finally:
        secret.chmod(0o644)
    python_class = getattr(builtins, _gap_files(expected)[rel])
    assert issubclass(python_class, OSError)
    assert _gap_files(found)[rel] == "OSError"
    expected, found = _without_file(expected, rel), _without_file(found, rel)
    for section in ("files", "imports", "evidence", "targets", "unknowns", "coverage"):
        assert _text(found[section]) == _text(expected[section]), section
