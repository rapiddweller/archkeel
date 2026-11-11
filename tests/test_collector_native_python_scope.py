# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native scope of a Python scan equals the scope of the Python collector (AD-334, 1c-1).

The oracle is the unmodified Python code: `selected_paths`, `module_for`, `package_for`, the
shadowed-module gaps of `parse_unshadowed` (#797), `collect._inputs` and `python_requirement`.
`ARCHKEEL_PYTHON_SCOPE_CORPORA` names more trees: `root=namespace=roots` entries, separated by `;`,
with the roots separated by `,`.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from archkeel.analyzer.interpreter import interpreter, python_request
from archkeel.analyzer.python.collect import _inputs
from archkeel.analyzer.python.explore_scope import parse_unshadowed, selected_paths
from archkeel.analyzer.python.source import module_for, package_for
from archkeel.analyzer.runtime import python_requirement
from archkeel.cli.config import load_config
from archkeel.ir.protocol import (
    CollectionError,
    CollectionRequest,
    ProtocolVersion,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

ROOT = Path(__file__).parents[1]
_FIXTURES = (
    "fixtures/K-python-realworld",
    "fixtures/F-architecture",
    "fixtures/H-uml",
    "fixtures/M-review-workflow",
    "fixtures/python-stdlib-demo",
    "fixtures/python-newer-syntax-demo",
    "fixtures/golden-python/synthetic-constructs",
    "fixtures/golden-python/synthetic-gaps",
    "fixtures/golden-python/synthetic-excluded-tests",
    "fixtures/golden-python/synthetic-tests-only",
    "fixtures/golden-python/fastapi-security",
    "fixtures/golden-python/fastapi-encoders",
)


def _module(rel: Path, root: Path, namespace: str) -> list[str | None]:
    try:
        module = module_for(root / rel, root=root, namespace=namespace)
    except ValueError:
        return [None, None]
    return [module, package_for(module)]


def _python(root: Path, roots: tuple[str, ...], namespace: str, exclude: bool) -> dict[str, Any]:
    root = root.resolve()
    selected = selected_paths(root, roots, exclude_test_sources=exclude)
    rels = [path.relative_to(root) for path in selected]
    shadowed = [
        {
            "file": item["data"]["file"],
            "id": item["id"],
            "title": item["title"],
            "message": item["data"]["message"],
        }
        for item in parse_unshadowed(selected, root=root, namespace=namespace).failures
        if item["kind"] == "ShadowedModule"
    ]
    inputs, digest = _inputs(root, selected)
    required, state = python_requirement(root)
    return {
        "selected": [rel.as_posix() for rel in rels],
        "modules": {rel.as_posix(): _module(rel, root, namespace) for rel in rels},
        "shadowed": shadowed,
        "inputs": [{"digest": i.digest, "path": i.path, "role": str(i.role)} for i in inputs],
        "source_digest": digest,
        "required": required,
        "requirement_state": str(state),
    }


def _native(
    binary: Path, root: Path, roots: tuple[str, ...], namespace: str, exclude: bool
) -> dict[str, Any]:
    block = interpreter()
    assert not isinstance(block, CollectionError), block
    request = CollectionRequest(
        SnapshotInput(str(root.resolve()), "a" * 40, False),
        SourceScope(roots, namespace, exclude),
        PythonSettings(),
        ProtocolVersion.V9,
    )
    completed = subprocess.run(
        [str(binary), "--dump-scope"],
        input=python_request(request, block),
        capture_output=True,
        check=True,
    )
    found: dict[str, Any] = json.loads(completed.stdout)
    for item in found["shadowed"]:
        del item["module"]
    return found


def _equal(
    binary: Path, root: Path, roots: tuple[str, ...], namespace: str, unseen: tuple[str, ...] = ()
) -> None:
    """Equal scope; `unseen` are the values that the survey turns into gaps (AD-367)."""
    for exclude in (False, True):
        expected = _python(root, roots, namespace, exclude)
        found = _native(binary, root, roots, namespace, exclude)
        assert [item["item"] for item in found.pop("unseen")] == list(unseen)
        assert found == expected, (root, exclude)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


_EDGES = {
    "src/app/__init__.py": "import os\n",
    "src/app/fmt.py": "x = 1\n",
    "src/app/fmt/__init__.py": "y = 2\n",
    "src/app/portion/mod.py": "z = 3\n",
    "src/app/portion.py": "w = 4\n",
    "src/app/a.b/c.py": "",
    "src/app/a/b.py": "",
    "src/app/.hidden/e.py": "",
    "src/app/__pycache__/f.py": "",
    "src/app/odd.py/d.py": "",
    "src/app/tests/helpers.py": "",
    "src/app/test_api.py": "",
    "src/app/api_test.py": "",
    "src/app/Upper.PY": "",
    "src/elsewhere/x.py": "",
    "src/app/bom.py": "﻿import os\n",
    # `with_suffix("")` differs by version: 3.13 refuses the stem `.`, 3.14 splits as splitext.
    "src/app/dots/..py": "",
    "src/app/dots/...py": "",
    "src/app/dots/a..py": "",
    "src/app/dots/.h.py": "",
    "src/app/real/test_a.py": "",
}


def test_the_edge_cases_and_the_shadowed_module_have_the_python_scope(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    root = _tree(tmp_path / "repo", _EDGES)
    (root / "outside.py").write_text("", encoding="utf-8")
    if os.name != "nt":
        (root / "src/app/linkdir").symlink_to("a")
        (root / "src/app/linkfile.py").symlink_to("a/b.py")
        (root / "src/app/link_test_dir").symlink_to("tests")
        (root / "src/app/outfile.py").symlink_to(tmp_path / "far.py")
        (tmp_path / "far.py").write_text("", encoding="utf-8")
        # Python selects a dangling link, and its read fails with `FileNotFoundError` (measured).
        (root / "src/app/dangling.py").symlink_to("nowhere.py")
        # Python never selects a file under `__pycache__`, a dangling link too.
        (root / "src/app/__pycache__/gone.py").symlink_to("nowhere.py")
        # A link to a test source is a test source.
        (root / "src/app/alias.py").symlink_to("real/test_a.py")
    unseen = () if os.name == "nt" else ('Missing("src/app/dangling.py")',)
    _equal(python_dump_binary, root, ("src",), "app", unseen)


def test_a_file_over_4_mib_is_named_as_unseen_and_is_the_one_difference(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    root = _tree(tmp_path / "repo", {"src/app/__init__.py": "", "src/app/big.py": "#" * (5 << 20)})
    expected = _python(root, ("src",), "app", False)
    found = _native(python_dump_binary, root, ("src",), "app", False)
    assert found.pop("unseen") == [
        {
            "item": 'Oversized("src/app/big.py")',
            "reason": "Source file over the size limit of 4194304 bytes: src/app/big.py",
        }
    ]
    # The file is no input and not in the source digest; its gap keeps the scope from PASS.
    big = next(item for item in expected["inputs"] if item["path"] == "src/app/big.py")
    expected["inputs"].remove(big)
    assert {key: found[key] for key in found if key != "source_digest"} == {
        key: expected[key] for key in expected if key != "source_digest"
    }


@pytest.mark.parametrize(
    "text",
    [
        None,
        '[project]\nrequires-python = ">=3.11"\n',
        '[project]\nrequires-python = "  "\n',
        "[project]\nrequires-python = 3\n",
        '[project]\nname = "x"\n[tool.poetry.dependencies]\npython = "^3.11.2"\n',
        '[tool.poetry.dependencies]\npython = "^03.1"\n',
        '[tool.poetry]\nname = "x"\n',
        "[project\n",
        '﻿[project]\nrequires-python = ">=3.11"\n',
        "project = 1\n",
        "a = 1\na = 2\n",
        "t = {a = 1,}\n",
        "d = 1979-05-27T07:32:00Z\n",
    ],
)
def test_the_requirement_of_pyproject_has_the_python_state(
    tmp_path: Path, python_dump_binary: Path, text: str | None
) -> None:
    root = _tree(tmp_path / "repo", {"src/app/__init__.py": ""})
    if text is not None:
        (root / "pyproject.toml").write_text(text, encoding="utf-8")
    _equal(python_dump_binary, root, ("src",), "app")


@pytest.mark.parametrize("fixture", _FIXTURES)
def test_each_fixture_has_the_python_scope(fixture: str, python_dump_binary: Path) -> None:
    root = ROOT / fixture
    config = load_config(root)
    _equal(python_dump_binary, root, config.roots, config.namespace)


def test_the_archkeel_source_has_the_python_scope(python_dump_binary: Path) -> None:
    _equal(python_dump_binary, ROOT, ("src",), "archkeel")


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PYTHON_SCOPE_CORPORA"), reason="no corpus is named"
)
def test_each_named_corpus_has_the_python_scope(python_dump_binary: Path) -> None:
    for entry in os.environ["ARCHKEEL_PYTHON_SCOPE_CORPORA"].split(";"):
        root, namespace, roots = entry.split("=")
        _equal(python_dump_binary, Path(root), tuple(roots.split(",")), namespace)
