# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-390: `archkeel report --native-core` takes its verdict from the Rust core, stage 1.

The tests run the real CLI on a small Cargo workspace with the bundled Rust collector of a built
install: the core and the collector come from one build of `native/`, so they share one code
digest, as in a platform wheel. A fake core (a script with its recorded digest) writes hostile
frames and other verdicts, so the shell must refuse them by name.
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
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import rust_repository as rr
from filelock import FileLock
from graph_report_support import commit_tree

from archkeel.analyzer.runtime import package_version
from archkeel.cli import main, native_core, observe

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "native"
SUFFIX = ".exe" if os.name == "nt" else ""
RULES = {"ASSIGNED": "complete_assignment", "NO-CYCLES": "no_component_cycles"}
RULES["REQUIRES"] = "complete_requires"
# The shebang scripts of the fake core and collector do not run on Windows (#1099).
posix = pytest.mark.skipif(os.name == "nt", reason="the test writes a shebang script")
FAKE = """#!{python}
import json, pathlib, sys
here = pathlib.Path(__file__).resolve().parent
(here / "request.json").write_bytes(sys.stdin.buffer.read())
plan = json.loads((here / "plan.json").read_text())
sys.stdout.write(plan["stdout"])
sys.exit(plan["exit"])
"""


@pytest.fixture(scope="module")
def built() -> Path:
    """The core and the Rust collector, built with the version of this install (AD-319)."""
    cargo = shutil.which("cargo")
    if cargo is None and os.environ.get("CI"):
        pytest.fail("CI must provide cargo for the native core tests.")
    if cargo is None:
        pytest.skip("cargo is not installed; install Rust to test changes in native/.")
    target = NATIVE / "target" / "shell"
    (NATIVE / "target").mkdir(exist_ok=True)
    command = [cargo, "build", "--locked", "-q", "-p", "archkeel-core"]
    command += ["-p", "archkeel-rust-collector", "--target-dir", str(target)]
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
    """The `_native` directory of a platform wheel with the core and the Rust collector."""
    directory = tmp_path / "native"
    directory.mkdir()
    for name in ("archkeel-core", "archkeel-rust-collector"):
        shutil.copy2(built / f"{name}{SUFFIX}", directory / f"{name}{SUFFIX}")
    _record(directory, "archkeel-core")
    _record(directory, "archkeel-rust-collector")
    monkeypatch.setattr(observe, "_NATIVE_DIRECTORY", directory)
    monkeypatch.delenv(native_core.SWITCH_VARIABLE, raising=False)
    monkeypatch.delenv(observe.NATIVE_STORE, raising=False)
    return directory


def fake_core(install: Path, frame: dict[str, Any] | str, exit_code: int = 0) -> Path:
    """Replace the core of the install with a script that writes `frame` and exits."""
    core = install / f"archkeel-core{SUFFIX}"
    core.write_text(FAKE.format(python=sys.executable))
    core.chmod(0o755)
    stdout = frame if isinstance(frame, str) else json.dumps(frame)
    (install / "plan.json").write_text(json.dumps({"stdout": stdout, "exit": exit_code}))
    _record(install, "archkeel-core")
    return install / "request.json"


def frame(
    statuses: dict[str, str],
    status: str,
    *,
    explained: dict[str, str] | None = None,
    violations: dict[str, int] | None = None,
    beyond: dict[str, str] | None = None,
    unsupported: dict[str, str] | str | None = None,
) -> dict[str, Any]:
    return {
        "engine": "archkeel-core fake",
        "status": status,
        "rules": {rule: [RULES.get(rule, "x"), value] for rule, value in statuses.items()},
        "explained": explained or {},
        "violations": violations or {},
        "beyond": beyond or {},
        "scope": "complete",
        "sections": {},
        "unsupported": {"rules": unsupported or {}, "sections": {}, "report": None},
        "self_test": {"contract": {"rules": RULES}, "reply": {"files": 2}},
    }


PASSING = {"ASSIGNED": "PASS", "NO-CYCLES": "PASS", "REQUIRES": "PASS"}
_CYCLE = (rr.component("base", "base_crate"), rr.component("app", "app", ("base",)))


def repository(root: Path, install: Path, **changes: Any) -> Path:
    """The Cargo workspace of `rust_repository` with the bundled collector of the install."""
    rr.repository(root, install / f"archkeel-rust-collector{SUFFIX}", **changes)
    toml = root / "archkeel.toml"
    lines = toml.read_text().splitlines(keepends=True)
    toml.write_text("".join(line for line in lines if not line.startswith("collector_argv")))
    return root


@contextlib.contextmanager
def _captured() -> Iterator[io.StringIO]:
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        yield output


def report(root: Path, *flags: str) -> tuple[int, dict[str, Any], bytes]:
    """The exit code, the JSON result and the architecture.json bytes of one report run."""
    artifact = root.parent / "out" / "architecture.json"
    shutil.rmtree(artifact.parent, ignore_errors=True)
    with _captured() as output:
        code = main(["report", "--root", str(root), "--json", "--output", str(artifact), *flags])
    written = artifact.read_bytes() if artifact.is_file() else b""
    return code, json.loads(output.getvalue()), written


def statuses(result: dict[str, Any]) -> dict[str, str]:
    return {row["id"]: row["status"] for row in result["rule_assessments"] or ()}


def core_notes(result: dict[str, Any]) -> list[str]:
    notes = result.get("notes") or ()
    return [note["unknown_claim"] for note in notes if note["subject"] == "native_core"]


def without_core_notes(result: dict[str, Any]) -> dict[str, Any]:
    notes = [note for note in result.get("notes") or () if note["subject"] != "native_core"]
    kept = {key: value for key, value in result.items() if key != "notes"}
    return {**kept, "notes": notes} if notes or "notes" not in result else kept


def diagnostics(result: dict[str, Any]) -> str:
    return " ".join(item["unknown_claim"] for item in result["diagnostics"])


# --- The switch -------------------------------------------------------------------------------


def test_the_switch_off_changes_no_byte_of_the_output(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", install)
    code, result, written = report(root)
    # Off with the variable at 0, and off with no core in the install: the same bytes.
    monkeypatch.setenv(native_core.SWITCH_VARIABLE, "0")
    (install / f"archkeel-core{SUFFIX}").unlink()
    again = report(root)
    assert (code, result, written) == again
    assert core_notes(result) == []
    factory = observe.observer_for
    assert native_core.NativeCore.requested(False, {}).observer(factory) is factory


def test_another_value_of_the_variable_is_refused(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repository(tmp_path / "repo", install)
    monkeypatch.setenv(native_core.SWITCH_VARIABLE, "yes")
    code, result, written = report(root)
    assert code == 2
    assert "ARCHKEEL_NATIVE_CORE must be 0 or 1" in diagnostics(result)
    assert written == b""


# --- The real core ------------------------------------------------------------------------------


def test_the_core_decides_a_pass_run(install: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", install)
    off = report(root)
    code, result, written = report(root, "--native-core")
    assert code == 0
    assert result["declared_rules"] == "PASS"
    assert statuses(result) == PASSING
    [note] = core_notes(result)
    assert note.startswith("The core decides every rule of this run (archkeel-core ")
    assert without_core_notes(result) == off[1]
    assert written == off[2]


def test_the_core_decides_a_fail_run_with_the_violation_rows_of_python(
    install: Path, tmp_path: Path
) -> None:
    parts = (rr.component("base", "base_crate"), rr.component("app", "app"))
    root = repository(tmp_path / "repo", install, components=parts)
    off = report(root)
    code, result, written = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (0, "FAIL")
    assert statuses(result) == {**PASSING, "REQUIRES": "FAIL"}
    assert core_notes(result)[0].startswith("The core decides every rule")
    # The violation rows and the evidence are the rows of the Python engine, byte for byte.
    assert without_core_notes(result) == off[1]
    assert written == off[2]


def test_an_unknown_run_that_python_does_not_complete_is_named(
    install: Path, tmp_path: Path
) -> None:
    source = 'pub fn run() {}\n#[path = "x.rs"] mod hidden;\n'
    root = repository(tmp_path / "repo", install, files={"crates/app/src/lib.rs": source})
    code, result, _ = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (2, "UNKNOWN")
    [note] = core_notes(result)
    assert "the Python run did not complete (exit 2)" in note


def test_a_validation_baseline_changes_no_verdict_and_the_core_decides(
    install: Path, tmp_path: Path
) -> None:
    """AD-399: `report --baseline` adds the comparison rows and changes no verdict, row or exit
    code, so the core decides the run. The baseline knows no violation; the run has a new one."""
    root = repository(tmp_path / "repo", install)
    with _captured():
        main(["validate", "--root", str(root), "--baseline", "baseline.json", "--write-baseline"])
    contract = json.loads((root / "architecture-contract.json").read_text())
    contract["components"] = [rr.component("base", "base_crate"), rr.component("app", "app")]
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    alone = report(root)
    off = report(root, "--baseline", "baseline.json")
    code, result, written = report(root, "--baseline", "baseline.json", "--native-core")
    verdict = ("exit_code", "declared_rules", "rule_assessments")
    assert [off[1][key] for key in verdict] == [alone[1][key] for key in verdict]
    assert {new["status"] for new in off[1]["baseline_comparisons"]} == {"new"}
    assert (code, result["declared_rules"]) == (off[0], "FAIL")
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert without_core_notes(result) == off[1]
    assert written == off[2]


def test_a_configured_collector_is_never_sent_to_the_core(install: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", install)
    collector = install / f"archkeel-rust-collector{SUFFIX}"
    toml = root / "archkeel.toml"
    toml.write_text(toml.read_text() + f"collector_argv = {json.dumps([str(collector)])}\n")
    request = fake_core(install, frame(PASSING, "PASS"))
    _, result, _ = report(root, "--native-core")
    assert "the run uses the configured collector" in core_notes(result)[0]
    assert not request.exists()


def test_a_missing_core_binary_is_a_named_error(install: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", install)
    (install / f"archkeel-core{SUFFIX}").unlink()
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "the core binary is missing" in diagnostics(result)
    assert (result["declared_rules"], written) == ("UNKNOWN", b"")


def test_a_core_binary_with_another_digest_is_a_named_error(install: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", install)
    (install / f"archkeel-core{SUFFIX}.sha256").write_text("0" * 64, encoding="ascii")
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "the core binary is not verified" in diagnostics(result)
    assert written == b""


# --- A fake core --------------------------------------------------------------------------------


@posix
def test_the_request_states_no_trust(install: Path, tmp_path: Path) -> None:
    root = repository(tmp_path / "repo", install)
    request = fake_core(install, frame(PASSING, "PASS"))
    report(root, "--native-core")
    sent = json.loads(request.read_text())
    assert set(sent) == {
        "protocol",
        "contract",
        "insides",
        "reply",
        "roots",
        "namespace",
        "base",
    }
    assert sent["protocol"] == "archkeel-core-check-2"
    assert (sent["roots"], sent["namespace"], sent["base"]) == (["crates"], "native", None)


@posix
@pytest.mark.parametrize(
    ("name", "core_frame"),
    [
        ("a rule FAIL", frame({**PASSING, "REQUIRES": "FAIL"}, "FAIL", violations={"REQUIRES": 1})),
        ("a run UNKNOWN", frame(PASSING, "UNKNOWN")),
        (
            "a rule UNKNOWN",
            frame({**PASSING, "ASSIGNED": "UNKNOWN"}, "UNKNOWN", explained={"ASSIGNED": "x"}),
        ),
        ("a rule less", frame({"ASSIGNED": "PASS", "NO-CYCLES": "PASS"}, "PASS")),
        ("a beyond rule on a PASS", frame(PASSING, "PASS", beyond={"ASSIGNED": "no gap"})),
    ],
)
def test_a_verdict_difference_is_a_named_error(
    install: Path, tmp_path: Path, name: str, core_frame: dict[str, Any]
) -> None:
    root = repository(tmp_path / "repo", install)
    fake_core(install, core_frame)
    code, result, written = report(root, "--native-core")
    assert code == 2, name
    assert "the core and the Python engine differ" in diagnostics(result)
    assert (result["declared_rules"], written) == ("UNKNOWN", b"")


@posix
def test_a_rule_difference_under_the_same_run_status_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    parts = (rr.component("base", "base_crate"), rr.component("app", "app"))
    root = repository(tmp_path / "repo", install, components=parts)
    swapped = {**PASSING, "ASSIGNED": "FAIL"}
    fake_core(install, frame(swapped, "FAIL", violations={"ASSIGNED": 1}))
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "ASSIGNED: core FAIL, Python PASS" in diagnostics(result)
    assert "REQUIRES: core PASS, Python FAIL" in diagnostics(result)
    assert written == b""


@posix
def test_a_frame_that_names_a_rule_is_never_shown_as_the_verdict(
    install: Path, tmp_path: Path
) -> None:
    root = repository(tmp_path / "repo", install)
    off = report(root)
    named = frame(
        {"ASSIGNED": "PASS", "NO-CYCLES": "PASS"},
        "UNKNOWN",
        unsupported={"REQUIRES": "unsupported: rule kind CompleteRequires: the slice ports it"},
    )
    fake_core(install, named, exit_code=3)
    code, result, written = report(root, "--native-core")
    assert (code, written) == (off[0], off[2])
    [note] = core_notes(result)
    assert "REQUIRES: unsupported: rule kind CompleteRequires" in note
    assert without_core_notes(result) == off[1]


@posix
@pytest.mark.parametrize(
    ("name", "stdout", "exit_code"),
    [
        ("exit 0 with a named rule", frame(PASSING, "UNKNOWN", unsupported="whole"), 0),
        ("exit 3 without a named part", frame(PASSING, "PASS"), 3),
        ("exit 2", "", 2),
        ("exit 1", frame(PASSING, "PASS"), 1),
        ("a truncated frame", json.dumps(frame(PASSING, "PASS"))[:-9], 0),
        ("a second frame", json.dumps(frame(PASSING, "PASS")) * 2, 0),
        ("PASS with zero rules", frame({}, "PASS"), 0),
        ("an unknown status", frame(PASSING, "MAYBE"), 0),
        ("a trust field in the frame", {**frame(PASSING, "PASS"), "pinned": True}, 0),
    ],
)
def test_a_hostile_frame_is_a_named_error(
    install: Path, tmp_path: Path, name: str, stdout: dict[str, Any] | str, exit_code: int
) -> None:
    root = repository(tmp_path / "repo", install)
    fake_core(install, stdout, exit_code)
    code, result, written = report(root, "--native-core")
    assert code == 2, name
    assert result["declared_rules"] == "UNKNOWN"
    assert written == b""


# --- The trust root of stage 1: the bundled collectors (AD-390 point 2) ------------------------

FORGED = """#!{python}
import sys
sys.stdout.write("a forged reply that keeps the digest of this build")
"""


def _script(path: Path, text: str) -> None:
    path.write_text(text.format(python=sys.executable))
    path.chmod(0o755)


@posix
def test_a_rust_collector_with_a_stale_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    """Review B1: the collector is a script that prints a forged reply; its `.sha256` is stale."""
    root = repository(tmp_path / "repo", install, components=_CYCLE)
    _script(install / f"archkeel-rust-collector{SUFFIX}", FORGED)
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is not verified" in diagnostics(result)
    assert (result["declared_rules"], written) == ("UNKNOWN", b"")


def test_a_rust_collector_without_its_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    root = repository(tmp_path / "repo", install)
    (install / f"archkeel-rust-collector{SUFFIX}.sha256").unlink()
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is missing" in diagnostics(result)
    assert written == b""


@posix
def test_a_typescript_collector_without_its_digest_file_is_a_named_error(
    install: Path, tmp_path: Path
) -> None:
    """Without the switch the host takes the Python collector here (AD-352); with it, the binary
    that is present must have its digest."""
    root = tmp_path / "ts"
    (root / "src").mkdir(parents=True)
    (root / "src/a.ts").write_text("export const a = 1;\n")
    (root / "tsconfig.json").write_text('{"compilerOptions": {"strict": true}, "include": ["src"]}')
    contract = {"schema_version": "2.1.0", "components": [], "rules": []}
    (root / "architecture-contract.json").write_text(json.dumps(contract))
    (root / "archkeel.toml").write_text(
        '[scan]\nlanguage = "typescript"\nroots = ["src"]\nnamespace = "src"\n'
        'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
    )
    commit_tree(root)
    _script(install / f"archkeel-typescript-collector{SUFFIX}", FORGED)
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "a bundled collector is missing" in diagnostics(result)
    assert written == b""


@posix
def test_the_repository_and_the_environment_cannot_redirect_the_binaries(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ignored: a core or a collector in the scanned repository or on `PATH` never runs. The
    binaries come only from the directory of the package (`observe._NATIVE_DIRECTORY`)."""
    root = repository(tmp_path / "repo", install)
    marker = tmp_path / "marker"
    planted = f"#!{sys.executable}\nopen({str(marker)!r}, 'a').write('ran')\n"
    for directory in (root, root / "_native", tmp_path / "bin"):
        directory.mkdir(exist_ok=True)
        for name in ("archkeel-core", "archkeel-rust-collector"):
            (directory / name).write_text(planted)
            (directory / name).chmod(0o755)
            (directory / f"{name}.sha256").write_text(hashlib.sha256(planted.encode()).hexdigest())
    commit_tree(root)
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}{os.pathsep}{os.environ['PATH']}")
    code, result, _ = report(root, "--native-core")
    assert (code, result["declared_rules"]) == (0, "PASS")
    assert core_notes(result)[0].startswith("The core decides every rule")
    assert not marker.exists()


def test_a_store_variable_is_refused_with_the_switch(
    install: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refused: `ARCHKEEL_NATIVE_STORE` would redirect the decode of the Python engine."""
    root = repository(tmp_path / "repo", install)
    monkeypatch.setenv(observe.NATIVE_STORE, str(tmp_path / "store"))
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "ARCHKEEL_NATIVE_STORE redirects the decode" in diagnostics(result)
    assert written == b""


@posix
def test_a_run_pass_with_an_unknown_row_is_a_named_error(install: Path, tmp_path: Path) -> None:
    """Review S1, fault M1: a beyond rule must not carry a run PASS over an UNKNOWN row."""
    root = repository(tmp_path / "repo", install)
    hostile = frame(
        {**PASSING, "NO-CYCLES": "UNKNOWN"},
        "PASS",
        explained={"NO-CYCLES": "a reason"},
        beyond={"REQUIRES": "no one of the 1 kept pair gaps can change the rule"},
    )
    fake_core(install, hostile)
    code, result, written = report(root, "--native-core")
    assert code == 2
    assert "PASS with a rule that is not PASS" in diagnostics(result)
    assert written == b""
