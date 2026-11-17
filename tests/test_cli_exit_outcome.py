# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The exit code of each outcome of a run under `--baseline` (AD-731).

With `--baseline`, exit 2 means "every UNKNOWN is accepted", and CI treats it as green. Only a
verdict of the core can give that code. A command that could not run, and a file that could not
be written, exit 1 with a baseline and 2 without one. A collector refusal already did so.
"""

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, case_root
from test_cli_core_only_scan import command

from archkeel.cli import core_only
from archkeel.cli.core_binary import CoreBinaryNotFound
from archkeel.cli.core_json import CoreError, RequestMismatch
from tests.test_cli_init import plant

BROKEN = "export type T = ;\n"


def _run(*arguments: str) -> tuple[int, dict[str, object], str]:
    """Run in this process; give the exit code, the JSON document and the text."""
    import contextlib
    import io

    found: list[str] = []
    for form in ("--json", "--text"):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = core_only.run([*arguments, form])
        found.append(output.getvalue())
        found.append(str(code))
    document, json_code, text, text_code = found
    assert json_code == text_code, "text and JSON give the same exit code"
    return int(json_code), json.loads(document), text


def _no_core() -> Path:
    raise CoreBinaryNotFound("the core binary is missing")


def _project(root: Path) -> Path:
    """A folder with a configuration and no Git work tree: auto-init does not start."""
    (root / "archkeel.toml").write_text('[scan]\ncontract = "c.json"\n', encoding="utf-8")
    return root


@pytest.mark.parametrize(("flags", "expected"), [((), 2), (("--baseline", "b.json"), 1)])
def test_a_missing_core_exits_1_under_a_baseline_and_2_without(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flags: tuple[str, ...], expected: int
) -> None:
    monkeypatch.setattr(core_only, "locate_core", _no_core)
    code, document, text = _run("validate", "--root", str(_project(tmp_path)), *flags)
    assert code == expected, document
    assert document["exit_code"] == expected
    assert document["refusal"] == {  # type: ignore[comparison-overlap]
        "kind": "core_binary_not_found",
        "message": "the core binary is missing",
    }
    assert text.splitlines()[0] == f"validate: REFUSED -> exit {expected}"


def _raises(error: Exception) -> Callable[..., tuple[bytes, int]]:
    def exchange(*_: object) -> tuple[bytes, int]:
        raise error

    return exchange


@pytest.mark.parametrize(
    ("exchange", "kind"),
    [
        (_raises(CoreError("the core did not answer in 600 s")), "core_error"),
        (_raises(CoreError("the core exits with -11")), "core_error"),
        (_raises(CoreError("the core refused the request (exit 2): bad")), "core_error"),
        (_raises(RequestMismatch("the frame names another root")), "request_mismatch"),
        (lambda *_: (b"not a frame", 0), "core_error"),
    ],
    ids=["timeout", "crash", "core refusal", "request mismatch", "frame decode"],
)
def test_a_core_that_gives_no_frame_exits_1_under_a_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exchange: Callable[..., tuple[bytes, int]],
    kind: str,
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "archkeel-core")
    monkeypatch.setattr(core_only, "exchange", exchange)
    root = str(_project(tmp_path))
    code, document, _ = _run("validate", "--root", root, "--baseline", "b.json")
    assert (code, document["refusal"]["kind"]) == (1, kind), document  # type: ignore[index]
    code, document, _ = _run("validate", "--root", root)
    assert (code, document["refusal"]["kind"]) == (2, kind), document  # type: ignore[index]


def test_an_argument_error_under_a_baseline_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", _no_core)
    code, document, _ = _run(
        "validate", "--root", str(tmp_path), "--baseline", "b.json", "--no-such-option"
    )
    assert code == 1, document
    assert document["refusal"]["kind"] == "invalid_input"  # type: ignore[index]


def test_an_auto_init_stop_under_a_baseline_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = plant(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    monkeypatch.setattr(core_only, "locate_core", _no_core)
    monkeypatch.setenv("ARCHKEEL_NO_INIT", "1")
    code, document, _ = _run("validate", "--root", str(root), "--baseline", "b.json")
    assert code == 1, document
    assert not (root / "archkeel.toml").exists()


def _core(
    built: Path, root: Path, *flags: str, verb: str = "validate"
) -> tuple[int, dict[str, object]]:
    done = command(built / f"archkeel-core{SUFFIX}", root, "--json", *flags, verb=verb)
    assert "Traceback" not in done.stderr, done.stderr
    return done.returncode, json.loads(done.stdout)


def test_a_failed_baseline_write_on_a_drifting_run_keeps_exit_1(built: Path) -> None:
    with case_root(HONEST) as root:
        _core(built, root, "--write-baseline", "b.json")
        (root / "src/b/t.ts").write_text(BROKEN)
        code, result = _core(
            built, root, "--baseline", "b.json", "--write-baseline", "missing/c.json"
        )
    assert code == 1, result
    assert result["baseline"]["state"] == "drift"  # type: ignore[index]
    assert result["refusal"]["kind"] == "io_error"  # type: ignore[index]


def test_a_failed_report_write_without_a_baseline_still_exits_2(built: Path) -> None:
    with case_root(HONEST) as root:
        flags = ("--output", "missing/r.json", "--format", "json")
        done = command(built / f"archkeel-core{SUFFIX}", root, "--json", *flags, verb="report")
    result = json.loads(done.stdout)
    assert done.returncode == 2, result
    assert result["refusal"]["kind"] == "io_error"


def test_a_refused_run_that_compares_and_writes_exits_1_and_keeps_the_frame(
    built: Path,
) -> None:
    with case_root(HONEST) as root:
        _core(built, root, "--write-baseline", "b.json")
        (root / "architecture-contract.json").write_text("{", encoding="utf-8")
        code, result = _core(built, root, "--baseline", "b.json", "--write-baseline", "c.json")
        assert not (root / "c.json").exists()
    assert code == 1, result
    assert result["baseline"]["state"] == "not_written"  # type: ignore[index]
    assert result["baseline"]["exit_code"] == 1  # type: ignore[index]
    assert result["refusal"]["kind"] == "baseline_not_written"  # type: ignore[index]
    assert "frame" in result


def test_a_write_of_a_refused_run_keeps_the_frame_and_names_baseline_not_written(
    built: Path,
) -> None:
    with case_root(HONEST) as root:
        (root / "architecture-contract.json").write_text("{", encoding="utf-8")
        code, result = _core(built, root, "--write-baseline", "b.json")
        binary = built / f"archkeel-core{SUFFIX}"
        text = command(binary, root, "--text", "--write-baseline", "b.json")
        assert not (root / "b.json").exists()
    assert code == 2, result
    assert result["refusal"]["kind"] == "baseline_not_written"  # type: ignore[index]
    assert "frame" in result and result["status"] == "UNKNOWN"
    assert text.returncode == 2
    assert "no baseline file was written" in text.stdout


def test_a_collect_refusal_and_a_failed_report_keep_both_refusals(built: Path) -> None:
    with case_root(HONEST) as root:
        (root / "architecture-contract.json").unlink()
        flags = ("--output", "missing/r.json", "--format", "json")
        code, result = _core(built, root, *flags, verb="report")
        text = command(built / f"archkeel-core{SUFFIX}", root, "--text", *flags, verb="report")
    assert code == 2, result
    assert result["refusal"]["kind"] == "collection_refused"  # type: ignore[index]
    kinds = [item["kind"] for item in result["refusals"]]  # type: ignore[union-attr]
    assert kinds == ["collection_refused", "io_error"]
    assert "cannot write report file" in text.stdout, text.stdout
