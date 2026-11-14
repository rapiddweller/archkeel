# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The release core serves mounted trees through the default command path."""

import hashlib
import html
import json
import os
from pathlib import Path
from time import time_ns

import pytest
from core_support import HONEST, case_root, run
from test_cli_core_only_scan import command

from archkeel.cli import core_only
from archkeel.cli.native_scan import exchange


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value))


def tree(root: Path) -> None:
    path = root / "architecture-contract.json"
    document = json.loads(path.read_text())
    document["components"][0]["inside"] = "inside.json"
    write(path, document)
    component = {**document["components"][0], "id": "INNER", "label": "inner"}
    component["inside"] = "deep.json"
    rule = {**document["rules"][1], "id": "INNER-ASSIGN", "source": "app.src.a"}
    write(root / "inside.json", {**document, "components": [component], "rules": [rule]})
    component = {**component, "id": "LEAF", "label": "leaf"}
    component.pop("inside")
    write(root / "deep.json", {**document, "components": [component], "rules": [rule]})


def test_html_report_keeps_tree_binding_and_lists_escaped_contract_file_identity(
    release_core: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        leaf = 'deep<script>"&.json'
        (root / "deep.json").rename(root / leaf)
        inside = json.loads((root / "inside.json").read_text())
        inside["components"][0]["inside"] = leaf
        write(root / "inside.json", inside)
        monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
        target = tmp_path / "tree.html"
        code, result = run("report", "--root", str(root), "--output", str(target))
        assert (code, result["status"], result["frame"]["status"]) == (0, "PASS", "PASS"), result
        files = result["frame"]["self_test"]["collect"]["contract_files"]
        assert files == {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in ("architecture-contract.json", "inside.json", leaf)
        }
        page = target.read_text()
        assert page.count(f"<h1>Verdict: {result['frame']['status']}</h1>") == 1
        identity = page.split("<h2>Request identity</h2>", 1)[1].split("<h2>Tool</h2>", 1)[0]
        for name, digest in files.items():
            assert html.escape(json.dumps(name), quote=True) in identity
            assert digest in identity
        assert "<script>" not in page


@pytest.mark.parametrize("verb", ["validate", "report"])
@pytest.mark.parametrize(
    "case,status,code",
    [("pass", "PASS", 0), ("nested", "FAIL", 1), ("root", "FAIL", 1), ("unknown", "UNKNOWN", 2)],
)
def test_two_mount_levels_keep_each_verdict_and_exit(
    release_core: Path, verb: str, case: str, status: str, code: int
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        path = root / ("architecture-contract.json" if case == "root" else "deep.json")
        document = json.loads(path.read_text())
        if case in {"root", "nested"}:
            document["components"] = document["components"][:1] if case == "root" else []
        if case == "unknown":
            document["components"][0]["packages"] = ["app.src.a", "app.src.b"]
        write(path, document)
        for form in ("--json", "--text"):
            done = command(release_core, root, form, verb=verb)
            assert done.returncode == code, done.stdout + done.stderr
            if form == "--json":
                result = json.loads(done.stdout)
                assert result["status"] == status and result["exit_code"] == code
                if case == "pass":
                    assert result["frame"]["rules"]["a:inner:INNER-ASSIGN"][1] == "PASS"
                    assert result["frame"]["self_test"]["collect"]["contract_files"] == {
                        name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                        for name in ("architecture-contract.json", "inside.json", "deep.json")
                    }
            else:
                assert f"{verb}: {status}" in done.stdout


@pytest.mark.parametrize(
    "fault",
    [
        "outside",
        "absolute",
        "colon",
        "link",
        "directory-link",
        "outside-link",
        "cycle",
        "missing",
        "malformed",
        "bytes",
    ],
)
def test_an_invalid_mount_never_gives_pass(release_core: Path, tmp_path: Path, fault: str) -> None:
    with case_root(HONEST) as root:
        tree(root)
        path = root / "inside.json"
        document = json.loads(path.read_text())
        reference = {
            "outside": "../outside.json",
            "absolute": str(tmp_path / "outside.json"),
            "colon": "unsafe:name.json",
            "cycle": "architecture-contract.json",
        }.get(fault, "deep.json")
        document["components"][0]["inside"] = reference
        write(path, document)
        leaf = root / "deep.json"
        if fault in {"link", "directory-link", "outside-link"}:
            target = (tmp_path if fault == "outside-link" else root) / "target.json"
            target.write_bytes(leaf.read_bytes())
            leaf.unlink()
            if fault == "directory-link":
                (root / "linked").symlink_to(root, target_is_directory=True)
                document["components"][0]["inside"] = "linked/target.json"
                write(path, document)
            else:
                leaf.symlink_to(target)
        elif fault == "missing":
            leaf.unlink()
        elif fault == "malformed":
            leaf.write_text("{")
        elif fault == "bytes":
            leaf.write_bytes(b" " * ((64 << 20) + 1))
        for verb, form in (("validate", "--json"), ("report", "--text")):
            done = command(release_core, root, form, verb=verb)
            assert done.returncode == 2, done.stdout + done.stderr
            assert "PASS" not in done.stdout
            if form == "--json":
                result = json.loads(done.stdout)
                assert result["status"] == "UNKNOWN" and result["exit_code"] == 2
                assert (
                    result.get("refusal")
                    or result["gaps"]
                    or result["frame"]["self_test"]["contract"].get("missing")
                )


@pytest.mark.parametrize("when", ["before-read", "backdated-write", "after-read", "replay"])
def test_a_nested_only_change_refuses_the_frame(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    when: str,
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
        # Keep HEAD and dirty unchanged across the replay.
        (root / "untracked").write_text("dirty")
        original = (root / "architecture-contract.json").read_bytes()
        saved: tuple[bytes, int] | None = None

        def changed(binary: str, kind: str, payload: bytes) -> tuple[bytes, int]:
            nonlocal saved
            path = root / "deep.json"
            if when in {"before-read", "backdated-write"}:
                before = path.stat()
                path.write_bytes(path.read_bytes() + b"\n")
                if when == "backdated-write":
                    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
            answer = saved or exchange(binary, kind, payload)
            if when == "after-read":
                path.write_bytes(path.read_bytes() + b"\n")
            saved = answer
            return answer

        monkeypatch.setattr(core_only, "exchange", changed)
        if when == "replay":
            assert core_only.run(["validate", "--root", str(root), "--json"]) == 0
            capsys.readouterr()
            path = root / "deep.json"
            path.write_bytes(path.read_bytes() + b"\n")
        assert core_only.run(["validate", "--root", str(root), "--json"]) == 2
        result = json.loads(capsys.readouterr().out)
        assert result["refusal"]["kind"] == "request_mismatch"
        assert "deep.json" in result["refusal"]["message"]
        assert (root / "architecture-contract.json").read_bytes() == original


@pytest.mark.parametrize("verb", ["validate", "report"])
@pytest.mark.parametrize("changed", [False, True])
def test_a_future_mtime_keeps_the_digest_check(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    verb: str,
    changed: bool,
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        monkeypatch.setattr(core_only, "locate_core", lambda: release_core)
        saved: tuple[bytes, int] | None = None

        def remembered(binary: str, kind: str, payload: bytes) -> tuple[bytes, int]:
            nonlocal saved
            saved = exchange(binary, kind, payload)
            return saved

        monkeypatch.setattr(core_only, "exchange", remembered)
        arguments = [verb, "--root", str(root), "--json"]
        assert core_only.run(arguments) == 0
        capsys.readouterr()
        path = root / "deep.json"
        if changed:
            path.write_bytes(path.read_bytes() + b"\n")
            monkeypatch.setattr(core_only, "exchange", lambda *_: saved)
        future = time_ns() + 86_400_000_000_000
        os.utime(path, ns=(future, future))
        for _ in range(2):
            assert core_only.run(arguments) == (2 if changed else 0)
            result = json.loads(capsys.readouterr().out)
            if changed:
                assert result["refusal"]["kind"] == "request_mismatch"
                assert (
                    "nested contract digest or byte limit differs: deep.json"
                    in result["refusal"]["message"]
                )
            else:
                assert result["status"] == "PASS"


@pytest.mark.parametrize(
    "fault", ["no-list", "missing-root", "wrong-root", "wrong-nested", "unsafe", "removed", "link"]
)
def test_the_binding_refuses_incomplete_or_changed_file_identity(
    release_core: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    with case_root(HONEST) as root:
        tree(root)
        monkeypatch.setattr(core_only, "locate_core", lambda: release_core)

        def planted(binary: str, kind: str, payload: bytes) -> tuple[bytes, int]:
            stdout, code = exchange(binary, kind, payload)
            frame = json.loads(stdout)
            files = frame["self_test"]["collect"]["contract_files"]
            if fault == "no-list":
                frame["self_test"]["collect"].pop("contract_files")
            elif fault == "missing-root":
                files.pop("architecture-contract.json")
            elif fault in {"wrong-root", "wrong-nested"}:
                files["architecture-contract.json" if fault == "wrong-root" else "deep.json"] = (
                    "0" * 64
                )
            elif fault == "unsafe":
                files["../outside.json"] = "0" * 64
            else:
                path = root / "deep.json"
                path.unlink()
                if fault == "link":
                    path.symlink_to(root / "inside.json")
            return json.dumps(frame).encode(), code

        monkeypatch.setattr(core_only, "exchange", planted)
        assert core_only.run(["report", "--root", str(root), "--json"]) == 2
        result = json.loads(capsys.readouterr().out)
        assert result["status"] == "UNKNOWN"
        assert result["refusal"]["kind"] == "request_mismatch"
