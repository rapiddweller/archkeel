# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The scope comparison and the summary use the same inputs."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from test_self_check_gate import FIXTURES, GATE, ROOT, gate, git, keep_base, with_topology


def test_a_root_contract_edit_is_growth_without_a_topology_change(tmp_path: Path) -> None:
    base = with_topology(json.loads((FIXTURES / "base.json").read_text()))
    pr = json.loads(json.dumps(base))
    pr["frame"]["contract_digest"] = "b" * 64
    paths = []
    for name, result in (("base", base), ("pr", pr)):
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(result))
        paths.append(str(path))
    done = subprocess.run(
        [sys.executable, str(ROOT / "tools/self_check_diff.py"), *paths],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert done.returncode == 1 and "scope changed" in done.stdout, done.stdout


def test_inside_contract_is_part_of_the_fingerprint(tmp_path: Path) -> None:
    sys.path.insert(0, str(GATE.parent))
    from self_check_contract import normalize_contract

    root = tmp_path / "root.json"
    child = tmp_path / "child.json"
    root.write_text(json.dumps({"components": [{"id": "c", "inside": "child.json"}]}))
    child.write_text(json.dumps({"components": [], "rules": [{"kind": "layer_order"}]}))
    inputs = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (root, child)}
    before = {"scope": {"contract": inputs["root.json"]}, "contract_files": dict(inputs)}
    normalize_contract(before, tmp_path)
    child.write_text(json.dumps({"components": [], "rules": [{"kind": "interface_boundary"}]}))
    inputs["child.json"] = hashlib.sha256(child.read_bytes()).hexdigest()
    after = {"scope": {"contract": inputs["root.json"]}, "contract_files": dict(inputs)}
    normalize_contract(after, tmp_path)
    assert before["scope"]["contract"] != after["scope"]["contract"]


def test_unreadable_contract_uses_all_recorded_inputs(tmp_path: Path) -> None:
    sys.path.insert(0, str(GATE.parent))
    from self_check_contract import normalize_contract

    digest = "a" * 64
    before = {"scope": {"contract": digest}, "contract_files": {"root.json": digest, "in": "one"}}
    after = {"scope": {"contract": digest}, "contract_files": {"root.json": digest, "in": "two"}}
    normalize_contract(before, tmp_path)
    normalize_contract(after, tmp_path)
    assert before["scope"]["contract"] != after["scope"]["contract"]


def test_offline_base_override_uses_the_same_fallback(tmp_path: Path) -> None:
    git(tmp_path, "init", "-q")
    (tmp_path / "native").mkdir()
    (tmp_path / "native/stub").write_text("")
    shutil.copy2(FIXTURES / "tiny/architecture-contract.json", tmp_path)
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "base")
    base = keep_base(tmp_path, "base.json", "")
    done = gate(tmp_path, "base.json", base="missing-ref", BASE_RESULT=str(base))
    assert done.returncode == 0 and "grown 0" in done.stdout, done.stdout
    own = json.loads((tmp_path / "test-artifacts/selfcheck/result.json").read_text())
    compared = json.loads((tmp_path / "test-artifacts/selfcheck/compared-base.json").read_text())
    assert own["contract_normalized"] == compared["contract_normalized"] == "inputs"


@pytest.mark.parametrize("change", ["layer", "order", "public", "format"])
def test_contract_changes_with_real_core(tmp_path: Path, release_core: Path, change: str) -> None:
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "tiny", project)
    (project / "native").mkdir()
    (project / "native/stub").write_text("")
    git(project, "init", "-q")
    path = project / "architecture-contract.json"
    contract = json.loads(path.read_text())
    first = contract["components"][0]
    first.update(packages=["inventory.inventory.stock"], public=[], layer="L2")
    second = json.loads(json.dumps(first))
    second.update(
        id="COMP-RESERVATION",
        label="reservation",
        packages=["inventory.inventory.reservation"],
        layer="L2" if change in ("public", "format") else "L1",
        requires=[
            {
                "component": "inventory",
                "rationale": "Stock is used.",
                "through": ["inventory.inventory.stock"],
            }
        ],
    )
    contract["components"].append(second)
    contract["schema_version"] = "3.22.0"
    contract["rules"] = [
        {
            "id": "LO",
            "kind": "layer_order",
            "layers": ["L1", "L2"],
            "rationale": "Layers control dependency direction.",
            "provenance": ["docs/architecture/inventory.md"],
            "decided_by": "architect",
        }
    ]
    paths = []
    statuses = []
    for revision in ("base", "pr"):
        if revision == "pr":
            if change == "layer":
                second["layer"] = "L2"
            elif change == "order":
                contract["rules"][0]["layers"].reverse()
            elif change == "public":
                first["public"].append("inventory.inventory.stock")
            else:
                contract["components"].reverse()
        path.write_text(
            json.dumps(contract, indent=2 if revision == "pr" else None, sort_keys=revision == "pr")
        )
        git(project, "add", "-A")
        git(project, "commit", "-qm", revision)
        request = {
            "protocol": "archkeel-core-scan-1",
            "root": str(project.resolve()),
            "config": "archkeel.toml",
            "topology": True,
        }
        run = subprocess.run(
            [str(release_core), "scan"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=120,
        )
        frame = json.loads(run.stdout)
        assert frame["rules"], frame
        statuses.append(frame["rules"]["LO"][1])
        result = {
            "frame": frame,
            "gaps": frame["gaps"],
            "exit_code": {"PASS": 0, "FAIL": 1, "UNKNOWN": 2}[frame["status"]],
        }
        file = tmp_path / f"{revision}.json"
        file.write_text(json.dumps(result))
        paths.append(file)
    done = subprocess.run(
        [sys.executable, str(GATE), "--result", str(paths[1]), "--base", "HEAD~1"],
        cwd=project,
        env={**os.environ, "BASE_RESULT": str(paths[0])},
        capture_output=True,
        text=True,
        timeout=120,
    )
    if change == "format":
        assert done.returncode == 0 and "grown 0" in done.stdout, done.stdout
    else:
        assert done.returncode == 1 and "scope changed" in done.stdout, done.stdout
    if change in ("layer", "order"):
        assert statuses == ["FAIL", "PASS"]
    sys.path.insert(0, str(GATE.parent))
    from self_check_diff import condense

    cached = condense(json.loads(paths[0].read_text()), git(project, "rev-parse", "HEAD~1"))
    cache = project / "test-artifacts/selfcheck/base.json"
    cache.write_text(json.dumps(cached))
    env = {key: value for key, value in os.environ.items() if key != "BASE_RESULT"}
    cached_run = subprocess.run(
        [sys.executable, str(GATE), "--result", str(paths[1]), "--base", "HEAD~1"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert "cache hit" in cached_run.stdout, cached_run.stdout
    assert cached_run.returncode == done.returncode, cached_run.stdout
    assert ("scope changed" in cached_run.stdout) == (change != "format"), cached_run.stdout


def test_public_and_requires_edits_with_real_core(tmp_path: Path, release_core: Path) -> None:
    project = tmp_path / "project"
    shutil.copytree(FIXTURES / "tiny", project)
    (project / "native").mkdir()
    (project / "native/stub").write_text("")
    git(project, "init", "-q")
    contract_file = project / "architecture-contract.json"
    contract = json.loads(contract_file.read_text())
    first = contract["components"][0]
    first["packages"] = ["inventory.inventory.stock"]
    first["public"] = []
    second = json.loads(json.dumps(first))
    second["id"] = "COMP-RESERVATION"
    second["label"] = "reservation"
    second["packages"] = ["inventory.inventory.reservation"]
    contract["components"].append(second)
    contract["rules"][0]["kind"] = "no_component_cycles"
    results = []
    for name in ("base", "public", "requires"):
        if name == "public":
            first["public"] = ["inventory.inventory.stock"]
        if name == "requires":
            first["requires"] = [
                {
                    "component": "reservation",
                    "rationale": "Reservation is used by inventory.",
                    "through": ["inventory.inventory.reservation"],
                }
            ]
        contract_file.write_text(json.dumps(contract))
        git(project, "add", "-A")
        git(project, "commit", "-qm", name)
        request = {
            "protocol": "archkeel-core-scan-1",
            "root": str(project.resolve()),
            "config": "archkeel.toml",
            "topology": True,
        }
        run = subprocess.run(
            [str(release_core), "scan"],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=120,
        )
        frame = json.loads(run.stdout)
        assert frame["status"] in ("PASS", "UNKNOWN") and frame["rules"], frame
        result = {
            "frame": frame,
            "gaps": frame["gaps"],
            "exit_code": 0 if frame["status"] == "PASS" else 2,
        }
        path = tmp_path / f"{name}.json"
        path.write_text(json.dumps(result))
        results.append(path)
    for result in results[1:]:
        done = subprocess.run(
            [sys.executable, str(ROOT / "tools/self_check_diff.py"), str(results[0]), str(result)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert done.returncode == 1 and "scope changed" in done.stdout, done.stdout


def test_summary_and_gate_agree_on_the_scan_table(tmp_path: Path) -> None:
    repo = tmp_path
    git(repo, "init", "-q")
    (repo / "native").mkdir()
    (repo / "native/stub").write_text("")
    shutil.copy2(FIXTURES / "tiny/architecture-contract.json", repo)
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "base")
    (repo / "other").write_text("")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "head")
    (repo / "native/archkeel.toml").write_text('[scan]\nroots = ["native"]\n')
    base_path = keep_base(repo, "base.json", git(repo, "rev-parse", "HEAD~1"))
    base = json.loads(base_path.read_text())
    base["scan"] = {"roots": ["native"]}
    base_path.write_text(json.dumps(base))
    done = gate(repo, "base.json")
    assert done.returncode == 0 and "grown 0" in done.stdout
    sys.path.insert(0, str(GATE.parent))
    from self_check_summary import ratchet

    own = json.loads((repo / "input-result.json").read_text())
    compared = repo / "test-artifacts/selfcheck/compared-base.json"
    kept = repo / "test-artifacts/selfcheck/result.json"
    assert ratchet(own, compared, repo, kept)[1] == 0
    (repo / "native/archkeel.toml").write_text('[scan]\nroots = ["src"]\n')
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "grown 1" in done.stdout
    assert ratchet(own, compared, repo, kept)[1] == 1
