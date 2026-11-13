# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The one review round of #1127: bind the answer and keep refusals distinct from FAIL."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from core_support import HONEST, SUFFIX, built, case_root
from test_cli_core_only import GUARD, ROOT
from test_cli_core_only_boundary import HEAD, frame

from archkeel.cli import core_only
from archkeel.cli.native_scan import exchange

__all__ = ["built"]


@pytest.fixture(autouse=True)
def environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(core_only.VARIABLE, raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "archkeel.toml").write_text('[scan]\ncontract = "contract.json"\n')
    (tmp_path / "contract.json").write_text('{"rules": [{"id": "R1"}]}')


@pytest.mark.parametrize("fault", ["foreign-root", "foreign-rule"])
def test_an_unbound_other_projects_pass_is_a_refusal(
    fault: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    document = json.loads(frame())
    snapshot = document["self_test"]["collect"]["request"]["snapshot"]
    snapshot["root"] = str(tmp_path / "other" if fault == "foreign-root" else tmp_path)
    if fault == "foreign-rule":
        document.pop("contract_digest", None)
        document["rules"] = {"OTHER": ["complete_assignment", "PASS"]}
        document["self_test"]["contract"]["rules"] = {"OTHER": "complete_assignment"}
    monkeypatch.setattr(core_only, "identity", lambda _: (HEAD, False))
    monkeypatch.setattr(core_only, "locate_core", lambda: Path("core"))
    monkeypatch.setattr(core_only, "exchange", lambda *_: (json.dumps(document).encode(), 0))
    assert core_only.run(["validate", "--root", str(tmp_path), "--json"]) == 2
    refusal = json.loads(capsys.readouterr().out)["refusal"]
    assert refusal["kind"] == "request_mismatch"
    assert ("another root" if fault == "foreign-root" else "contract digest") in refusal["message"]


def test_a_contract_changed_after_the_real_scan_is_refused(
    built: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    with case_root(HONEST) as root:
        binary = built / f"archkeel-core{SUFFIX}"

        def changed(binary: str, command: str, payload: bytes) -> tuple[bytes, int]:
            answer = exchange(binary, command, payload)
            path = root / "architecture-contract.json"
            path.write_bytes(path.read_bytes() + b"\n")
            return answer

        monkeypatch.setattr(core_only, "locate_core", lambda: binary)
        monkeypatch.setattr(core_only, "exchange", changed)
        assert core_only.run(["validate", "--root", str(root), "--json"]) == 2
    refusal = json.loads(capsys.readouterr().out)["refusal"]
    assert refusal["kind"] == "request_mismatch" and "contract digest" in refusal["message"]


@pytest.mark.parametrize("form", ["--text", "--json"])
def test_unexpected_exception_is_not_an_architecture_failure(
    form: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def broken() -> Path:
        raise RuntimeError("planted internal fault")

    monkeypatch.setattr(core_only, "locate_core", broken)
    assert core_only.run(["validate", form]) == 2
    captured = capsys.readouterr()
    assert "Traceback" in captured.err and "planted internal fault" in captured.err
    if form == "--json":
        assert json.loads(captured.out)["refusal"]["kind"] == "internal_error"
    else:
        assert captured.out.startswith("REFUSED:") and "internal_error" in captured.out


@pytest.mark.parametrize("form", ["--text", "--json"])
def test_a_refusal_is_not_presented_as_an_unknown_rule(
    form: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert core_only.run(["check", form]) == 2
    text = capsys.readouterr().out
    if form == "--json":
        refusal = json.loads(text)["refusal"]
        assert refusal["kind"] == "not_on_this_development_line" and "#1103" in refusal["message"]
    else:
        assert text.startswith("REFUSED:")


@pytest.mark.parametrize("form", ["--text", "--json"])
def test_a_native_collection_refusal_is_also_typed(
    built: Path,
    form: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: built / f"archkeel-core{SUFFIX}")
    with case_root(HONEST) as root:
        config = root / "archkeel.toml"
        config.write_text(config.read_text().replace('"typescript"', '"python"'))
        assert core_only.run(["validate", "--root", str(root), form]) == 2
    text = capsys.readouterr().out
    if form == "--json":
        assert json.loads(text)["refusal"]["kind"] == "collection_refused"
    else:
        assert text.startswith("REFUSED:")


@pytest.mark.parametrize("form", ["--text", "--json"])
def test_the_real_core_path_and_code_digest_are_visible(
    built: Path,
    form: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    monkeypatch.setattr(core_only, "locate_core", lambda: binary)
    with case_root(HONEST) as root:
        assert core_only.run(["validate", "--root", str(root), form]) == 0
        result = capsys.readouterr().out
        if form == "--json":
            payload = json.loads(result)
            assert payload["core"]["path"] == str(binary)
            assert payload["core"]["engine"] == payload["frame"]["engine"]
            assert len(payload["core"]["code_digest"]) == 64
            assert (
                payload["frame"]["contract_digest"]
                == hashlib.sha256((root / "architecture-contract.json").read_bytes()).hexdigest()
            )
        else:
            assert f"Core: {binary}" in result and "code digest:" in result


def test_the_post_scan_guard_catches_a_module_planted_without_an_import(built: Path) -> None:
    binary = built / f"archkeel-core{SUFFIX}"
    script = GUARD.replace(
        "from archkeel.cli import main",
        "from archkeel.cli import main as real_main, core_only\n"
        f"from pathlib import Path\ncore_only.locate_core = lambda: Path({str(binary)!r})\n"
        "def main(argv):\n"
        "    code = real_main(argv)\n"
        "    sys.modules['archkeel.ir'] = object()\n"
        "    return code",
    )
    with case_root(HONEST) as root:
        done = subprocess.run(
            [
                sys.executable,
                "-c",
                script,
                "validate",
                "--root",
                str(root),
                "--json",
            ],
            env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    assert done.returncode != 0
    assert "forbidden module after command: archkeel.ir" in done.stderr
