# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-450: Python import rules through the release core and the default shell."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from test_cli_core_only_scan import command

RULE = {"rationale": "Keep the boundary.", "provenance": ["p"], "decided_by": "architect"}
COMPONENT = {
    "role": "component",
    "responsibilities": ["Own the modules."],
    "forbidden_responsibilities": [],
    "provenance": ["p"],
    "decided_by": "architect",
}
BASE = {
    "src/app/__init__.py": "",
    "src/app/client.py": "import os\n",
    "src/app/service.py": "VALUE = 1\n",
}


def component(
    name: str, packages: list[str], requires: list[str] = (), *, exact: bool = False
) -> dict[str, Any]:
    owned = {"exact_modules": packages, "packages": []} if exact else {"packages": packages}
    return {
        **COMPONENT,
        "id": f"COMP-{name.upper()}",
        "label": name,
        **owned,
        "requires": [{"component": other, "rationale": "Use it."} for other in requires],
    }


def rules(*, type_checking: bool = True) -> list[dict[str, Any]]:
    forbid = {"source": "app.client", "target": "app.service"}
    return [
        {
            **RULE,
            "id": "FORBID",
            "kind": "forbidden_dependency",
            **forbid,
            "include_type_checking": type_checking,
        },
        {**RULE, "id": "ASSIGN", "kind": "complete_assignment", "source": "app"},
        {**RULE, "id": "CYCLES", "kind": "no_component_cycles"},
        {**RULE, "id": "EXTERNAL", "kind": "complete_external_scope", "source": "app"},
    ]


def project(
    root: Path,
    files: dict[str, str | bytes],
    *,
    roots: str = '["src"]',
    contract_rules: list[dict[str, Any]] | None = None,
) -> Path:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode() if isinstance(text, str) else text)
    (root / "pyproject.toml").write_text('[project]\nrequires-python = ">=3.11"\n')
    (root / "archkeel.toml").write_text(
        f'[scan]\nlanguage = "python"\nroots = {roots}\nnamespace = "app"\n'
        'contract = "architecture-contract.json"\n'
    )
    contract = {
        "schema_version": "2.2.0",
        "components": [
            component("root", ["app"], exact=True),
            component("client", ["app.client"], ["service"]),
            component("service", ["app.service"]),
        ],
        "rules": rules() if contract_rules is None else contract_rules,
    }
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    return root


def verdict(binary: Path, root: Path, verb: str = "validate") -> dict[str, Any]:
    done = command(binary, root, "--json", verb=verb)
    result = json.loads(done.stdout)
    assert "refusal" not in result, (result, done.stderr)
    assert done.returncode == result["exit_code"], result
    return result


def rows(result: dict[str, Any]) -> dict[str, str]:
    return {rule: row[1] for rule, row in result["frame"]["rules"].items()}


@pytest.mark.parametrize("verb", ["validate", "report"])
def test_a_clean_project_passes_each_import_rule(
    release_core: Path, tmp_path: Path, verb: str
) -> None:
    result = verdict(release_core, project(tmp_path, BASE), verb)
    assert rows(result) == dict.fromkeys(["FORBID", "ASSIGN", "CYCLES", "EXTERNAL"], "PASS")
    assert result["status"] == "PASS" and result["exit_code"] == 0


@pytest.mark.parametrize(
    "source",
    [
        "import app.service\n",
        "from . import service\n",
        "from app.service import VALUE\n",
        "try:\n    import app.service\nexcept ImportError:\n    pass\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import app.service\n",
        "def later():\n    import app.service\n",
        "import importlib\nload = lambda: importlib.import_module('app.service')\n",
        "__import__('app.service')\n",
    ],
)
def test_a_forbidden_import_fails_and_names_its_file_and_line(
    release_core: Path, tmp_path: Path, source: str
) -> None:
    files = {**BASE, "src/app/client.py": source}
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result)["FORBID"] == "FAIL", result
    assert result["exit_code"] == 1
    frame = result["frame"]
    line = next(n for n, text in enumerate(source.splitlines(), 1) if "service" in text)
    sites = [frame["locations"][e] for d in frame["details"]["FORBID"] for e in d["evidence"]]
    assert {"path": "src/app/client.py", "line": line} in sites, frame


def test_a_type_checking_import_is_outside_a_rule_that_leaves_it_out(
    release_core: Path, tmp_path: Path
) -> None:
    source = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import app.service\n"
    files = {**BASE, "src/app/client.py": source}
    result = verdict(
        release_core, project(tmp_path, files, contract_rules=rules(type_checking=False))
    )
    assert rows(result)["FORBID"] == "PASS", result


def test_a_component_cycle_fails(release_core: Path, tmp_path: Path) -> None:
    files = {
        **BASE,
        "src/app/client.py": "import app.service\n",
        "src/app/service.py": "import app.client\n",
    }
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result)["CYCLES"] == "FAIL", result


@pytest.mark.parametrize(
    ("source", "expected"),
    [("import json\n", "PASS"), ("import requests\n", "FAIL"), ("import distutils\n", "FAIL")],
)
def test_a_standard_name_must_be_standard_in_each_supported_minor(
    release_core: Path, tmp_path: Path, source: str, expected: str
) -> None:
    files = {**BASE, "src/app/client.py": source}
    result = verdict(release_core, project(tmp_path, files))
    assert rows(result)["EXTERNAL"] == expected, result


@pytest.mark.parametrize(
    ("dependency", "source"),
    [
        ("requests", "import requests.adapters\n"),
        ("google.cloud", "from google.cloud import storage\n"),
    ],
)
def test_an_external_dependency_matches_by_module_scope(
    release_core: Path, tmp_path: Path, dependency: str, source: str
) -> None:
    rule = {
        **RULE,
        "id": "SCOPE",
        "kind": "external_dependency_scope",
        "dependency": dependency,
        "allowed_sources": ["app.service"],
    }
    files = {**BASE, "src/app/client.py": source}
    result = verdict(release_core, project(tmp_path, files, contract_rules=[rule]))
    assert rows(result) == {"SCOPE": "FAIL"}, result


GAPS = {
    "dynamic_import": {"src/app/client.py": "import importlib\nimportlib.import_module(name)\n"},
    "dynamic_import ": {"src/app/client.py": "__import__('app.' + name)\n"},
    "dynamic_import  ": {"src/app/client.py": "exec('import app.service')\n"},
    "import_system_change": {"src/app/client.py": "import sys\nsys.path.insert(0, 'x')\n"},
    "project_module_not_found": {
        "src/app/client.py": "import app.space\n",
        "src/app/space/inner.py": "",
    },
    "star_import": {"src/app/client.py": "from app import *\n"},
    "reexport_ambiguity": {
        "src/app/__init__.py": "service = 1\n",
        "src/app/client.py": "from app import service\n",
    },
    "relative_import_beyond_top": {"src/app/client.py": "from ... import other\n"},
    "exception_gap": {"src/app/client.py": "def broken(:\n"},
    "exception_gap ": {"src/app/client.py": b"x = '\xff'\n"},
    "stub_or_compiled_module": {"src/app/extra.pyi": "x: int\n"},
    "dynamic_import#submodule": {
        "src/app/client.py": "import importlib.util\nimportlib.import_module('app.service')\n"
    },
    "dynamic_import#from": {
        "src/app/client.py": "from importlib import import_module\nimport_module('app.service')\n"
    },
    "dynamic_import#computed": {
        "src/app/client.py": "import importlib\nimportlib.import_module('app.' + name)\n"
    },
    "stub_or_compiled_module ": {"src/app/fast.cpython-311-darwin.so": "\0"},
    "duplicate_module": {"lib/app/service.py": "VALUE = 2\n"},
    "module_outside_layout": {"src/app/inner/app/deep.py": ""},
    # Proof review of #1141: each plant must stay UNKNOWN.
    "dynamic_import#alias": {
        "src/app/client.py": "from importlib import import_module as load\nload('app.service')\n"
    },
    "dynamic_import#value": {
        "src/app/client.py": (
            "import importlib\nload = importlib.import_module\nload('app.service')\n"
        )
    },
    "dynamic_import#getattr": {
        "src/app/client.py": "import importlib\ngetattr(importlib, 'import_' + 'module')('x')\n"
    },
    "dynamic_import#builtins": {"src/app/client.py": "import builtins\nbuiltins.exec('x')\n"},
    "dynamic_import#runner": {"src/app/client.py": "run = exec\nrun('import app.service')\n"},
    "dynamic_import#dunder": {"src/app/client.py": "f = __import__\nf('app.service')\n"},
    "dynamic_import#pickle": {"src/app/client.py": "import pickle\npickle.loads(data)\n"},
    "dynamic_import#patch": {
        "src/app/client.py": "from unittest import mock\nmock.patch('app.service.VALUE')\n"
    },
    "dynamic_import#compile": {"src/app/client.py": "compile(text, 'f', 'exec')\n"},
    "dynamic_import#setattr": {"src/app/client.py": "import sys\nsetattr(sys, 'path', [])\n"},
    "import_system_change#alias": {"src/app/client.py": "import sys as s\ns.path.insert(0, 'x')\n"},
    "import_system_change#from": {
        "src/app/client.py": "from sys import path\npath.insert(0, 'x')\n"
    },
    "import_system_change#sort": {"src/app/client.py": "import sys\nsys.path.sort()\n"},
    "import_system_change#loop": {
        "src/app/client.py": "import sys\nfor sys.path in [['x']]:\n    pass\n"
    },
    "exception_gap#encoding": {"src/app/client.py": "# coding: utf-7\nimport os\n"},
    "project_module_not_found#from": {
        "src/app/client.py": "from app import space\n",
        "src/app/space/inner.py": "",
    },
    "project_module_not_found#relative": {
        "src/app/client.py": "from . import space\n",
        "src/app/space/inner.py": "",
    },
    "stub_or_compiled_module#pyw": {"src/app/window.pyw": "import app.service\n"},
}


@pytest.mark.parametrize("gap", sorted(GAPS))
def test_each_named_gap_gives_unknown(release_core: Path, tmp_path: Path, gap: str) -> None:
    roots = '["src", "lib"]' if gap.startswith("duplicate_module") else '["src"]'
    if gap.startswith("module_outside_layout"):
        roots = '["src/app/inner"]'
    result = verdict(release_core, project(tmp_path, {**BASE, **GAPS[gap]}, roots=roots))
    assert set(rows(result).values()) == {"UNKNOWN"}, result
    assert result["exit_code"] == 2
    assert gap.split("#")[0].strip() in json.dumps(result["frame"]), result


@pytest.mark.skipif(
    os.name != "posix" or os.geteuid() == 0, reason="needs an unprivileged POSIX user"
)
@pytest.mark.parametrize("entry", ["src/app/locked", "src/app/locked/hidden.py"])
def test_an_unreadable_entry_gives_no_pass(release_core: Path, tmp_path: Path, entry: str) -> None:
    files = {**BASE, "src/app/locked/hidden.py": "import app.service\n"}
    root = project(tmp_path, files)
    (root / entry).chmod(0)
    try:
        done = command(release_core, root, "--json")
    finally:
        (root / entry).chmod(0o755)
    result = json.loads(done.stdout)
    assert done.returncode == 2 and result["status"] == "UNKNOWN", result
    if entry.endswith(".py"):
        assert set(rows(result).values()) == {"UNKNOWN"}, result
        assert "src/app/locked/hidden.py" in json.dumps(result["frame"]["collection_gaps"])
    else:
        # The repository survey refuses a directory that it cannot list, before the collector.
        assert result["refusal"]["kind"] == "collection_refused", result


@pytest.mark.parametrize(
    "source",
    [
        "TYPE_CHECKING = False\nif TYPE_CHECKING:\n    import app.service\n",
        "from config import TYPE_CHECKING\nif TYPE_CHECKING:\n    import app.service\n",
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    import app.service\n",
        (
            "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    pass\n"
            "else:\n    import app.service\n"
        ),
    ],
)
def test_a_look_alike_type_checking_guard_is_a_runtime_edge(
    release_core: Path, tmp_path: Path, source: str
) -> None:
    files = {**BASE, "src/app/client.py": source}
    contract = rules(type_checking=False)
    result = verdict(release_core, project(tmp_path, files, contract_rules=contract))
    assert rows(result)["FORBID"] == "FAIL", result


@pytest.mark.skipif(os.name != "posix", reason="needs POSIX links")
def test_a_linked_package_directory_gives_unknown(release_core: Path, tmp_path: Path) -> None:
    files = {
        **BASE,
        "src/app/client/__init__.py": "",
        "elsewhere/sub/__init__.py": "import app.service\n",
    }
    files.pop("src/app/client.py")
    root = tmp_path / "repo"
    root.mkdir()
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    (root / "src/app/client/sub").symlink_to("../../../elsewhere/sub")
    result = verdict(release_core, project(root, {}))
    assert set(rows(result).values()) == {"UNKNOWN"}, result
    assert "linked_source" in json.dumps(result["frame"]), result


def test_a_component_outside_the_namespace_gives_no_pass(
    release_core: Path, tmp_path: Path
) -> None:
    root = project(tmp_path, BASE)
    contract = json.loads((root / "architecture-contract.json").read_text())
    contract["components"].append(component("outside", ["zzz.other"]))
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qam", "outside"],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    result = verdict(release_core, root)
    assert "PASS" not in rows(result).values(), result
    assert "outside the namespace" in result["frame"]["scope"], result


@pytest.mark.parametrize(
    "files",
    [
        {"src/app/client.py": "import importlib\nimportlib.import_module('app')\n"},
        {"src/app/client.pyi": "VALUE: int\n", "src/app/__init__.pyi": ""},
    ],
)
def test_a_proven_literal_call_or_a_stub_beside_its_source_passes(
    release_core: Path, tmp_path: Path, files: dict[str, str]
) -> None:
    result = verdict(release_core, project(tmp_path, {**BASE, **files}))
    assert set(rows(result).values()) == {"PASS"}, result


def test_a_poetry_caret_requirement_is_read(release_core: Path, tmp_path: Path) -> None:
    root = project(tmp_path, BASE)
    (root / "pyproject.toml").write_text('[tool.poetry.dependencies]\npython = "^3.9"\n')
    subprocess.run(
        ["git", "-C", str(root), "commit", "-qam", "poetry"],
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    result = verdict(release_core, root)
    assert set(rows(result).values()) == {"PASS"}, result


@pytest.mark.parametrize(
    "source",
    [
        "__import__('app.service')\n",
        "import importlib\nimportlib.import_module('app.service')\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    __import__('app.service')\n",
    ],
)
def test_a_literal_call_is_a_runtime_edge_for_a_rule_without_type_checking(
    release_core: Path, tmp_path: Path, source: str
) -> None:
    # AD-472: the guard proof covers import statements only, so a call is never type-only.
    files = {**BASE, "src/app/client.py": source}
    contract = rules(type_checking=False)
    result = verdict(release_core, project(tmp_path, files, contract_rules=contract))
    assert rows(result)["FORBID"] == "FAIL", result
