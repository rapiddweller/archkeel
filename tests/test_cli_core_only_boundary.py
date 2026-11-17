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

from archkeel.cli import core_arguments, core_binary, core_only, core_text, native_scan
from archkeel.cli.core_exit import Outcome
from archkeel.cli.core_frame import CoreError, RefusalKind, Status

HEAD = "a" * 40
EXIT = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}
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


def _read(document: dict) -> object:
    from archkeel.cli.core_frame import read_frame

    return read_frame(json.dumps(document).encode(), 0, scan=True, require_protocol=True)


def test_a_frame_may_state_the_assumption_of_its_collector() -> None:
    document = json.loads(frame())
    document["premise"] = "code outside the scan roots hands in no global object"
    assert _read(document).premise == document["premise"]
    document["premises"] = ["a second word is no field"]
    with pytest.raises(CoreError):
        _read(document)


@pytest.mark.parametrize("value", [1, True, None, ["a"], {"a": "b"}, "", "  "])
def test_a_premise_that_is_no_text_is_refused(value: object) -> None:
    document = json.loads(frame())
    document["premise"] = value
    with pytest.raises(CoreError):
        _read(document)


# The resolver of each language whose collector states a premise, in the form of the frame schema.
RESOLVERS = {
    "typescript": {"language": "typescript", "tsconfig": "tsconfig.json"},
    "python": {
        "language": "python",
        "phase": "imports",
        "interpreter": {
            "version": "3.12.10",
            "stdlib_module_names": [],
            "builtin_module_names": [],
        },
    },
}


@pytest.mark.parametrize("language", sorted(RESOLVERS))
def test_a_scan_frame_of_a_language_with_a_premise_must_state_it(language: str) -> None:
    document = json.loads(frame())
    document["self_test"]["collect"]["request"]["resolver"] = RESOLVERS[language]
    with pytest.raises(CoreError):
        _read(document)
    document["premise"] = "code outside the scan roots hands in no global object"
    assert _read(document).premise is not None


@pytest.mark.parametrize("status", [Status.PASS, Status.FAIL, Status.UNKNOWN])
def test_the_text_verdict_prints_the_assumption(
    status: Status, capsys: pytest.CaptureFixture[str]
) -> None:
    document = json.loads(frame(status))
    document["premise"] = "code outside the scan roots hands in no global object"
    lines = core_text.render("validate", _read(document), EXIT[status], outcome=Outcome.VERDICT)
    print("\n".join(lines))
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith(f"validate: {status} -> exit {EXIT[status]} (")
    assert "Assumption: code outside the scan roots hands in no global object" in lines


def _stated_once_frame() -> dict:
    document = json.loads(frame(Status.UNKNOWN))
    places = {f"E{n}": {"path": f"src/u{n}.ts", "line": n} for n in range(1, 8)}
    document["locations"].update(places)
    document["collection_gaps"] = [
        {
            "kind": "source_resolution_gap",
            "subjects": ["app.a"],
            "reason": "A form that can write any global keeps every free name from a proof",
            "evidence": list(places),
            "detail": "7 uses of 2 free standard names depend on it",
        }
    ]
    return document


def test_a_collection_gap_may_carry_a_detail_and_the_text_names_it_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    lines = core_text.render("validate", _read(_stated_once_frame()), 2, outcome=Outcome.VERDICT)
    print("\n".join(lines))
    text = capsys.readouterr().out
    assert text.count("7 uses of 2 free standard names depend on it") == 1
    assert "src/u1.ts:1" in text and "source_resolution_gap" not in text


@pytest.mark.parametrize("detail", [1, ["a"], None, {"a": 1}])
def test_a_collection_gap_detail_that_is_no_text_is_refused(detail: object) -> None:
    document = _stated_once_frame()
    document["collection_gaps"][0]["detail"] = detail
    with pytest.raises(CoreError):
        _read(document)


def test_a_collection_gap_has_no_other_extra_field() -> None:
    document = _stated_once_frame()
    document["collection_gaps"][0]["note"] = "x"
    with pytest.raises(CoreError):
        _read(document)


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
            "gaps": [],
            "collection_gaps": [],
            "measures": None,
            "self_test": {
                "contract": {"rules": {"R1": "forbidden_dependency"}},
                "reply": {"files": 2},
                "collect": {
                    "contract_files": {"contract.json": hashlib.sha256(b"contract").hexdigest()},
                    "request": {
                        "protocol_version": "9.0.0",
                        "snapshot": {"root": str(Path.cwd()), "git_head": HEAD, "dirty": False},
                        "scope": {
                            "roots": ["src"],
                            "namespace": "app",
                            "exclude_test_sources": False,
                        },
                        "resolver": {"language": "rust"},
                    },
                },
            },
        }
    ).encode()


def test_call_measure_is_checked_before_the_frame_is_accepted() -> None:
    from archkeel.cli.core_frame import read_frame

    document = json.loads(frame())
    measure = dict.fromkeys(
        (
            "calls_total",
            "calls_resolved",
            "calls_partial",
            "calls_builtin",
            "calls_external",
            "calls_unresolved",
            "unresolved_self",
            "unresolved_attribute",
            "unresolved_name",
            "unresolved_dynamic",
            "typing_positions",
            "untyped_private_accesses",
        ),
        0,
    )
    document["measures"] = measure
    read_frame(json.dumps(document).encode(), 0, scan=True, require_protocol=True)
    measure["calls_unresolved"] = 1
    with pytest.raises(CoreError, match="inconsistent call measures"):
        read_frame(json.dumps(document).encode(), 0, scan=True, require_protocol=True)


@pytest.fixture(autouse=True)
def no_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(core_arguments._VARIABLE, raising=False)
    monkeypatch.delenv(OLD_STAGE_ONE_VARIABLE, raising=False)
    monkeypatch.setattr(core_only, "identity", lambda _: (HEAD, False))
    monkeypatch.chdir(tmp_path)
    (tmp_path / "archkeel.toml").write_text('[scan]\ncontract = "contract.json"\n')
    (tmp_path / "contract.json").write_bytes(b"contract")


@pytest.mark.parametrize("variable", [core_arguments._VARIABLE, OLD_STAGE_ONE_VARIABLE])
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
    assert "--native-core" in refusal["message"] and "no release has it" in refusal["message"]


@pytest.mark.parametrize("fault", ["git_head", "dirty", "no-claim"])
def test_a_frame_of_another_commit_or_work_tree_state_is_refused(
    fault: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-432: the shell states the commit and the dirty state that it read. A frame that names
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
    for word in ("R1", "forbidden dependency", "app.a -> app.b", "src/a.ts:4", "Next:"):
        assert word in text


def test_text_names_each_unknown_kind_cause_location_and_action(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (frame(Status.UNKNOWN), 0))
    assert core_only.run(["validate", "--text"]) == 2
    text = capsys.readouterr().out
    for word in ("R1", "pair gap", "src/a.ts:4", "Next:"):
        assert word in text
    assert "scope_incomplete" not in text


def test_an_unported_rule_names_its_missing_kind(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    document = json.loads(frame())
    document["status"] = "UNKNOWN"
    reason = "unsupported: rule kind symbol_placement"
    document["unsupported"]["rules"] = {"R2": reason}
    document["gaps"] = [{"kind": "rule_kind_not_ported", "subject": "R2", "reason": reason}]
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (json.dumps(document).encode(), 3))
    assert core_only.run(["validate", "--text"]) == 2
    text = capsys.readouterr().out
    assert "R2" in text and "rule kind that the core does not decide yet" in text
    assert "symbol_placement" in text and "Next:" in text and "rule_kind_not_ported" not in text


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
        monkeypatch.setattr(native_scan, "_TIMEOUT_SECONDS", 0.05)
    assert core_only.run(["validate", "--json"]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == Status.UNKNOWN


def test_lookup_uses_checkout_or_verified_installed_layout(tmp_path: Path) -> None:
    package = tmp_path / "src" / "archkeel"
    crate = tmp_path / "native" / "core"
    crate.mkdir(parents=True)
    (crate / "Cargo.toml").touch()
    (tmp_path / "pyproject.toml").touch()
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


@pytest.mark.parametrize("layout", ["site-packages", "no pyproject.toml", "no core crate"])
def test_lookup_uses_the_build_output_only_from_a_real_checkout(
    tmp_path: Path, layout: str
) -> None:
    """AD-436: an installed package has no checkout, so a build output beside it never runs."""
    package = tmp_path / ("lib" if layout == "site-packages" else "src") / "archkeel"
    built = tmp_path / "native" / "target" / "release" / "archkeel-core"
    built.parent.mkdir(parents=True)
    built.write_bytes(b"planted")
    if layout != "no core crate":
        (tmp_path / "native" / "core").mkdir()
        (tmp_path / "native" / "core" / "Cargo.toml").touch()
    if layout != "no pyproject.toml":
        (tmp_path / "pyproject.toml").touch()
    with pytest.raises(core_binary.CoreBinaryNotFound, match="holds no core binary"):
        core_binary.locate_core(package)
