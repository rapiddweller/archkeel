# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-363: the core binary speaks the engine command of the dual run and owns nothing yet.

The core reads the contract bytes and the collector reply that the harness sends, and answers
each part that no slice has ported with its name. A slice that owns nothing fails the run; the
self-test proves the round trip; the host uses the core for no verdict.
"""

from __future__ import annotations

import json
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
    # The violations of the S1 kinds and the four sections of S3 are equal; each other section
    # and rule names its part.
    assert len(differences) == 1 + 15
    assert differences[0].startswith("rust/native: rules: ")
    assert "8 owned rules are unsupported" in differences[0]
    assert "rust/native: metrics: -: unsupported: section metrics: slice S10 ports it" in lines
    owned = ("violations", "dependency_edges", "modules", "packages", "cycles", "edges")
    assert not [line for line in differences if line.split(": ")[1] in owned]


def test_the_s1_kinds_equal_python_or_name_the_scope_proof(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-370: on the hand-made S1 cases each decided rule and each violation row equals the
    Python engine; a rule that only the scope proof of S4 can pass names it."""
    arguments = ["compare", "--case", "s1/*", "--sections", "violations", "--engine-command", core]
    code, lines = _run([*arguments, "--families", "complete_assignment,root_layout"], capsys)
    differences = [line for line in lines if line.startswith("s1/")]
    assert code == 1
    assert differences
    assert all(
        line.endswith("unsupported: the scope proof: slice S4 ports it") for line in differences
    )
    assert lines[-1].startswith(
        "dual run: family complete_assignment,root_layout; 1 sections; 13 projects; 26 rules;"
    )


def test_the_s2_kinds_and_the_edges_equal_python_or_name_their_slice(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-372, AD-374: on the hand-made S2 cases each decided rule, each violation row and each
    full edge row equals the Python engine; a PASS names the scope proof."""
    families = "external_dependency_scope,complete_external_scope"
    arguments = ["compare", "--case", "s2/*", "--sections", "violations,dependency_edges"]
    code, lines = _run([*arguments, "--families", families, "--engine-command", core], capsys)
    differences = [line for line in lines if line.startswith("s2/")]
    assert code == 1
    assert differences
    named = "unsupported: the scope proof: slice S4 ports it"
    assert all(line.endswith(named) for line in differences), differences
    assert lines[-1].startswith(
        f"dual run: family {','.join(sorted(families.split(',')))}; 2 sections; 16 projects; "
        "32 rules;"
    )


def test_the_s3_sections_equal_python_on_every_case_whose_reply_the_store_accepts(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-374: the full rows of `dependency_edges` (ranks included), `modules` (fan counts with
    the macro bodies), `packages` and `cycles` equal the Python engine. A case whose reply the
    store refuses names that refusal; no other difference is allowed."""
    arguments = ["compare", "--sections", "dependency_edges,modules,packages,cycles"]
    code, lines = _run([*arguments, "--families", "none", "--engine-command", core], capsys)
    differences = [
        line for line in lines if ": " in line and not line.startswith(("engine", "dual"))
    ]
    assert all(
        line.endswith(": -: missing input: no valid collector reply") for line in differences
    )
    refused = {line.split(": ")[0] for line in differences}
    assert not [case for case in refused if case.startswith(("s3/", "s2/", "s1/", "rust/"))]
    assert code == (1 if differences else 0)
    assert lines[-1].startswith("dual run: family none; 4 sections; 567 projects; 0 rules;")


def test_a_part_without_its_input_names_the_missing_input(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """The contract of J-compass mounts inside contracts: the core does not assemble the tree, so
    the rules name it, and each section names the missing contract, not a slice. A section of
    slice S3 needs no contract, so it names the reply that the store refuses."""
    code, lines = _run(["compare", "--case", "fixture/J-compass", "--engine-command", core], capsys)
    assert code == 1
    differences = [line for line in lines if line.startswith("fixture/J-compass: ")]
    assert (
        "the contract mounts inside contracts; the tree assembly is not in the core yet"
        in (differences[0])
    )
    s3 = {"dependency_edges", "modules", "packages", "cycles"}
    by_section = {line.split(": ")[1]: line for line in differences[1:]}
    assert all(
        line.endswith(": -: missing input: no valid contract")
        for section, line in by_section.items()
        if section not in s3
    )
    assert all(
        by_section[section].endswith(": -: missing input: no valid collector reply")
        for section in s3
    )


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


def test_the_model_the_evaluator_and_the_core_name_no_language() -> None:
    """The no-language rule of design WP6-0 section B; the Rust profile has no rule kind that
    reads an identifier, so the check is here and not in the native contract."""
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0)}"
        for crate in ("model", "eval", "core")
        for path in (ROOT / "native" / crate / "src").glob("*.rs")
        if not path.name.endswith("_tests.rs")
        for match in LANGUAGES.finditer(path.read_text())
    ]
    assert found == []


def test_each_native_component_is_a_node_of_the_component_graph() -> None:
    """The graph of native.md is written by hand while the native scan has gaps
    (`archkeel validate --write-graph` refuses), so a new component must not go missing."""
    contract = json.loads((ROOT / "native/architecture-contract.json").read_text())
    page = (ROOT / "docs/architecture/native.md").read_text()
    block = page.split("<!-- archkeel-component-graph -->", 1)[1].split("```", 2)[1]
    nodes = set(re.findall(r'n_\d+\["([^"]+)"\]', block))
    assert {component["label"] for component in contract["components"]} <= nodes
    assert "n_2 --> n_31" in block
