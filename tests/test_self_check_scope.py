# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The scope comparison and the summary use the same inputs."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

from test_self_check_gate import FIXTURES, GATE, ROOT, gate, git, keep_base


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
        assert done.returncode == 0 and "grown 0" in done.stdout, done.stdout


def test_summary_and_gate_agree_on_the_scan_table(tmp_path: Path) -> None:
    repo = tmp_path
    git(repo, "init", "-q")
    (repo / "native").mkdir()
    (repo / "native/stub").write_text("")
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
    assert ratchet(own, compared, repo)[1] == 0
    (repo / "native/archkeel.toml").write_text('[scan]\nroots = ["src"]\n')
    done = gate(repo, "base.json")
    assert done.returncode == 1 and "grown 1" in done.stdout
    assert ratchet(own, compared, repo)[1] == 1
