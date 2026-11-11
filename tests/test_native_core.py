# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-363: the core binary speaks the engine command of the dual run and owns nothing yet.

The core reads the contract bytes and the collector reply that the harness sends, and answers
each part that no slice has ported with its name. A slice that owns nothing fails the run; the
self-test proves the round trip; the host uses the core for no verdict.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from conftest import build_native_copy

from tools import dual_run

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = re.compile(r"python|typescript|dart|\brust\b", re.IGNORECASE)


@pytest.fixture(scope="module")
def core(tmp_path_factory: pytest.TempPathFactory) -> str:
    binary = build_native_copy(tmp_path_factory, "core", binary="archkeel-core")
    return f"{binary} dual-run"


def _run(arguments: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str]]:
    capsys.readouterr()
    code = dual_run.main(arguments)
    return code, capsys.readouterr().out.splitlines()


def test_a_slice_that_owns_nothing_fails_the_run(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["compare", "--case", "fixture/H-uml", "--engine-command", core]
    code, lines = _run([*arguments, "--sections", "none", "--families", "none"], capsys)
    assert code == 2
    assert lines == ["the run selects nothing: name the owned sections or families, or --self-test"]


def test_a_run_of_cases_without_rules_and_without_sections_fails(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = ["--case", "fixture/E-runtime", "--case", "fixture/F-typescript-story"]
    code, lines = _run(["compare", *cases, "--sections", "none", "--engine-command", core], capsys)
    assert code == 2
    assert lines[-1] == "the run compares nothing: 0 owned rules and 0 sections"


def test_each_owned_part_is_unsupported_by_name_and_never_equal(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = _run(["compare", "--case", "rust/native", "--engine-command", core], capsys)
    assert code == 1
    differences = [line for line in lines if line.startswith("rust/native: ")]
    assert len(differences) == 1 + 20
    assert differences[0].startswith("rust/native: rules: ")
    assert "8 owned rules are unsupported" in differences[0]
    assert "rust/native: modules: -: unsupported: section modules: slice S1 ports it" in lines


def test_a_part_without_its_input_names_the_missing_input(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The contract of H-typescript has `declarations` (slice 0c-2): the rules say so, and each
    section names the missing contract, not a slice."""
    code, lines = _run(
        ["compare", "--case", "fixture/H-typescript", "--engine-command", core], capsys
    )
    assert code == 1
    differences = [line for line in lines if line.startswith("fixture/H-typescript: ")]
    assert "contract declarations: slice 0c-2 ports them" in differences[0]
    assert all(line.endswith(": -: missing input: no valid contract") for line in differences[1:])


def test_the_round_trip_reads_the_contract_and_the_reply_of_each_rust_case(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    cases = ["--case", "rust/native", "--case", "probe/rust_impls-*"]
    code, lines = _run(["compare", *cases, "--engine-command", core, "--self-test"], capsys)
    assert code == 0, lines
    assert lines[-1].startswith("dual run: self-test; 0 sections; 19 projects;")


def test_on_the_fixtures_each_self_test_difference_is_named(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = _run(
        ["compare", "--case", "fixture/*", "--engine-command", core, "--self-test"], capsys
    )
    assert code == 1
    differences = [line for line in lines if line.startswith("fixture/")]
    assert differences
    assert all(re.search(r": (unsupported|refused): ", line) for line in differences), differences
    # The rule ids and kinds of a parsed contract equal the verdict map: no kind differs.
    assert not [line for line in differences if " expected, " in line]
    # The TypeScript replies are compressed, so the store accepts them.
    refused = {line.split(":")[0] for line in differences if ": reply: " in line}
    assert "fixture/H-typescript" not in refused


def test_the_host_uses_the_core_for_no_verdict() -> None:
    sources = [path.read_text() for path in (ROOT / "src/archkeel").rglob("*.py")]
    assert not [text for text in sources if "archkeel-core" in text or "archkeel_core" in text]
    assert "archkeel-core" not in (ROOT / "native/hatch_build.py").read_text()


def test_the_model_and_the_core_name_no_language() -> None:
    """The no-language rule of design WP6-0 section B; the Rust profile has no rule kind that
    reads an identifier, so the check is here and not in the native contract."""
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for crate in ("model", "core")
        for path in (ROOT / "native" / crate / "src").glob("*.rs")
        if not path.name.endswith("_tests.rs")
        for match in LANGUAGES.finditer(path.read_text())
    ]
    assert found == []
