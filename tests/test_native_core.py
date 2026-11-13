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
from tools.dual_run_oracle import Selection

from tools import dual_run

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
    # The violations of the decided kinds and the four sections of S3 are equal; each other
    # section and rule names its part.
    assert len(differences) == 1 + 15
    assert differences[0].startswith("rust/native: rules: ")
    # AD-384, AD-418: every rule of the native contract is decided. A dropped pair gap holds
    # only the rules whose reading it can change, so no rule names it; the kept gaps hold the
    # others, and no kept gap can change the module set (a PASS beyond the reference engine).
    assert differences[0] == (
        "rust/native: rules: NATIVE-ASSIGNMENT-COMPLETE: core decides, Python does not: no one "
        "of the 20 kept pair gaps can change the rule"
    )
    assert not [line for line in differences if "unsupported: the scope proof" in line]
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


# AD-378: the only names that a rule of a decided kind can have instead of a verdict. AD-385: a
# rule of a tree has its verdict; a tree names only a file that the shell did not send or its
# refusal (the `tree` pattern of each test).
S4_NAMES = (
    "missing input: no valid collector reply",
    "unsupported: the baseline of the request: no slice reads it yet",
)

# AD-384 point 4: the one direction change. Python gives a rule UNKNOWN for any kept pair gap;
# the core passes a rule that no kept gap can change. Only these cases have such a rule.
BEYOND = re.compile(
    r": rules: \S+: core decides, Python does not: no one of the \d+ kept pair gaps "
)
BEYOND_CASES = {
    # AD-418: the module set of the self-check, which no kept gap can change.
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


# AD-388, L-35c: the one stricter change of the producer. Python trusts a pinned external
# collector; the core cannot verify a pin, so the rule is UNKNOWN and names the pin. Only the
# cases with a pinned external collector have such a rule.
STRICTER = re.compile(
    r": rules: \S+: core stricter than Python: incomplete scope: the reply does not come from "
    r"the bundled collector, and the collector pin is not verified by the core$"
)


def _stricter(differences: list[str]) -> list[str]:
    """The named lines of AD-388 point 4; each one is in a case with a pinned collector."""
    pinned = {case.id for case in dual_run.corpus_cases() if case.pinned and case.collector_argv}
    found = [line for line in differences if STRICTER.search(line)]
    assert {line.split(":")[0] for line in found} <= pinned, found
    return found


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
    named += _beyond(differences) + _stricter(differences)
    left = [line for line in differences if line not in named and not tree.search(line)]
    assert left == [], left
    assert code == (1 if differences else 0)
    # The native external reply is compressed. Both engines now refuse its unverified identity.
    s4 = [line for line in differences if line.startswith("s4/")]
    assert {line.split(":")[0] for line in s4} == {
        "s4/a-symbol-selector-is-a-limit-of-some-profiles",
        "s4/an-interface-boundary-is-a-limit-of-some-profiles",
        "s4/an-external-collector-with-a-pin-passes",
    }


S5_NAMES = (
    *S4_NAMES,
    "unsupported: the scope proof: a coverage gap that the dependency scope proof of "
    "complete_requires can accept",
    # AD-385: a layer_order rule of an inside contract cites the inside contract file.
    "unsupported: the scope proof: a layer_order rule of an inside contract cites the inside "
    "contract file; the core does not bind it",
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
    beyond = _beyond(differences) + _stricter(differences)
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
    # give the receipt of `complete_requires`) or the unverified pin of AD-388.
    stricter = set(_stricter(differences))
    named = {
        line.split(":")[0]
        for line in differences
        if line.startswith("s5/") and line not in stricter
    }
    assert named <= {
        "s5/forbidden-symbol-rule-leaves-a-position-undecided",
        "s5/requires-symbol-port-is-judged-with-the-symbol-feature",
    }
    # AD-384: the s7 cases differ only by a named PASS beyond the reference engine.
    s7 = [line for line in differences if line.startswith("s7/")]
    assert s7 == [
        line for line in s7 if BEYOND.search(line) or line.endswith(S5_NAMES) or line in stricter
    ], s7


def test_the_s3_sections_equal_python_on_every_case_whose_reply_the_store_accepts(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-374: the full rows of `dependency_edges` (ranks included), `modules` (fan counts with
    the macro bodies), `packages` and `cycles` equal the Python engine. A case whose reply the
    store refuses names that refusal; no other difference is allowed."""
    arguments = ["compare", "--sections", "dependency_edges,modules,packages,cycles"]
    code, lines = _run([*arguments, "--families", "none", "--engine-command", core], capsys)
    differences = [
        line for line in lines if ": " in line and not line.startswith(("engine", "dual", "SKIP "))
    ]
    assert all(
        line.endswith(": -: missing input: no valid collector reply") for line in differences
    )
    refused = {line.split(": ")[0] for line in differences}
    assert not [
        case for case in refused if case.startswith(("s3/", "s2/", "s1/", "rust/", "tree/"))
    ]
    assert code == (1 if differences else 0)
    assert lines[-1].startswith("dual run: family none; 4 sections; 324 projects; 0 rules;")
    assert "; 331 skipped;" in lines[-1]


def test_an_unsupported_project_is_a_counted_named_skip(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-422: a Dart case cannot become a partial native-core comparison."""
    code, lines = _run(["compare", "--case", "fixture/J-compass", "--engine-command", core], capsys)
    assert code == 2
    assert lines == [
        "SKIP fixture/J-compass: dart projects are not supported; use archkeel 4.0.1",
        "dual run: 0 supported projects; 1 skipped; no comparison",
    ]


# The reasons that a tree case may name: a file that the shell did not send, or a refused tree
# (AD-379). Each other rule of a tree has the verdict of Python (AD-385).
TREE_REASONS = (
    "unsupported: the contract mounts inside contracts that the shell has not sent: ",
    "refused: inside-contract tree: ",
    "missing input: no valid contract",
)
ALL_DECIDED = f"{S5_FAMILIES},complete_assignment,root_layout,external_dependency_scope,"
ALL_DECIDED += "complete_external_scope"


def test_the_tree_cases_equal_python_on_the_decided_kinds_or_name_each_gap(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-379, AD-385: on the `tree/*` cases each rule of a decided kind (root and inside), each
    violation row and the S3 rows equal the Python engine. Only a missing file and a refused tree
    are named."""
    families = "complete_assignment,root_layout,external_dependency_scope,complete_external_scope"
    sections = "violations,dependency_edges,modules,packages,cycles"
    arguments = ["compare", "--case", "tree/*", "--sections", sections, "--families", families]
    code, lines = _run([*arguments, "--engine-command", core], capsys)
    differences = [line for line in lines if line.startswith("tree/")]
    assert code == 1
    assert all(any(reason in line for reason in TREE_REASONS) for line in differences), differences
    named = {line.split(": ")[0] for line in differences}
    assert named == {
        "tree/a-cycle-of-inside-references-is-refused",
        "tree/a-missing-inside-contract-is-refused",
        "tree/an-inside-path-outside-the-repository-is-refused",
    }
    assert lines[-1].startswith("dual run: family complete_assignment,complete_external_scope,")
    assert "; 13 projects; 86 rules; 6 differences;" in lines[-1]


def test_the_inside_cases_equal_python_on_every_decided_kind_with_their_rows(
    core: str, capsys: pytest.CaptureFixture[str]
) -> None:
    """AD-385: on the `inside/*` cases each rule of the nine decided kinds of a tree (each
    direction kind inside a mount, a tree two levels deep, an inside contract without rules, a
    mount with a doubt, the same rule id in two inside contracts, a rule that must read only its
    own domain, an edge that leaves a mount or enters another one, a cut exact-module claim) has
    the verdict and the violation rows of Python. The core names only the file of an inside
    `layer_order` rule; no PASS or FAIL status differs."""
    arguments = ["compare", "--case", "inside/*", "--sections", "violations"]
    code, lines = _run([*arguments, "--families", ALL_DECIDED, "--engine-command", core], capsys)
    differences = [line for line in lines if line.startswith("inside/")]
    assert not [line for line in differences if ", found " in line or ": status: " in line]
    assert not [line for line in differences if ": violations: " in line]
    scan_roots = "the receipt of complete_requires needs the scan roots; the request has none"
    layer = "a layer_order rule of an inside contract cites the inside contract file"
    assert all(scan_roots in line or layer in line for line in differences), differences
    assert code == 1
    assert "; 9 projects; 106 rules; 1 differences;" in lines[-1]


def test_a_pinned_external_collector_is_not_trusted_by_the_core(core: str) -> None:
    """AD-388, L-35c (review S2 of #1090): Python trusts the pinned external collector of this
    case and passes its rules; the core cannot verify the pin, so each of these rules is UNKNOWN
    with the reason that names the pin, and the run is not PASS."""
    case = next(c for c in dual_run.corpus_cases() if c.id == PIN_CASE)
    with dual_run.materialized(case) as root:
        frame, reference = dual_run.engine_and_reference(case, root, core, Selection())
    assert reference is not None and reference["declared_rules"] == "PASS"
    assert frame["status"] == "UNKNOWN", frame
    statuses = [status for _, status in frame["rules"].values()]
    assert statuses and set(statuses) == {"UNKNOWN"}, frame
    assert {why for why in frame["explained"].values()} == {
        "incomplete scope: the reply does not come from the bundled collector, and the "
        "collector pin is not verified by the core"
    }


PIN_CASE = "pin/a-pinned-external-collector-is-not-trusted-by-the-core"


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
        "protocol": "archkeel-dual-run-5",
        "case": "c",
        "root": "/r",
        "config": "archkeel.toml",
        "baseline": None,
        "collector_argv": None,
        "contracts": {"architecture-contract.json": "{}"},
        "reply": None,
        "sections": ["cycles", "modules", "cycles"],
        "namespace": "shop",
        "profile": "",
        "standard_library": [],
        "insides": [],
        "roots": [],
    }
    done = subprocess.run(
        [binary, "dual-run"], input=json.dumps(request), capture_output=True, text=True, check=False
    )
    assert done.returncode == 2
    assert done.stdout == ""
    assert "repeated section cycles" in done.stderr


def test_the_host_uses_the_core_only_behind_its_switch() -> None:
    """AD-390: only the switch module of the shell, its frame reader and its scan request
    (AD-406) name the core, and no wheel carries the core yet (stage 3)."""
    names = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src/archkeel").rglob("*.py")
        if "archkeel-core" in path.read_text() or "archkeel_core" in path.read_text()
    }
    assert names == {
        "src/archkeel/cli/native_core.py",
        "src/archkeel/cli/core_frame.py",
        "src/archkeel/cli/native_scan.py",
        "src/archkeel/cli/core_binary.py",
    }
    assert "archkeel-core" not in (ROOT / "native/hatch_build.py").read_text()


def test_the_core_reaches_a_trusted_producer_in_two_named_functions_only() -> None:
    """AD-390 point 2: the check request reaches trust only in `stage_one_shell_trust`, the dual
    run only in its `producer` (AD-388), and the scan request only in `in_process`, because the
    core ran the collector itself (AD-406). No other production code of the core names it."""
    found = []
    for path in sorted((ROOT / "native/core/src").glob("*.rs")):
        if path.name.endswith("_tests.rs"):
            continue
        function = ""
        for line in path.read_text().splitlines():
            if match := re.match(r"\s*(?:pub\(crate\) )?fn (\w+)", line):
                function = match[1]
            if "Producer::Trusted" in line and not line.lstrip().startswith("//"):
                found.append(f"{path.name}::{function}")
    assert found == [
        "check.rs::stage_one_shell_trust",
        "dual_run.rs::producer",
        "scan.rs::in_process",
    ]


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
