# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-406: with the switch, a linked `report` asks the core to run the collector itself.

The shell sends the scan request (the root, the configuration file, the Git head and dirty state)
and no reply bytes. The core derives the collection request, runs the linked collector
in its own process and decides the run; stage 1 stays on, so the Python engine decides the same
run and a difference is exit 2. The real core and collector come from one build of `native/`. A
fake core (a script with its recorded digest) answers each request kind with a planned frame, so
the shell must refuse a dead core, a changed request and a changed verdict by name.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from filelock import FileLock

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.runtime import package_version
from archkeel.check.report import observe_repository
from archkeel.cli import main, native_core, native_scan, observe
from archkeel.cli.config import load_config
from archkeel.cli.core_frame import GapKind, read_frame
from tools.dual_run_corpus import Case, corpus_cases, materialized

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
SUFFIX = ".exe" if os.name == "nt" else ""
BINARIES = ("archkeel-core", "archkeel-typescript-collector", "archkeel-rust-collector")
# A corpus case that the core decides through the scan request (PASS in both engines).
HONEST = "probe/sources-test-an-honest-project-gives-pass-in-both-producers-honest"
# A corpus case whose Python run completes and whose contract has a UML target.
UML = "fixture/H-uml-typescript"
posix = pytest.mark.skipif(os.name == "nt", reason="the test writes a shebang script")
FAKE = """#!{python}
import json, os, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
kind = sys.argv[1]
(here / f"request-{{kind}}.json").write_bytes(sys.stdin.buffer.read())
plan = json.loads((here / "plan.json").read_text())[kind]
if plan == "abort":
    os.abort()
sys.stdout.write(plan["stdout"])
sys.exit(plan["exit"])
"""


@pytest.fixture(scope="module")
def built() -> Path:
    """The core and the TypeScript collector, built with the version of this install (AD-319)."""
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native core tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    target = NATIVE / "target" / "shell"
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [cargo, "build", "--locked", "-q", "-p", "archkeel-core"]
    command += ["-p", "archkeel-typescript-collector", "--target-dir", str(target)]
    command += ["-p", "archkeel-rust-collector"]
    with FileLock(str(NATIVE / "target" / ".pytest-native-build.lock")):
        done = subprocess.run(
            command,
            cwd=NATIVE,
            env={**os.environ, "ARCHKEEL_VERSION": package_version()},
            capture_output=True,
            text=True,
            check=False,
        )
    assert done.returncode == 0, done.stderr
    return target / "debug"


def _record(directory: Path, name: str) -> None:
    binary = directory / f"{name}{SUFFIX}"
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    (directory / f"{name}{SUFFIX}.sha256").write_text(digest, encoding="ascii")


@pytest.fixture
def install(built: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The `_native` directory of a platform wheel with the core and the TypeScript collector."""
    directory = tmp_path / "native"
    directory.mkdir()
    for name in BINARIES:
        shutil.copy2(built / f"{name}{SUFFIX}", directory / f"{name}{SUFFIX}")
        _record(directory, name)
    monkeypatch.setattr(observe, "_NATIVE_DIRECTORY", directory)
    monkeypatch.delenv(native_core.SWITCH_VARIABLE, raising=False)
    monkeypatch.delenv(observe.NATIVE_STORE, raising=False)
    return directory


def _case(name: str) -> Case:
    return next(case for case in corpus_cases() if case.id == name)


def _typescript(case: Case, root: Path) -> bool:
    try:
        scan = tomllib.loads((root / case.config).read_text())["scan"]
    except (OSError, KeyError, tomllib.TOMLDecodeError):
        return False
    return bool(scan.get("language") == "typescript")


def report(root: Path, *flags: str) -> tuple[int, dict[str, Any]]:
    artifact = root.parent / "out" / "architecture.json"
    shutil.rmtree(artifact.parent, ignore_errors=True)
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = main(["report", "--root", str(root), "--json", "--output", str(artifact), *flags])
    return code, json.loads(output.getvalue())


def core_notes(result: dict[str, Any]) -> list[str]:
    notes = result.get("notes") or ()
    return [note["unknown_claim"] for note in notes if note["subject"] == "native_core"]


def diagnostics(result: dict[str, Any]) -> str:
    return " ".join(item["unknown_claim"] for item in result["diagnostics"])


@contextlib.contextmanager
def case_root(name: str) -> Iterator[Path]:
    with materialized(_case(name)) as root:
        yield root.resolve()


def fake_core(install: Path, plan: dict[str, Any]) -> Path:
    """Replace the core with a script that answers each request kind with its plan."""
    core = install / f"archkeel-core{SUFFIX}"
    core.write_text(FAKE.format(python=sys.executable))
    core.chmod(0o755)
    (install / "plan.json").write_text(json.dumps(plan))
    _record(install, "archkeel-core")
    return install


def _shell_request(root: Path, case: Case) -> bytes:
    """The request payload that the shell sends to its bundled TypeScript collector. The launch
    fails on purpose after the payload is taken, so no collector runs."""
    config = load_config(root, case.config)
    sent: list[bytes] = []
    factory = partial(observe.observer_for, request_sink=sent.append, verify_bundled=True)
    observer = observe.configured_observer(config, factory)
    failing = ProcessCollector(
        (str(root / "no-collector"),),
        request_sink=sent.append,
        protocol_version=observer.collector.protocol_version,
    )
    observe_repository(root, config, replace(observer, collector=failing))
    [payload] = sent
    return payload


# --- The derived request -----------------------------------------------------------------------


def test_the_derived_request_equals_the_request_of_the_shell_on_every_typescript_case(
    install: Path,
) -> None:
    """Each TypeScript fixture and corpus case: the core reads the configuration itself and
    derives the request that the shell sends to its collector, field by field. The only refusal
    is a configured collector, by name."""
    binary = str(install / f"archkeel-core{SUFFIX}")
    compared, refused, differ = 0, [], []
    for case in corpus_cases():
        with materialized(case) as found:
            root = found.resolve()
            if not _typescript(case, root):
                continue
            try:
                payload = _shell_request(root, case)
            except Exception as error:  # noqa: BLE001 - the shell refuses the configuration
                refused.append(f"{case.id}: shell: {type(error).__name__}")
                continue
            request = native_scan.scan_request(payload, case.config)
            assert isinstance(request, dict)
            stdout, _ = native_scan.exchange(binary, "scan", json.dumps(request).encode())
            # The raw part: a frame that the reader refuses for another reason still shows the
            # request that the core derived.
            collect = json.loads(stdout)["self_test"]["collect"]
            if "request" not in collect:
                refused.append(f"{case.id}: {collect['refused']}")
                continue
            compared += 1
            if found_differences := native_scan.differences(
                collect["request"], json.loads(payload)
            ):
                differ.append(f"{case.id}: {found_differences}")
    assert differ == []
    assert [line for line in refused if ": collect: unsupported: collector: " not in line] == []
    assert compared >= 200


# --- The real core ------------------------------------------------------------------------------


def test_the_core_decides_a_typescript_run_through_the_scan_request(install: Path) -> None:
    with case_root(HONEST) as root:
        off = report(root)
        code, result = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (off[0], "PASS")
    [note] = core_notes(result)
    assert "The core ran the TypeScript collector in its own process" in note
    assert result["rule_assessments"] == off[1]["rule_assessments"]


@pytest.mark.parametrize("language", ["typescript", "rust"])
def test_a_declaration_only_scan_names_no_decided_rule_and_keeps_product_parity(
    install: Path,
    tmp_path: Path,
    language: str,
) -> None:
    with contextlib.ExitStack() as stack:
        root = (
            _rust_repository(install, tmp_path)
            if language == "rust"
            else stack.enter_context(case_root(HONEST))
        )
        config = load_config(root)
        path = root / config.contract
        contract = json.loads(path.read_text())
        contract["rules"] = [
            {
                **contract["rules"][0],
                "id": "ALLOW",
                "kind": "allowed_dependency",
                "source": config.namespace,
                "target": config.namespace,
            }
        ]
        path.write_text(json.dumps(contract))
        payload = _shell_request(root, _case(HONEST))
        request = native_scan.scan_request(payload, "archkeel.toml")
        assert isinstance(request, dict)
        binary = str(install / f"archkeel-core{SUFFIX}")
        stdout, exit_code = native_scan.exchange(binary, "scan", json.dumps(request).encode())
        frame = read_frame(stdout, exit_code, scan=True)
        assert exit_code == 3
        assert frame.status == "UNKNOWN" and not frame.decided
        assert frame.rules["ALLOW"].status == "DECLARATION"
        [gap] = frame.gaps
        assert gap.kind is GapKind.NO_DECIDED_RULE
        assert gap.reason == "unsupported: contract has no decided rule"
        assert frame.derived is not None and json.loads(frame.derived) == json.loads(payload)
        off = report(root)
        code, result = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (off[0], off[1]["declared_rules"]) == (0, "PASS")
    assert result["rule_assessments"] == off[1]["rule_assessments"]
    assert "contract has no decided rule" in core_notes(result)[0]


def _rust_repository(install: Path, tmp_path: Path) -> Path:
    from rust_repository import repository

    root = repository(tmp_path / "project", install / f"archkeel-rust-collector{SUFFIX}")
    config = root / "archkeel.toml"
    config.write_text(
        "\n".join(
            line
            for line in config.read_text().splitlines()
            if not line.startswith("collector_argv")
        )
        + "\n"
    )
    return root


def test_an_undecided_scan_goes_back_to_the_check_request_and_names_its_parts(
    install: Path,
) -> None:
    with case_root(UML) as root:
        code, result = report(root, "--native-core")
    assert code == 0
    [note] = core_notes(result)
    assert "UML target" in note
    # A part that both requests name is named one time.
    assert note.count("UML target") == 1


# --- The fake core ------------------------------------------------------------------------------


def _check_frame(stdout: str = "", exit_code: int = 3) -> dict[str, Any]:
    frame = {
        "engine": "archkeel-core fake",
        "status": "UNKNOWN",
        "rules": {},
        "explained": {},
        "violations": {},
        "beyond": {},
        "scope": "complete",
        "sections": {},
        "unsupported": {
            "rules": "planted: the fake core decides nothing",
            "sections": {},
            "report": None,
        },
        "self_test": {"contract": {"rules": {}}, "reply": {"files": 1}},
    }
    return {"stdout": stdout or json.dumps(frame), "exit": exit_code}


def _scan_frame(derived: dict[str, Any], rules: dict[str, Any], status: str) -> dict[str, Any]:
    frame = json.loads(_check_frame()["stdout"])
    frame["status"] = status
    frame["rules"] = rules
    frame["unsupported"]["rules"] = {}
    frame["self_test"]["contract"] = {"rules": {rule: kind for rule, (kind, _) in rules.items()}}
    frame["self_test"]["collect"] = {"request": derived}
    return {"stdout": json.dumps(frame), "exit": 0}


def _python(root: Path) -> tuple[int, dict[str, Any]]:
    return report(root)


@posix
def test_a_dead_core_on_the_scan_request_gives_no_verdict(install: Path) -> None:
    fake_core(install, {"scan": "abort", "check": _check_frame()})
    with case_root(HONEST) as root:
        code, result = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (2, "UNKNOWN")
    assert "the core exits with" in diagnostics(result)
    assert not (install / "request-check.json").exists()


@posix
def test_the_scan_request_carries_the_identity_and_no_reply(install: Path) -> None:
    fake_core(install, {"scan": _check_frame(), "check": _check_frame()})
    with case_root(HONEST) as root:
        report(root, "--native-core")
        sent = json.loads((install / "request-scan.json").read_text())
    assert sorted(sent) == ["config", "dirty", "git_head", "protocol", "root"]
    assert sent["protocol"] == "archkeel-core-scan-1"
    assert sent["root"] == str(root)
    # The refused scan frame (no `collect` part) is a frame that the shell refuses: exit 2.


@posix
def test_another_derived_request_sends_the_run_to_the_check_request(install: Path) -> None:
    with case_root(HONEST) as root:
        payload = _shell_request(root, _case(HONEST))
        python = _python(root)
        rules = {row["id"]: ["x", row["status"]] for row in python[1]["rule_assessments"]}
        derived = json.loads(payload)
        derived["scope"]["roots"] = ["elsewhere"]
        fake_core(install, {"scan": _scan_frame(derived, rules, "PASS"), "check": _check_frame()})
        code, result = report(root, "--native-core")
    assert code == 0
    [note] = core_notes(result)
    assert "the core derived another collection request: scope.roots" in note
    assert (install / "request-check.json").exists()


@posix
def test_a_scan_verdict_that_differs_from_python_is_exit_2(install: Path) -> None:
    with case_root(HONEST) as root:
        payload = _shell_request(root, _case(HONEST))
        python = _python(root)
        rows = python[1]["rule_assessments"]
        rules = {row["id"]: ["x", row["status"]] for row in rows}
        first = rows[0]["id"]
        rules[first] = ["x", "FAIL"]
        frame = _scan_frame(json.loads(payload), rules, "FAIL")
        changed = json.loads(frame["stdout"])
        changed["violations"] = {first: 1}
        frame["stdout"] = json.dumps(changed)
        fake_core(install, {"scan": frame, "check": _check_frame()})
        code, result = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (2, "UNKNOWN")
    assert "the core and the Python engine differ" in diagnostics(result)


@posix
def test_a_configured_collector_sends_no_scan_request(install: Path) -> None:
    fake_core(install, {"scan": _check_frame(), "check": _check_frame()})
    with case_root(HONEST) as root:
        toml = root / "archkeel.toml"
        collector = install / f"archkeel-typescript-collector{SUFFIX}"
        toml.write_text(toml.read_text() + f"collector_argv = {json.dumps([str(collector)])}\n")
        report(root, "--native-core")
    assert not (install / "request-scan.json").exists()


# --- The build and the check command ----------------------------------------------------------


@pytest.mark.parametrize("collector", ["typescript", "rust"])
def test_the_release_build_links_the_collector_without_its_test_feature(collector: str) -> None:
    """#1099 (a): the wheel builds the whole workspace without a feature (`hatch_build.py`). In
    that resolution the core links the TypeScript collector without `dump`, whose planted faults
    read the environment. A build with `dump` gives no accepted reply: `archkeel-collect` refuses
    it by name (`built`, its unit test)."""
    cargo = shutil.which("cargo")
    if cargo is None:
        pytest.skip("cargo is not installed")
    tree = subprocess.run(
        [cargo, "tree", "--locked", "--workspace", "-e", "features", "-i"]
        + [f"archkeel-{collector}-collector"],
        cwd=NATIVE,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "archkeel-core" in tree
    assert 'feature "dump"' not in tree
    hook = (NATIVE / "hatch_build.py").read_text()
    assert '"auditable", "build", "--release", "--locked", "--target-dir"' in hook
    assert "--features" not in hook


def test_check_never_sends_the_scan_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """AD-399: `check` reads the contract at the baseline commit from Git and the base reply of
    the accepted commit. The scan request has neither, so `check` stays on the check request."""
    from archkeel.check.ports import Language, ScanConfig
    from archkeel.cli.core_frame import CoreFrame, Status
    from archkeel.ir.model import Command, RunResult

    def no_scan(*_: object) -> None:
        raise AssertionError("check sent a scan request")

    undecided = CoreFrame("fake", Status.UNKNOWN, "complete", {}, {}, {}, {}, (), ("x.json",))
    monkeypatch.setattr(native_core, "scan", no_scan)
    monkeypatch.setattr(native_core.NativeCore, "run", lambda *_: undecided)
    core = native_core.NativeCore("archkeel-core", [b"base", b"candidate"], [b"{}", b"{}"])
    config = ScanConfig(("src",), "shop", "c.json", "", language=Language.TYPESCRIPT)
    result = RunResult(Command.CHECK, 0, rule_assessments=())
    shown = core.decide_check(result, Path("."), config, "HEAD")
    assert any("did not decide this run" in note.unknown_claim for note in shown.notes)
