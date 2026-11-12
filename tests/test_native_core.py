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
import subprocess
from collections import Counter
from pathlib import Path

import pytest
from conftest import build_native_copy
from native_rules_support import language_names

from tools import dual_run
from tools.dual_run_oracle import Selection

ROOT = Path(__file__).resolve().parents[1]


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
    # AD-378: the five rules of the S1 and S2 kinds are a decided UNKNOWN equal to Python (the
    # reply has pair gaps that the contract does not allow); the three others name their kind.
    assert "3 owned rules are unsupported, first: unsupported: rule kind" in differences[0]
    assert "rust/native: metrics: -: unsupported: section metrics: slice S10 ports it" in lines
    owned = ("violations", "dependency_edges", "modules", "packages", "cycles", "edges")
    assert not [line for line in differences if line.split(": ")[1] in owned]


def test_the_s1_kinds_equal_python_with_the_scope_proof(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-370, AD-378: on the hand-made S1 cases each rule and each violation row equals the
    Python engine: PASS with the scope proof, FAIL, and UNKNOWN with its reason."""
    arguments = ["compare", "--case", "s1/*", "--sections", "violations", "--engine-command", core]
    code, lines = _run([*arguments, "--families", "complete_assignment,root_layout"], capsys)
    assert [line for line in lines if line.startswith("s1/")] == []
    assert code == 0, lines
    assert lines[-1].startswith(
        "dual run: family complete_assignment,root_layout; 1 sections; 13 projects; 26 rules; "
        "0 differences;"
    )


def test_the_s2_kinds_and_the_edges_equal_python_with_the_scope_proof(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-372, AD-374, AD-378: on the hand-made S2 cases each rule, each violation row and each
    full edge row equals the Python engine."""
    families = "external_dependency_scope,complete_external_scope"
    arguments = ["compare", "--case", "s2/*", "--sections", "violations,dependency_edges"]
    code, lines = _run([*arguments, "--families", families, "--engine-command", core], capsys)
    assert [line for line in lines if line.startswith("s2/")] == []
    assert code == 0, lines
    assert lines[-1].startswith(
        f"dual run: family {','.join(sorted(families.split(',')))}; 2 sections; 16 projects; "
        "32 rules; 0 differences;"
    )


# AD-378: the only names that a rule of a decided kind can have instead of a verdict.
S4_NAMES = (
    "missing input: no valid collector reply",
    # AD-379: a tree names its scope, its inside rules, a file that the shell did not send, or
    # its refusal; the first named rule of a case decides which name the row carries.
    "unsupported: the scope proof: the contract mounts inside contracts; the core does not read "
    "their coverage",
    "unsupported: a rule of an inside contract: the core does not clip a mount scope yet",
    "unsupported: the baseline of the request: no slice reads it yet",
)

# AD-384 point 4: the one direction change. Python gives a rule UNKNOWN for any kept pair gap;
# the core passes a rule that no kept gap can change. Only these cases have such a rule.
BEYOND = re.compile(
    r": rules: \S+: core decides, Python does not: no one of the \d+ kept pair gaps "
)
BEYOND_CASES = {
    "rust/native",
    "s7/rust-a-forbidden-and-a-sibling-rule-across-the-gap-hold-and-away-pass",
    "s7/rust-a-kept-pair-gap-holds-the-cycle-rules-and-not-the-module-set",
    "s7/rust-an-external-import-away-from-the-gap-passes-the-external-rules",
    "s7/rust-a-pair-gap-into-a-module-with-an-external-import-holds-the-external-rules",
    *(
        f"probe/rust_impls-test-{name}"
        for name in (
            "a-known-edge-from-another-module-of-the-component-close",
            "a-method-of-another-module-gives-no-false-pass-fp-29-a--2",
            "a-method-of-another-module-gives-no-false-pass-fp-30-a-",
            "a-path-call-that-the-scan-cannot-resolve-exactly-gives-",
            "a-path-call-that-the-scan-cannot-resolve-exactly-gives--3",
            "a-path-call-that-the-scan-cannot-resolve-exactly-gives--4",
            "pair-gaps-that-may-form-a-component-cycle-give-no-pass",
            "pair-gaps-that-may-form-a-cycle-give-no-pass-for-a-cycl",
            "pair-gaps-that-may-form-a-cycle-give-no-pass-for-a-cycl-2",
            "the-gap-of-a-pair-is-dropped-only-when-the-contract-all",
            "the-gap-of-a-pair-is-dropped-only-when-the-contract-all-3",
            "the-gap-of-an-allowed-pair-stays-when-the-edge-closes-a",
        )
    ),
}


def _beyond(differences: list[str]) -> list[str]:
    """The named lines of AD-384 point 4; each one is in a case of BEYOND_CASES."""
    found = [line for line in differences if BEYOND.search(line)]
    assert {line.split(":")[0] for line in found} <= BEYOND_CASES, found
    return found


def test_the_scope_proof_gives_the_verdict_of_python_or_an_exact_name_on_every_case(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-378: over the whole corpus each rule of the four decided kinds has the verdict of the
    Python engine, or a name of S4_NAMES, or a limit of one profile. No decided verdict differs."""
    families = "complete_assignment,root_layout,external_dependency_scope,complete_external_scope"
    arguments = ["compare", "--sections", "none", "--families", families]
    code, lines = _run([*arguments, "--engine-command", core], capsys)
    differences = [line for line in lines if ": rules: " in line]
    assert not [line for line in differences if ", found " in line], differences
    limit = re.compile(r"unsupported: the scope proof: \S+ is a limit of some profiles; ")
    tree = re.compile(r"(has not sent: |refused: inside-contract tree: )")
    named = [line for line in differences if line.endswith(S4_NAMES) or limit.search(line)]
    named += _beyond(differences)
    left = [line for line in differences if line not in named and not tree.search(line)]
    assert left == [], left
    assert code == (1 if differences else 0)
    # The s4 cases: each gap that the reply of a store-accepted profile can hold gives the
    # verdict of Python. The reply of the honest external collector is not compressed, so the
    # store refuses it; the Rust tests check the producer.
    s4 = [line for line in differences if line.startswith("s4/")]
    assert {line.split(":")[0] for line in s4} == {
        "s4/a-symbol-selector-is-a-limit-of-some-profiles",
        "s4/an-interface-boundary-is-a-limit-of-some-profiles",
        "s4/an-external-collector-with-a-pin-passes",
        "s4/an-external-collector-without-a-pin-is-unknown",
    }


S5_NAMES = (
    *S4_NAMES,
    "unsupported: the scope proof: a coverage gap that the dependency scope proof of "
    "complete_requires can accept",
)
# AD-384: slice S7 adds `no_component_cycles` to this run; its rows are compared too.
S5_FAMILIES = (
    "forbidden_dependency,allowed_dependency,sibling_isolation,layer_order,complete_requires,"
    "no_component_cycles"
)


def test_the_direction_kinds_give_the_verdict_of_python_or_an_exact_name_on_every_case(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-380: each rule of the five direction kinds has the verdict of the Python engine (an
    `allowed_dependency` rule its DECLARATION), or a name of S5_NAMES, or a limit of one
    profile. The violation rows of the decided rules equal the rows of Python. No decided
    verdict and no PASS or FAIL status of a run differs."""
    arguments = ["compare", "--sections", "violations", "--families", S5_FAMILIES]
    code, lines = _run([*arguments, "--engine-command", core], capsys)
    differences = [line for line in lines if ": rules: " in line or ": status: " in line]
    assert not [line for line in differences if ", found " in line or ": status: " in line]
    limit = re.compile(r"unsupported: the scope proof: \S+ is a limit of some profiles; ")
    tree = re.compile(r"(has not sent: |refused: inside-contract tree: )")
    beyond = _beyond(differences)
    left = [
        line
        for line in differences
        if not (line.endswith(S5_NAMES) or limit.search(line) or tree.search(line))
        and line not in beyond
    ]
    assert left == [], left
    rows = [line for line in lines if ": violations: " in line]
    # A section without its input names it: a refused reply, or a contract with a tree.
    missing = (
        ": -: missing input: no valid collector reply",
        ": -: missing input: no valid contract",
    )
    assert all(line.endswith(missing) for line in rows), rows
    assert not [line for line in rows if line.startswith(("s5/", "s7/"))]
    assert code == (1 if differences or rows else 0)
    # The s5 cases: a difference is only a limit of some profiles (AD-384: the scan roots now
    # give the receipt of `complete_requires`).
    named = {line.split(":")[0] for line in differences if line.startswith("s5/")}
    assert named <= {
        "s5/forbidden-symbol-rule-leaves-a-position-undecided",
        "s5/requires-symbol-port-is-judged-with-the-symbol-feature",
    }
    # AD-384: the s7 cases differ only by a named PASS beyond the reference engine.
    s7 = [line for line in differences if line.startswith("s7/")]
    assert s7 == [line for line in s7 if BEYOND.search(line) or line.endswith(S5_NAMES)], s7


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
    assert not [
        case for case in refused if case.startswith(("s3/", "s2/", "s1/", "rust/", "tree/"))
    ]
    assert code == (1 if differences else 0)
    assert lines[-1].startswith("dual run: family none; 4 sections; 635 projects; 0 rules;")


def test_a_part_without_its_input_names_the_missing_input(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-379: the contract of J-compass mounts inside contracts. The harness sends them, so the
    core assembles the tree and names each inside rule; each section names the reply that the
    store refuses, not the contract."""
    code, lines = _run(["compare", "--case", "fixture/J-compass", "--engine-command", core], capsys)
    assert code == 1
    differences = [line for line in lines if line.startswith("fixture/J-compass: ")]
    assert "unsupported: a rule of an inside contract" in differences[0]
    assert all(
        line.endswith(": -: missing input: no valid collector reply") for line in differences[1:]
    )
    assert len(differences) == 1 + 20


# The reasons that a tree case may name: each is a named gap, never an equal verdict (AD-379).
TREE_REASONS = (
    "unsupported: the scope proof: the contract mounts inside contracts; the core does not read "
    "their coverage",
    "unsupported: a rule of an inside contract: the core does not clip a mount scope yet",
    "unsupported: the contract mounts inside contracts that the shell has not sent: ",
    "refused: inside-contract tree: ",
    "missing input: no valid contract",
)


def test_the_tree_cases_equal_python_on_the_decided_kinds_or_name_each_gap(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-379: on the `tree/*` cases each root rule of a decided kind, each violation row and the
    S3 rows equal the Python engine. A rule of an inside contract, a PASS and a refused tree are
    named; no difference is unnamed."""
    families = "complete_assignment,root_layout,external_dependency_scope,complete_external_scope"
    sections = "violations,dependency_edges,modules,packages,cycles"
    arguments = ["compare", "--case", "tree/*", "--sections", sections, "--families", families]
    code, lines = _run([*arguments, "--engine-command", core], capsys)
    differences = [line for line in lines if line.startswith("tree/")]
    assert code == 1
    assert all(any(reason in line for reason in TREE_REASONS) for line in differences), differences
    assert not [line for line in differences if ": expected " in line or "drops this row" in line]
    named = {line.split(": ")[0] for line in differences if "a rule of an inside contract" in line}
    assert "tree/an-unresolved-import-is-unknown-beside-an-inside-contract" in named
    assert lines[-1].startswith("dual run: family complete_assignment,complete_external_scope,")
    assert "; 13 projects; 86 rules;" in lines[-1]
    v01 = "tree/an-inside-claim-outside-its-parent-makes-passing-root-rules-unknown: rules: "
    assert [line for line in differences if line.startswith(v01)] == [
        f"{v01}ASSIGNMENT: 7 owned rules are unsupported, first: {TREE_REASONS[0]}"
    ]


@pytest.mark.parametrize(
    "name",
    [case.id for case in dual_run.corpus_cases() if case.id.startswith("tree/")],
)
def test_the_run_status_of_a_tree_is_never_pass(core: str, name: str) -> None:
    """AD-379: a tree has named inside rules and a scope that the proof does not complete, so
    its run status is never PASS, and no root rule of a mounted tree is PASS."""
    case = next(item for item in dual_run.corpus_cases() if item.id == name)
    with dual_run.materialized(case) as root:
        frame, _ = dual_run.engine_and_reference(case, root, core, Selection())
    assert frame["status"] != "PASS", frame
    assert "PASS" not in [status for _, status in frame["rules"].values()]


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


def test_a_repeated_section_name_is_refused_before_any_row_is_built(core: str) -> None:
    """AD-374 review: a request that names one section many times made the core build its rows
    once for each name (9.56 GB for 200 names of `dependency_edges`). The binary refuses it."""
    binary = core.split(" ")[0]
    request = {
        "protocol": "archkeel-dual-run-3",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": None,
        "collector_argv": None,
        "pinned": False,
        "contracts": {"architecture-contract.json": "{}"},
        "reply": None,
        "sections": ["cycles", "modules", "cycles"],
        "namespace": "shop",
        "profile": "",
        "standard_library": [],
        "insides": [],
    }
    done = subprocess.run(
        [binary, "dual-run"], input=json.dumps(request), capture_output=True, text=True, check=False
    )
    assert done.returncode == 2
    assert done.stdout == ""
    assert "repeated section cycles" in done.stderr


def test_the_host_uses_the_core_for_no_verdict() -> None:
    sources = [path.read_text() for path in (ROOT / "src/archkeel").rglob("*.py")]
    assert not [text for text in sources if "archkeel-core" in text or "archkeel_core" in text]
    assert "archkeel-core" not in (ROOT / "native/hatch_build.py").read_text()


def test_the_model_the_evaluator_and_the_core_name_no_language() -> None:
    """The no-language rule of design WP6-0 section B; the Rust profile has no rule kind that
    reads an identifier, so the check is here and not in the native contract.

    AD-382: the rule also reads `report` and each subdirectory. AD-381 renamed the last
    language names of the `report` doc comments, so the pin is empty."""
    assert language_names(ROOT / "native") == Counter()


def test_each_native_component_is_a_node_of_the_component_graph() -> None:
    """The graph of native.md is written by hand while the native scan has gaps
    (`archkeel validate --write-graph` refuses), so a new component must not go missing."""
    contract = json.loads((ROOT / "native/architecture-contract.json").read_text())
    page = (ROOT / "docs/architecture/native.md").read_text()
    block = page.split("<!-- archkeel-component-graph -->", 1)[1].split("```", 2)[1]
    nodes = set(re.findall(r'n_\d+\["([^"]+)"\]', block))
    assert {component["label"] for component in contract["components"]} <= nodes
    assert "n_2 --> n_31" in block
