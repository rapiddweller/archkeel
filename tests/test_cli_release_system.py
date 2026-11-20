# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""A final release needs every rule of the bound system to pass."""

import copy
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from archkeel.cli.native_scan import identity
from tools import release_system


@pytest.fixture
def evidence(tmp_path):
    document = {
        "kind": "system",
        "title": "System",
        "rules": [],
        "parts": [
            {"id": "one", "config": "one.toml"},
            {"id": "two", "config": "two.toml"},
        ],
    }
    (tmp_path / "system.json").write_text(json.dumps(document))
    for part in document["parts"]:
        name = part["id"]
        (tmp_path / part["config"]).write_text(f'[scan]\ncontract = "{name}.json"\n')
        (tmp_path / f"{name}.json").write_text(
            json.dumps({"components": [], "rules": [{"id": name, "kind": "test"}]})
        )
    binary = tmp_path / "_native" / "archkeel-core"
    binary.parent.mkdir()
    binary.write_bytes(b"core")
    wheel = tmp_path / "candidate.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("archkeel/_native/archkeel-core", b"core")
    files = {
        name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
        for name in ("system.json", "one.json", "two.json")
    }
    frame = {
        "engine": "archkeel-core 1",
        "contract_digest": files["system.json"],
        "rules": {"one": ["test", "PASS"], "two": ["test", "PASS"]},
        "system": {
            "document": "system.json",
            "parts": [
                {"id": part["id"], "config": part["config"], "rules": [part["id"]]}
                for part in document["parts"]
            ],
        },
        "self_test": {
            "collect": {
                "contract_files": files,
                "request": {
                    "snapshot": {"root": str(tmp_path), "git_head": "a" * 40, "dirty": False}
                },
            }
        },
        "premises": {"one": [{"kind": "external", "subject": "client"}]},
        "assuming": "external client",
    }
    return tmp_path, wheel, {"core": {"path": str(binary)}, "frame": frame}


def check(evidence):
    root, wheel, result = evidence
    return release_system.check(result, root, "system.json", wheel, "a" * 40)


def test_complete_evidence(evidence):
    assert check(evidence) == []


def test_a_real_dirty_checkout_is_refused(evidence):
    root, wheel, result = evidence
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "init",
        ],
        cwd=root,
        check=True,
    )
    clean = identity(root)
    assert clean is not None and clean[1] is False
    snapshot = result["frame"]["self_test"]["collect"]["request"]["snapshot"]
    snapshot["git_head"] = clean[0]
    assert release_system.check(result, root, "system.json", wheel, clean[0]) == []
    (root / "untracked-source.py").write_text("pass\n")
    dirty = identity(root)
    assert dirty == (clean[0], True)
    snapshot["dirty"] = dirty[1]
    assert release_system.check(result, root, "system.json", wheel, clean[0]) == [
        "snapshot differs"
    ]


@pytest.mark.parametrize(
    "change",
    [
        "missing",
        "duplicate",
        "foreign",
        "wrong_part",
        "unknown",
        "fail",
        "commit",
        "dirty",
        "contract",
        "core",
    ],
)
def test_bad_evidence_is_refused(evidence, change):
    root, wheel, original = evidence
    result = copy.deepcopy(original)
    frame = result["frame"]
    if change == "missing":
        del frame["rules"]["one"]
    elif change == "duplicate":
        frame["system"]["parts"][0]["rules"].append("one")
    elif change == "foreign":
        frame["rules"]["foreign"] = ["test", "PASS"]
    elif change == "wrong_part":
        frame["system"]["parts"][0]["rules"] = ["two"]
    elif change in ("unknown", "fail"):
        frame["rules"]["one"][1] = change.upper()
    elif change == "commit":
        frame["self_test"]["collect"]["request"]["snapshot"]["git_head"] = "b" * 40
    elif change == "dirty":
        frame["self_test"]["collect"]["request"]["snapshot"]["dirty"] = True
    elif change == "contract":
        (root / "one.json").write_text("{}")
    else:
        Path(result["core"]["path"]).write_bytes(b"other")
    assert release_system.check(result, root, "system.json", wheel, "a" * 40)


def test_duplicate_json_keys_are_refused():
    with pytest.raises(ValueError, match="duplicate"):
        release_system.loads('{"rules":{"one":1,"one":2}}')


def test_final_check_blocks_publication():
    workflow = Path(".github/workflows/release.yml").read_text()
    assert workflow.index("python3 -m tools.release_system") < workflow.index(
        "name: Upload distributions"
    )
    assert "publish:\n    needs: build" in workflow
    assert '"${RELEASE_TAG#v}" == "5.0.0"' in workflow


def test_a_different_checkout_commit_never_starts_the_wheel(evidence, monkeypatch):
    root, wheel, _ = evidence
    monkeypatch.chdir(root)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="b" * 40)

    monkeypatch.setattr(release_system.subprocess, "run", run)
    assert release_system.main(wheel, "a" * 40) == 2
    assert len(commands) == 1


def test_candidate_run_keeps_the_frame_and_uses_an_isolated_install(evidence, monkeypatch):
    root, wheel, result = evidence
    monkeypatch.chdir(root)
    commands = []

    def run(command, **kwargs):
        commands.append((command, kwargs))
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 0, stdout="a" * 40)
        return subprocess.CompletedProcess(command, 0, stdout=json.dumps(result))

    monkeypatch.setattr(release_system.subprocess, "run", run)
    monkeypatch.setattr(release_system, "SYSTEM", "system.json")
    assert release_system.main(wheel, "a" * 40) == 0
    assert json.loads((root / "test-artifacts/release-system.json").read_text()) == result
    command, options = commands[1]
    assert command[:5] == ["uv", "run", "--isolated", "--no-project", "--with"]
    assert command[5] == str(wheel)
    assert options["cwd"] != str(root)
    assert "PYTHONPATH" not in options["env"]
