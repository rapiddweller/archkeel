# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-664: the declared reach of a door site, through the release core.

Consumer: a CI job that reads the row of each rule and the exit code. A door (`eval` of a text
that the scan cannot see) holds each rule but the rules on the files. A contract can declare the
modules that one door may load or change. A matched declaration lets the rules decide, and each
PASS that the door would hold says "PASS assuming the declared reach"; a declared load is a real
edge; a declaration that matches no door is a problem and applies nothing. Python runs the truth
of each door: the text that the door runs can load the module that a rule forbids.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_cli_native_python_imports import command, project, rows, verdict
from test_cli_python_gap_effects import BINDS_SECRET, FILES, ON_FILES, RULES

# The door: the module evaluates a text of the environment when it is imported (line 2).
DOOR = "import os\nVALUE = eval(os.environ.get('DOOR', '1'))\n"
# The text that gives the name `app.service.model` the secret module.
SWAP = (
    "__import__('sys').modules.__setitem__('app.service.model', "
    "__import__('app.service.secret', fromlist=['KEY']))"
)
SITE = "D-EVAL (app.service.model:2 eval)"
GIT = {
    **os.environ,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t",
}


def declaration(**fields: Any) -> dict[str, Any]:
    return {
        "id": "D-EVAL",
        "module": "app.service.model",
        "door": "eval",
        "line": 2,
        "loads": [],
        "rationale": "The text is a formula of numbers.",
        "provenance": ["p"],
        **fields,
    }


def scanned(
    binary: Path,
    root: Path,
    files: dict[str, str],
    declared: list[dict[str, Any]],
    *,
    version: str = "3.15.0",
) -> dict[str, Any]:
    """The verdict of the project with `files` and the door declarations `declared`."""
    project(root, {**FILES, **files}, contract_rules=RULES)
    path = root / "architecture-contract.json"
    contract = json.loads(path.read_text())
    contract["schema_version"] = version
    contract["declarations"] = {"door_reach": declared}
    path.write_text(json.dumps(contract))
    subprocess.run(["git", "-C", str(root), "commit", "-qam", "reach"], check=True, env=GIT)
    return verdict(binary, root)


def truth(root: Path, door: str, code: str) -> str:
    """What Python prints for `code` when the door runs the text `door`."""
    done = subprocess.run(
        [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, 'src'); {code}"],
        cwd=root,
        env={**os.environ, "DOOR": door},
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_an_undeclared_door_keeps_each_rule_but_the_files_unknown(
    release_core: Path, tmp_path: Path
) -> None:
    result = scanned(release_core, tmp_path, {"src/app/service/model.py": DOOR}, [])
    expected = {rule["id"]: "PASS" if rule["id"] in ON_FILES else "UNKNOWN" for rule in RULES}
    assert rows(result) == expected, result
    assert "assumed" not in result["frame"] and "door_reach" not in result["frame"]
    # The door is real: the text gives the client the secret module.
    assert truth(tmp_path, SWAP, BINDS_SECRET) == "True"


def test_a_matched_declaration_passes_each_rule_only_as_an_assumption(
    release_core: Path, tmp_path: Path
) -> None:
    result = scanned(release_core, tmp_path, {"src/app/service/model.py": DOOR}, [declaration()])
    assert set(rows(result).values()) == {"PASS"}, result
    frame = result["frame"]
    # No PASS that the door could change is a plain PASS: each one names the door site.
    assumed = {rule["id"] for rule in RULES} - set(ON_FILES)
    assert frame["assumed"] == dict.fromkeys(sorted(assumed), [SITE]), frame["assumed"]
    assert frame["door_reach"] == [
        {
            "id": "D-EVAL",
            "module": "app.service.model",
            "line": 2,
            "door": "eval",
            "loads": [],
            "changes": [],
        }
    ]
    assert result["status"] == "PASS" and result["exit_code"] == 0
    text = command(release_core, tmp_path, "--text").stdout
    assert "all 7 rules pass; 5 pass assuming the declared reach of 1 door" in text, text
    assert "D-EVAL: app.service.model:2 (eval) loads nothing; changes nothing" in text, text
    # The premise is the claim of the contract, not a proof: the same door can break it.
    assert truth(tmp_path, SWAP, BINDS_SECRET) == "True"


def test_a_declared_load_is_a_real_edge_that_a_rule_can_forbid(
    release_core: Path, tmp_path: Path
) -> None:
    files = {"src/app/client/page.py": "import app.service.model as model\n" + DOOR}
    door = declaration(module="app.client.page", line=3, loads=["app.service.secret"])
    result = scanned(release_core, tmp_path, files, [door])
    assert rows(result)["CLIENT-NO-SECRET"] == "FAIL", result
    details = result["frame"]["details"]["CLIENT-NO-SECRET"]
    assert result["frame"]["door_reach"][0]["possible_loads"] == ["app.service.secret"]
    assert {(row["source"], row["target"]) for row in details} == {
        ("app.client.page", "app.service.secret")
    }, details
    # The door can load what the declaration names.
    load = "import app.client.page, sys; print('app.service.secret' in sys.modules)"
    assert truth(tmp_path, "__import__('app.service.secret')", load) == "True"


def test_a_declaration_that_matches_no_door_is_reported_and_applies_nothing(
    release_core: Path, tmp_path: Path
) -> None:
    result = scanned(
        release_core, tmp_path, {"src/app/service/model.py": DOOR}, [declaration(line=3)]
    )
    expected = {rule["id"]: "PASS" if rule["id"] in ON_FILES else "UNKNOWN" for rule in RULES}
    assert rows(result) == expected, result
    assert "assumed" not in result["frame"] and "door_reach" not in result["frame"]
    kinds = {gap["kind"] for gap in result["gaps"]}
    assert "door_reach.unmatched" in kinds, result["gaps"]
    (gap,) = [gap for gap in result["gaps"] if gap["kind"] == "door_reach.unmatched"]
    assert "D-EVAL" in gap["subject"] and "not applied" in gap["reason"], gap
    assert result["exit_code"] == 2


def test_a_loader_needs_a_declaration_of_its_binding_and_of_its_call(
    release_core: Path, tmp_path: Path
) -> None:
    loader = (
        "from importlib import import_module\n"
        "def load(name):\n"
        "    return import_module('app.service.' + name)\n"
    )
    files = {"src/app/service/model.py": loader}
    binding = declaration(id="D-BIND", door="loader", line=1, loads=["app.service"])
    call = declaration(id="D-CALL", door="loader", scope="load", loads=["app.service"])
    del call["line"]
    only_call = scanned(release_core, tmp_path / "a", files, [call])
    assert rows(only_call)["CYCLES"] == "UNKNOWN", only_call
    both = scanned(release_core, tmp_path / "b", files, [binding, call])
    assert set(rows(both).values()) == {"PASS"}, both
    assert {door["id"] for door in both["frame"]["door_reach"]} == {"D-BIND", "D-CALL"}
    # A module that imports the bound door runs it outside its module: the binding is refused.
    files["src/app/service/other.py"] = "from app.service.model import import_module as f\n"
    refused = scanned(release_core, tmp_path / "c", files, [binding, call])
    kinds = {gap["kind"] for gap in refused["gaps"]}
    assert "door_reach.invalid" in kinds, refused["gaps"]
    assert rows(refused)["CYCLES"] == "UNKNOWN", refused


@pytest.mark.parametrize(
    ("constant", "edit", "status"),
    [
        ("MODULES = ('model',)\n", "", "PASS"),
        ("MODULES = ('secret',)\n", "", "FAIL"),
        ("MODULES = ('model', 'gone')\n", "", "UNKNOWN"),
        ("MODULES = ('model',)\nMODULES = ('secret',)\n", "", "UNKNOWN"),
        ("MODULES = ['model']\n", "", "UNKNOWN"),
        ("MODULES = ('model',)\n", "stale", "UNKNOWN"),
        ("MODULES = ('model',)\n", "same-line", "UNKNOWN"),
    ],
)
def test_a_python_loader_bound_reads_the_written_tuple_again(
    release_core: Path, tmp_path: Path, constant: str, edit: str, status: str
) -> None:
    call = 'importlib.import_module(f"app.service.{names[0]}")'
    actual = call.replace("names[0]", "names[-1]") if edit == "stale" else call
    if edit == "same-line":
        actual = f"({call}, importlib.import_module(names[-1]))"
    source = (
        "import importlib\n"
        "from app.service.registry import MODULES\n"
        "def load(names=MODULES):\n"
        f"    return {actual}\n"
    )
    door = declaration(module="app.client.page", door="loader", line=4)
    door.pop("loads")
    door["loads_from"] = {
        "constant": "app.service.registry:MODULES",
        "template": "app.service.{}",
        "call": call,
    }
    files = {"src/app/client/page.py": source, "src/app/service/registry.py": constant}
    if status == "FAIL":
        path = "src/app/service/secret.py"
        files[path] = "import app.client.page\n" + FILES[path]
    result = scanned(
        release_core,
        tmp_path,
        files,
        [door],
        version="3.18.0",
    )
    assert rows(result)["CLIENT-NO-SECRET"] == status, result
    frame = result["frame"]
    if status == "UNKNOWN":
        assert "door_reach" not in frame
        problem = "ambiguous" if edit == "same-line" else "invalid"
        assert any(gap["kind"] == f"door_reach.{problem}" for gap in result["gaps"])
    else:
        (bound,) = frame["door_reach"]
        assert bound["constant"] == (
            "app.service.registry:MODULES (src/app/service/registry.py:1, template app.service.{})"
        )
        target = "model" if status == "PASS" else "secret"
        assert bound["possible_loads"] == [f"app.service.{target}"]
    if status == "PASS":
        assert (
            "loads only the targets from app.service.registry:MODULES"
            in frame["assumed"]["CLIENT-NO-SECRET"][0]
        )
        assert "only the targets from app.service.registry:MODULES" in (
            command(release_core, tmp_path, "--text").stdout
        )
        page = tmp_path / "bound.html"
        command(release_core, tmp_path, "--output", str(page), verb="report")
        assert "loads only the targets from app.service.registry:MODULES" in page.read_text()
    if status == "FAIL":
        (detail,) = frame["details"]["CLIENT-NO-SECRET"]
        assert detail["possible"] is True
        assert rows(result)["CYCLES"] == "FAIL"
        report = json.loads(
            command(release_core, tmp_path, "--json", "--topology", verb="report").stdout
        )
        edges = {(edge["source"], edge["target"]) for edge in report["frame"]["topology"]["edges"]}
        assert ("app.service.secret", "app.client.page") in edges
        assert ("app.client.page", "app.service.secret") not in edges
    if status != "UNKNOWN":
        assert truth(tmp_path, "", "from app.client.page import load; print(load().__name__)") == (
            f"app.service.{target}"
        )
