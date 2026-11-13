# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Fail-closed command mapping, command scope and binary lookup."""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from archkeel.cli import core_binary, core_only, native_scan
from archkeel.cli.core_frame import CoreError, RefusalKind, Status

HEAD = "a" * 40
OLD_STAGE_ONE_VARIABLE = "ARCHKEEL_NATIVE_CORE"


@pytest.mark.parametrize(
    "gap",
    [
        None,
        {},
        [{"kind": "source"}],
        [
            {
                "kind": "source",
                "subjects": [1],
                "reason": "unreadable",
                "evidence": [],
            }
        ],
    ],
)
def test_malformed_collection_gap_metadata_refuses(gap: object) -> None:
    from archkeel.cli.core_frame import read_frame

    document = json.loads(frame())
    document["collection_gaps"] = gap
    with pytest.raises(CoreError):
        read_frame(json.dumps(document).encode(), 0, scan=True, require_protocol=True)


def frame(status: Status = Status.PASS) -> bytes:
    return json.dumps(
        {
            "protocol": "archkeel-core-frame-1",
            "engine": "archkeel-core " + "a" * 64,
            "contract_digest": hashlib.sha256(b"contract").hexdigest(),
            "status": status,
            "rules": {"R1": ["forbidden_dependency", status]},
            "explained": {"R1": "pair gap at app.a -> app.b (src/a.ts:4)"}
            if status is Status.UNKNOWN
            else {},
            "violations": {"R1": 1} if status is Status.FAIL else {},
            "details": {
                "R1": [
                    {
                        "source": "app.a",
                        "target": "app.b",
                        "evidence": ["E1"],
                        "cause": "forbidden dependency",
                    }
                ]
            }
            if status is Status.FAIL
            else {},
            "locations": {"E1": {"path": "src/a.ts", "line": 4}},
            "beyond": {},
            "scope": "complete",
            "sections": {},
            "unknown_kinds": {"R1": "scope_incomplete"} if status is Status.UNKNOWN else {},
            "unsupported": {"rules": {}, "sections": {}, "report": None},
            "self_test": {
                "contract": {"rules": {"R1": "forbidden_dependency"}},
                "reply": {"files": 2},
                "collect": {
                    "request": {
                        "snapshot": {"root": str(Path.cwd()), "git_head": HEAD, "dirty": False}
                    }
                },
            },
        }
    ).encode()


@pytest.fixture(autouse=True)
def no_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(core_only.VARIABLE, raising=False)
    monkeypatch.delenv(OLD_STAGE_ONE_VARIABLE, raising=False)
    monkeypatch.setattr(core_only, "identity", lambda _: (HEAD, False))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "archkeel.toml").write_text('[scan]\ncontract = "contract.json"\n')
    (tmp_path / "contract.json").write_bytes(b"contract")


@pytest.mark.parametrize("variable", [core_only.VARIABLE, OLD_STAGE_ONE_VARIABLE])
@pytest.mark.parametrize("value", ["1", "0", "wrong"])
def test_an_old_engine_variable_selects_nothing(
    variable: str,
    value: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv(variable, value)
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(), 0))
    assert core_only.run(["validate", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == Status.PASS
    assert core_only.run(["check", "--json"]) == 2
    refusal = json.loads(capsys.readouterr().out)["refusal"]
    assert refusal["kind"] == RefusalKind.NOT_ON_THIS_LINE


@pytest.mark.parametrize("command", ["validate", "report"])
def test_the_stage_one_switch_is_refused_by_name(
    command: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_binary() -> Path:
        pytest.fail("a refused option must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    assert core_only.run([command, "--native-core", "--json"]) == 2
    refusal = json.loads(capsys.readouterr().out)["refusal"]
    assert refusal["kind"] == RefusalKind.NOT_ON_THIS_LINE
    assert "--native-core" in refusal["message"] and "4.0.1" in refusal["message"]


@pytest.mark.parametrize("fault", ["git_head", "dirty", "no-claim"])
def test_a_frame_of_another_commit_or_work_tree_state_is_refused(
    fault: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-430: the shell states the commit and the dirty state that it read. A frame that names
    another one answers another tree, so it is no verdict of this request."""
    claims = {"git_head": ("b" * 40, False), "dirty": (HEAD, True), "no-claim": None}
    monkeypatch.setattr(core_only, "identity", lambda _: claims[fault])
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(), 0))
    assert core_only.run(["validate", "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == Status.UNKNOWN
    assert result["refusal"]["kind"] == RefusalKind.REQUEST_MISMATCH


@pytest.mark.parametrize(
    "status,expected", [(Status.PASS, 0), (Status.FAIL, 1), (Status.UNKNOWN, 2)]
)
def test_frame_status_not_core_exit_selects_command_exit(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: Status,
    expected: int,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(status), 0))
    assert core_only.run(["validate", "--json"]) == expected
    assert json.loads(capsys.readouterr().out)["status"] == status


def test_text_names_each_failure_cause_edge_location_and_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(Status.FAIL), 0))
    assert core_only.run(["validate", "--text"]) == 1
    text = capsys.readouterr().out
    for word in ("R1", "forbidden dependency", "app.a -> app.b", "src/a.ts:4", "Action:"):
        assert word in text


def test_text_names_each_unknown_kind_cause_location_and_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(Status.UNKNOWN), 0))
    assert core_only.run(["validate", "--text"]) == 2
    text = capsys.readouterr().out
    for word in ("R1", "scope_incomplete", "pair gap", "src/a.ts:4", "Action:"):
        assert word in text


def test_an_unported_rule_names_its_missing_kind(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = json.loads(frame())
    document["status"] = "UNKNOWN"
    document["unsupported"]["rules"] = {"R2": "unsupported: rule kind symbol_placement"}
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (json.dumps(document).encode(), 3))
    assert core_only.run(["validate", "--text"]) == 2
    text = capsys.readouterr().out
    assert "R2: UNKNOWN: rule kind not decided by the core" in text
    assert "symbol_placement" in text and "Action:" in text


@pytest.mark.parametrize(
    "fault", ["empty", "bad-json", "protocol", "signal", "nonzero", "missing", "timeout"]
)
def test_a_failed_exchange_never_falls_back_or_passes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fault: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))

    def exchange(*_: object) -> tuple[bytes, int]:
        if fault in {"missing", "timeout"}:
            raise CoreError(fault)
        if fault == "protocol":
            return frame().replace(b"archkeel-core-frame-1", b"wrong-protocol"), 0
        return {
            "empty": (b"", 0),
            "bad-json": (b"broken", 0),
            "signal": (b"", -9),
            "nonzero": (b"", 7),
        }[fault]

    monkeypatch.setattr(core_only, "exchange", exchange)
    assert core_only.run(["validate", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == Status.UNKNOWN


@pytest.mark.skipif(os.name == "nt", reason="this executable test uses a POSIX shebang")
@pytest.mark.parametrize(
    "action", ["empty", "bad-json", "protocol", "signal", "nonzero", "timeout", "collector"]
)
def test_real_process_faults_are_typed_refusals(
    action: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    actions = {
        "empty": "pass",
        "bad-json": "print('broken')",
        "protocol": f"print({frame().replace(b'archkeel-core-frame-1', b'wrong').decode()!r})",
        "signal": "os.kill(os.getpid(), signal.SIGTERM)",
        "nonzero": "sys.exit(7)",
        "timeout": "time.sleep(60)",
        "collector": "sys.stderr.write('parse_work_limit: src/a.ts'); sys.exit(2)",
    }
    binary = tmp_path / "core"
    binary.write_text(f"#!{sys.executable}\nimport os, signal, sys, time\n" + actions[action])
    binary.chmod(0o755)
    monkeypatch.setattr(core_only, "locate_core", lambda: binary)
    if action == "timeout":
        monkeypatch.setattr(native_scan, "TIMEOUT_SECONDS", 0.05)
    assert core_only.run(["validate", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == Status.UNKNOWN


@pytest.mark.parametrize("kind", list(core_only.CheckKind))
@pytest.mark.parametrize(
    "flags",
    [
        [],
        [
            "--baseline",
            "b",
            "--expectation-commit",
            "e",
            "--head",
            "h",
            "--expected",
            "expectation.json",
            "--expected-digest",
            "digest",
            "--branch",
            "origin/feature",
            "--accepted-branch",
            "origin/main",
            "--host-records",
            "host.json",
        ],
    ],
)
def test_each_mandatory_merge_check_is_named_without_a_scan(
    kind: core_only.CheckKind,
    flags: list[str],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_binary() -> Path:
        pytest.fail("a refused check must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    assert core_only.run(["check", "--json", *flags]) == 2
    result = json.loads(capsys.readouterr().out)
    assert kind in result["refusal"]["message"] and "#1103" in result["refusal"]["message"]


@pytest.mark.parametrize("command", ["validate", "report"])
@pytest.mark.parametrize("option", sorted(core_only.REMOVED_OPTIONS))
def test_each_option_of_the_release_line_refuses_by_name(
    command: str,
    option: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_binary() -> Path:
        pytest.fail("a refused option must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    for flags in ([option], [option, "value"], [f"{option}=value"]):
        assert core_only.run([command, "--json", *flags]) == 2
        refusal = json.loads(capsys.readouterr().out)["refusal"]
        assert refusal["kind"] == RefusalKind.NOT_ON_THIS_LINE
        assert f"{command} {option} is not available" in refusal["message"]
        assert "use release 4.0.1" in refusal["message"] and "#880" in refusal["message"]


@pytest.mark.parametrize(
    "arguments",
    [["nothing"], ["validate", "--unknown"], ["validate", "extra"], ["--json", "validate"]],
)
def test_an_unknown_command_or_argument_is_invalid_input(
    arguments: list[str], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_binary() -> Path:
        pytest.fail("an invalid command line must not start the core")

    monkeypatch.setattr(core_only, "locate_core", no_binary)
    assert core_only.run([*arguments, "--json"]) == 2
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == Status.UNKNOWN
    assert result["refusal"]["kind"] == RefusalKind.INVALID_INPUT


def test_lookup_uses_checkout_or_verified_installed_layout(tmp_path: Path) -> None:
    package = tmp_path / "src" / "archkeel"
    crate = tmp_path / "native" / "core"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").touch()
    source = tmp_path / "native" / "target" / "release" / "archkeel-core"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source")
    assert core_binary.locate_core(package) == source
    installed = package / "_native" / "archkeel-core"
    installed.parent.mkdir(parents=True)
    installed.write_bytes(b"installed")
    with pytest.raises(CoreError, match="missing"):
        core_binary.locate_core(package)
    digest = installed.with_name(installed.name + ".sha256")
    digest.write_text(hashlib.sha256(installed.read_bytes()).hexdigest())
    assert core_binary.locate_core(package) == installed
    installed.write_bytes(b"changed")
    with pytest.raises(CoreError, match="digest"):
        core_binary.locate_core(package)
