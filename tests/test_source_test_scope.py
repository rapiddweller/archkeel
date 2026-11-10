# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-313: `[scan] exclude_test_sources` gives report and validate one test-free scope."""

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_architecture_demo import _prepare_repo

from archkeel.check.ports import Language, ScanConfig
from archkeel.check.validation import run_validate
from archkeel.cli import main
from archkeel.cli.config import ConfigError, load_config, parse_config
from archkeel.cli.observe import observer_for
from archkeel.render.summary import report_summary
from fixtures.demo_catalog_support import FIXTURE_DIR

_TYPESCRIPT = Path(__file__).parents[1] / "fixtures" / "H-typescript"
_KEY = "exclude_test_sources = true\n"
# language: fixture, a test file inside the scan root, its text
_CASES = {
    "python": (
        FIXTURE_DIR,
        "shop/model/test_mode.py",
        "from shop.app import orders\n",
    ),
    "typescript": (
        _TYPESCRIPT,
        "src/domain/scope-probe.spec.ts",
        'import { Order } from "./order";\nexport const probe = Order;\n',
    ),
}


def _scan_lines(fixture: Path) -> str:
    return (fixture / "archkeel.toml").read_text()


def _run(
    command: str,
    root: Path,
    config: str,
    capsys: pytest.CaptureFixture[str],
    *extra: str,
) -> tuple[int, dict[str, object]]:
    capsys.readouterr()
    code = main([command, "--root", str(root), "--config", config, *extra, "--json"])
    return code, json.loads(capsys.readouterr().out)


def _repo(tmp_path: Path, name: str, language: str, *, probe: bool) -> Path:
    fixture, path, text = _CASES[language]
    scan = _scan_lines(fixture)
    files: dict[str, str | None] = {
        "archkeel-off.toml": scan,
        "archkeel-on.toml": scan + _KEY,
    }
    if probe:
        files[path] = text
    return _prepare_repo(tmp_path / name, files, fixture)


@pytest.mark.parametrize("language", sorted(_CASES))
@pytest.mark.parametrize("command", ["validate", "report"])
def test_the_key_removes_test_files_and_keeps_production_verdicts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str, command: str
) -> None:
    clean = _repo(tmp_path, "clean", language, probe=False)
    probed = _repo(tmp_path, "probed", language, probe=True)
    _, base = _run(command, clean, "archkeel-off.toml", capsys)
    _, off = _run(command, probed, "archkeel-off.toml", capsys)
    _, on = _run(command, probed, "archkeel-on.toml", capsys)

    discovered = base["coverage"]["files_discovered"]  # type: ignore[index]
    assert off["coverage"]["files_discovered"] == discovered + 1  # type: ignore[index]
    assert on["coverage"] == base["coverage"]
    assert on["rule_assessments"] == base["rule_assessments"]
    assert off.get("notes") is None
    notes = on["notes"]
    assert [note["subject"] for note in notes] == ["scan.exclude_test_sources"]  # type: ignore[attr-defined,union-attr]
    assert "1 test source file(s)" in notes[0]["unknown_claim"]  # type: ignore[index]
    assert _CASES[language][1] in notes[0]["unknown_claim"]  # type: ignore[index]
    assert base.get("notes") is None


@pytest.mark.parametrize("language", sorted(_CASES))
def test_the_report_artifact_has_no_test_module_when_the_key_is_set(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str
) -> None:
    probed = _repo(tmp_path, "probed", language, probe=True)
    stem = Path(_CASES[language][1]).name.split(".")[0]
    for config, present in (("archkeel-off.toml", True), ("archkeel-on.toml", False)):
        artifact = tmp_path / f"{config}.json"
        assert _run("report", probed, config, capsys, "--output", str(artifact))[0] == 0
        assert (stem in artifact.read_text()) is present


@pytest.mark.parametrize("language", sorted(_CASES))
def test_an_absent_key_is_the_same_as_false(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], language: str
) -> None:
    probed = _repo(tmp_path, "probed", language, probe=True)
    (probed / "archkeel-false.toml").write_text(
        _scan_lines(_CASES[language][0]) + "exclude_test_sources = false\n"
    )
    _, absent = _run("validate", probed, "archkeel-off.toml", capsys)
    _, false = _run("validate", probed, "archkeel-false.toml", capsys)
    assert absent == false


_HEAD = b'[scan]\nroots = ["src"]\nnamespace = "app"\ncontract = "c.json"\n'


def test_the_key_defaults_to_false_and_reads_true() -> None:
    assert parse_config(_HEAD).exclude_test_sources is False
    assert parse_config(_HEAD + b"exclude_test_sources = true\n").exclude_test_sources is True
    ts = b'language = "typescript"\n' + _HEAD.removeprefix(b"[scan]\n")
    assert parse_config(b"[scan]\n" + ts + b"exclude_test_sources = true\n").exclude_test_sources


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (b'exclude_test_sources = "yes"\n', "must be a boolean"),
        (b'language = "dart"\nexclude_test_sources = true\n', "not supported for dart"),
    ],
)
def test_the_key_rejects_a_bad_value_or_a_language_without_a_test_rule(
    extra: bytes, message: str
) -> None:
    with pytest.raises(ConfigError, match=message):
        parse_config(_HEAD + extra)


def test_dart_may_name_the_key_as_false() -> None:
    config = parse_config(_HEAD + b'language = "dart"\nexclude_test_sources = false\n')
    assert config.exclude_test_sources is False


def _statuses(result: dict[str, object]) -> dict[str, str]:
    return {item["id"]: item["status"] for item in result["rule_assessments"]}  # type: ignore[attr-defined,union-attr]


def test_a_production_file_named_like_a_test_is_named_in_the_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`test_mode.py` is production code that breaks a rule. The key hides it by its name, so
    the note must name it: the pass alone must not be the only sign."""
    probed = _repo(tmp_path, "probed", "python", probe=True)
    _, off = _run("validate", probed, "archkeel-off.toml", capsys)
    _, on = _run("validate", probed, "archkeel-on.toml", capsys)
    assert _statuses(off)["DEP-MODEL-NO-APP"] == "FAIL"
    assert _statuses(on)["DEP-MODEL-NO-APP"] == "PASS"
    claim = on["notes"][0]["unknown_claim"]  # type: ignore[index]
    assert "shop/model/test_mode.py" in claim


def test_the_note_lists_at_most_twenty_sorted_paths_and_counts_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    probed = _repo(tmp_path, "probed", "python", probe=False)
    for index in range(23):
        (probed / "shop" / "model" / f"test_{index:02}.py").write_text("VALUE = 1\n")
    _, on = _run("validate", probed, "archkeel-on.toml", capsys)
    claim = on["notes"][0]["unknown_claim"]  # type: ignore[index]
    assert claim.startswith("23 test source file(s)")
    assert "shop/model/test_19.py" in claim
    assert "test_20.py" not in claim
    assert "and 3 more" in claim
    assert claim.index("test_00.py") < claim.index("test_01.py")


def test_the_human_output_prints_the_note(tmp_path: Path) -> None:
    probed = _repo(tmp_path, "probed", "python", probe=True)
    config = load_config(probed, "archkeel-on.toml")
    observer = observer_for(config.language, exclude_test_sources=True)
    result, _ = run_validate(probed, config, observer)
    result = replace(result, notes=config.scope_notes(observer.excluded_tests))
    assert "shop/model/test_mode.py" in report_summary(result).sentence


def test_validate_against_notes_a_changed_test_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A pull request that turns the key on changes the scope: the result must say so."""
    probed = _repo(tmp_path, "probed", "python", probe=True)
    (probed / "archkeel.toml").write_text((probed / "archkeel-off.toml").read_text())
    subprocess.run(["git", "add", "-A"], cwd=probed, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "scope"],
        cwd=probed,
        check=True,
        capture_output=True,
    )
    _, same = _run("validate", probed, "archkeel-off.toml", capsys, "--against", "HEAD")
    assert same.get("notes") is None
    (probed / "archkeel.toml").write_text((probed / "archkeel-on.toml").read_text())
    _, changed = _run("validate", probed, "archkeel.toml", capsys, "--against", "HEAD")
    subjects = [note["subject"] for note in changed["notes"]]  # type: ignore[attr-defined,union-attr]
    claims = " ".join(note["unknown_claim"] for note in changed["notes"])  # type: ignore[attr-defined,union-attr]
    assert subjects == ["scan.exclude_test_sources"] * 2
    assert "true here and false at" in claims


def test_an_unsupported_language_cannot_carry_the_key() -> None:
    with pytest.raises(ValueError, match="not supported for dart"):
        ScanConfig(("lib",), "app", "c.json", "d" * 64, Language.DART, exclude_test_sources=True)
