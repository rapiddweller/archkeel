# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
import ast
import json
import re
import subprocess
import tomllib
from collections.abc import Iterator
from pathlib import Path

from archkeel.ir.lock import LOCK_PATH

ROOT = Path(__file__).parents[1]
HEADER = "\n".join(
    (
        "# Archkeel",
        "# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.",
        "# SPDX-License-Identifier: MIT",
        "",
    )
).encode()
FORBIDDEN = (
    b"/" + b"Users/",
    b"/" + b"home/",
    b"/" + b"private/tmp",
    b"/" + b"tmp/",
    b"/" + b"var/folders",
)
WINDOWS_DRIVE_ROOT = b"C:" + bytes([92])
# Split so this file does not match itself. A lone `=======` is a Markdown setext heading, so
# only the two unambiguous markers count; a conflict always leaves at least one of them.
CONFLICT_MARKERS = (b"<<<" + b"<<<<", b">>>" + b">>>>")
TRACKED = tuple(
    ROOT / name
    for name in subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT, text=True).split("\0")
    if name
)
SOURCES = tuple(
    path for path in TRACKED if path.suffix == ".py" and path.is_relative_to(ROOT / "src")
)
LONG_FUNCTION_LINES = 80
ALLOWED_LONG_FUNCTIONS = {
    ("src/archkeel/analyzer/python/collect.py::collect"): (
        "One deterministic collector pass shares the parsed and resolved project."
    ),
    ("src/archkeel/check/declarations.py::_rule_declaration"): (
        "One output record is built per declared rule kind."
    ),
    ("src/archkeel/check/declarations.py::project_declarations"): (
        "One output pass projects each root declaration from the same observation."
    ),
    ("src/archkeel/check/evaluation/evaluate.py::_evaluate_inside_contract"): (
        "One inside evaluation keeps local declarations and their parent scope together."
    ),
    ("src/archkeel/check/evaluation/evaluate.py::_inside_rule_results"): (
        "One pass gathers evaluator receipts for each inside rule."
    ),
    ("src/archkeel/check/evaluation/evaluate.py::evaluate_source"): (
        "One composition pass carries source facts through evaluation and coverage."
    ),
    ("src/archkeel/check/evaluation/rules.py::_boundary_rule_positions"): (
        "One traversal retains direct, inherited and undecidable positions for the same rule."
    ),
    ("src/archkeel/check/evaluation/rules.py::_boundary_type_verdict"): (
        "One decision path preserves proven, failed and unknown type outcomes."
    ),
    ("src/archkeel/check/evaluation/rules.py::_boundary_types_violations"): (
        "One position pass applies the same rule and allowance policy to every facade."
    ),
    ("src/archkeel/check/evaluation/rules.py::_inherited_generic_facade_types"): (
        "One proof walk binds base TypeVars and checks inherited signature positions."
    ),
    ("src/archkeel/check/evaluation/rules.py::_scoped_facade_signature_types"): (
        "One nested pass ties inherited types to their contract mount and publisher."
    ),
    ("src/archkeel/check/evaluation/rules.py::facade_signature_types"): (
        "One publication pass preserves resolved and uncertain types per facade."
    ),
    ("src/archkeel/check/evaluation/rules.py::public_api_exposed_types"): (
        "One type walk serves every declared public API entry."
    ),
    ("src/archkeel/check/evaluation/rules.py::requires_violations"): (
        "One import pass applies complete-requires rules and records each missing dependency."
    ),
    ("src/archkeel/check/evaluation/rules.py::rule_violations"): (
        "One ordered pass retains each rule result and its evidence receipt."
    ),
    ("src/archkeel/check/evaluation/rules.py::_collect_rule_violations"): (
        "One ordered composition keeps the rule families and their shared evidence together."
    ),
    ("src/archkeel/check/evaluation/state.py::evaluate_contexts"): (
        "One context pass joins state facts with their exact receiver and mutation evidence."
    ),
    ("src/archkeel/check/observation.py::_metrics"): (
        "One projection records the overview metrics from the same evaluated facts."
    ),
    ("src/archkeel/check/observation.py::assemble_observation"): (
        "One assembly keeps coverage, declarations and evaluator results on one source snapshot."
    ),
    ("src/archkeel/check/onboarding.py::draft_contract"): (
        "One draft derives ownership, measured size, interfaces and rules "
        "from the same observation."
    ),
    ("src/archkeel/check/onboarding.py::run_init"): (
        "One onboarding flow observes inputs, drafts the three files and "
        "returns its open decisions."
    ),
    ("src/archkeel/check/observe.py::_observe"): (
        "One observer boundary validates request, contract, facts and "
        "completeness before publication."
    ),
    ("src/archkeel/ir/facts_validation.py::validate_source_facts"): (
        "One fail-closed validation pass checks references across all fact sections."
    ),
    ("src/archkeel/check/delta.py::_compare_records"): (
        "Exact, relocated and changed stages share the unmatched record pools."
    ),
    ("src/archkeel/check/delta.py::build_architecture_delta"): (
        "Shared, coverage and availability reasons are decided in one place per dimension."
    ),
    ("src/archkeel/check/run.py::run_check"): (
        "Sequences authentication, git and host order, both snapshots and "
        "evaluation; one with-block owns the snapshot lifetimes."
    ),
    ("src/archkeel/check/validation.py::run_validate"): (
        "Sequences baseline, contract, observation and artifact decisions; the "
        "branches are the validation protocol."
    ),
    ("src/archkeel/cli/__init__.py::build_parser"): (
        "Declarative argparse setup, one subparser per command; help text is the length."
    ),
    ("src/archkeel/cli/__init__.py::main"): (
        "Composition root; one error boundary maps every command to a result."
    ),
    ("src/archkeel/ir/codec.py::encode_canonical_model"): (
        "Columnizing and interning share the sentinel rows."
    ),
    ("src/archkeel/ir/codec.py::parse_contract"): (
        "Field lists plus one parser per kind; the duplicate-id check spans all groups."
    ),
    ("src/archkeel/ir/codec.py::parse_delta"): (
        "Checks the delta envelope in wire order and assembles five named part "
        "parsers into one value."
    ),
    ("src/archkeel/render/html.py::render_html"): ("One template with its bindings."),
}


# A `git add -A` after running `archkeel report` to measure something committed `r.json`,
# `r.report.html` and two more into the repository root, and every test still passed. The root
# is small and changes rarely, so naming its whole contents catches any stray file rather than
# the report shapes that happened to land this time.
ROOT_FILES = frozenset(
    (
        ".gitignore",
        ".python-version",
        "CODE_OF_CONDUCT.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "Makefile",
        "README.md",
        "RELEASE_NOTES.md",
        "architecture-baseline.json",
        "architecture-contract.json",
        "archkeel.toml",
        "plugin.json",
        "pyproject.toml",
        "uv.lock",
    )
)


def _functions(node: ast.AST, prefix: str) -> Iterator[tuple[str, int]]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            name = f"{prefix}{child.name}"
            if not isinstance(child, ast.ClassDef):
                yield name, (child.end_lineno or child.lineno) - child.lineno + 1
            yield from _functions(child, f"{name}.")
        else:
            yield from _functions(child, prefix)


def test_tracked_python_files_have_license_header() -> None:
    assert TRACKED
    missing = [
        str(path.relative_to(ROOT))
        for path in TRACKED
        if path.suffix == ".py" and not path.read_bytes().startswith(HEADER)
    ]
    assert missing == []


def test_long_functions_have_a_named_reason() -> None:
    # AD-6: every long function is listed with its reason, and the list only shrinks.
    long_functions = {
        f"{path.relative_to(ROOT)}::{name}"
        for path in SOURCES
        for name, lines in _functions(ast.parse(path.read_bytes()), "")
        if lines > LONG_FUNCTION_LINES
    }
    assert sorted(long_functions - ALLOWED_LONG_FUNCTIONS.keys()) == []
    assert sorted(ALLOWED_LONG_FUNCTIONS.keys() - long_functions) == []


def test_every_analyzer_collector_is_a_declared_peer() -> None:
    """AD-25: a peer the contract never names is a peer nothing isolates.

    One-directional by design: every module defining a `collect_*` entry point must be
    declared, while a declared member need not follow that naming — `violations` exposes
    `rule_violations`. The second assertion catches a member left behind by a rename.
    """
    contract = json.loads((ROOT / "architecture-contract.json").read_bytes())
    declared = {
        member
        for rule in contract["rules"]
        if rule["kind"] == "sibling_isolation"
        for member in rule["members"]
    }
    python_root = ROOT / "src/archkeel/analyzer/python"
    collectors = {
        f"archkeel.analyzer.python.{path.relative_to(python_root).with_suffix('')}".replace(
            "/", "."
        )
        for path in python_root.rglob("*.py")
        if any(
            isinstance(node, ast.FunctionDef) and node.name.startswith("collect_")
            for node in ast.parse(path.read_bytes()).body
        )
    }

    assert sorted(collectors - declared) == []
    assert [
        member
        for member in sorted(declared)
        if not (ROOT / f"src/{member.replace('.', '/')}.py").is_file()
    ] == []
    assert list((ROOT / "src/archkeel/analyzer/embedded").rglob("*.py")) == []


def test_sdist_ships_library_and_build_inputs_only() -> None:
    """The sdist promises a runnable test suite only if it ships one that can run.

    It cannot: a tarball has no `.git` for the license-header check above, no pinned
    interpreters for `fixtures/E-runtime`, no `tools/`, and none of the cross-test imports the
    suite relies on. A shipped-but-untestable suite would be a second, weaker definition of
    "tests pass," so `only-include` carries what rebuilds the wheel (`src`, `schema` and the
    declared `README.md`) and distributors rebuild the test suite from the Git tag instead
    (docs/reference.md).
    """
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    only_include = config["tool"]["hatch"]["build"]["targets"]["sdist"]["only-include"]
    missing = [entry for entry in only_include if not (ROOT / entry).exists()]
    assert missing == [], f"only-include names a path the repository does not have: {missing}"

    def is_test_input(entry: str) -> bool:
        return entry.partition("/")[0] in {"tests", "fixtures", "tools"}

    shipped_test_inputs = [entry for entry in only_include if is_test_input(entry)]
    assert shipped_test_inputs == [], (
        "the sdist must not ship a test suite or its fixtures: it cannot run from a tarball "
        f"(see docs/reference.md), so shipping it half-working is worse than not shipping it; "
        f"found {shipped_test_inputs}"
    )


def test_decision_index_matches_decision_files() -> None:
    """AD-55: the decisions index and docs/architecture/decisions/ name the same set.

    A decision file nobody indexed, or an index row pointing at a missing file, is a
    drift the split's whole point was to prevent: add the file's row to the index table
    in docs/architecture/archkeel.md, or add the missing file under decisions/.
    """
    archkeel_md = (ROOT / "docs/architecture/archkeel.md").read_text(encoding="utf-8")
    indexed = dict(
        re.findall(
            r"^\| AD-(\S+) \| \[.*?\]\(decisions/(ad-\S+\.md)\) \|$", archkeel_md, re.MULTILINE
        )
    )
    decisions_dir = ROOT / "docs/architecture/decisions"
    on_disk = {path.name for path in decisions_dir.glob("ad-*.md")}

    assert indexed, "the index table in docs/architecture/archkeel.md parsed no rows"
    missing_files = sorted(set(indexed.values()) - on_disk)
    assert missing_files == [], (
        "the index in docs/architecture/archkeel.md names a file docs/architecture/decisions/ "
        f"does not have: {missing_files}"
    )
    unindexed_files = sorted(on_disk - set(indexed.values()))
    assert unindexed_files == [], (
        "docs/architecture/decisions/ holds a file the index in docs/architecture/archkeel.md "
        f"does not name: {unindexed_files}"
    )


def test_repository_root_holds_no_stray_file() -> None:
    """Generated output is invisible to every other guard: it is valid text at a plausible path."""
    tracked = frozenset(path.name for path in TRACKED if path.parent == ROOT)
    # CI adds the accepted lock after source approval.
    assert sorted(tracked - ROOT_FILES - {LOCK_PATH}) == []
    assert sorted(ROOT_FILES - tracked) == []


def test_tracked_text_has_no_local_absolute_paths() -> None:
    hits = []
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for line, text in enumerate(payload.splitlines(), 1):
            suffix = text.partition(WINDOWS_DRIVE_ROOT)[2]
            windows_path = bool(suffix) and not (
                suffix.startswith((b"n", b"t", b"r"))
                and suffix[1:2] in (b'"', b"'", b",", b")", b"]", b" ", b"\t")
            )
            if any(prefix in text for prefix in FORBIDDEN) or windows_path:
                hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == []


def test_tracked_text_carries_no_unresolved_merge_conflict() -> None:
    """A `git add -A` over an unresolved merge commits the markers and every test still passes.

    That happened: a merge left them in the decision record, and the split carried them into a
    decision's own file, where nothing looked at them again.
    """
    hits = []
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for line, text in enumerate(payload.splitlines(), 1):
            if any(text.startswith(marker) for marker in CONFLICT_MARKERS):
                hits.append(f"{path.relative_to(ROOT)}:{line}")
    assert hits == [], f"unresolved merge conflict markers: {hits}"


# The seven decision records that were already over the limit when it was drawn, each with the
# reason it is still there. The list may only shrink: a record rewritten short comes off it, and
# a new record never goes on, which is what makes the limit a ratchet rather than a suggestion.
LONG_DECISIONS = {
    "ad-48-reflection-that-writes-and-a-value-compared-with-a-string.md": "Two rule kinds in one "
    "record, each with its own measurement.",
    "ad-57-a-target-graph-marker-draws-the-edges-the-contract-permits.md": "Carries the marker's "
    "own syntax and a worked graph.",
    "ad-58-a-class-lives-where-its-symbolplacement-rule-allows-and-a.md": "Two rule kinds in one "
    "record, with the 189-position measurement.",
    "ad-60-report-only-rule-and-component-narrow-what-a-rendered.md": "Three flags, each with its "
    "own before and after.",
    "ad-61-a-widening-fails-unless-an-amendment-binds-its-exact-before.md": "Carries the "
    "amendment format and its failure modes.",
    "ad-62-an-annotated-variables-owner-is-the-scope-it-is-written-in.md": "Carries the scope "
    "cases one by one.",
    "ad-63-boundarytypes-reads-a-components-declared-public-list-not-a.md": "Records the rule's "
    "whole re-measurement and the vacuous-rule hole it opened.",
}
DECISION_LINE_LIMIT = 70


def test_decision_records_stay_readable() -> None:
    """A decision nobody finishes reading decides nothing (AD-19's reasoning, applied here).

    The median record is 27 lines and three quarters are under 46, so the limit costs the
    house style nothing; what it stops is the drift that produced a 163-line record whose
    reader has to hunt for what changed. A record that needs more room says why here, and
    `LONG_DECISIONS` may only shrink.
    """
    decisions = sorted((ROOT / "docs/architecture/decisions").glob("ad-*.md"))
    assert decisions, "no decision records found"
    too_long = {
        path.name for path in decisions if len(path.read_text().splitlines()) > DECISION_LINE_LIMIT
    }
    assert sorted(too_long - LONG_DECISIONS.keys()) == [], (
        f"a decision record over {DECISION_LINE_LIMIT} lines needs a named reason in "
        "LONG_DECISIONS, or it needs to be shorter"
    )
    assert sorted(LONG_DECISIONS.keys() - too_long) == [], (
        "LONG_DECISIONS names a record that is short enough now: remove the entry"
    )


def test_every_decision_reference_names_a_record() -> None:
    """`AD-64` in a comment is a promise that the record exists and says what the comment claims.

    The first half is checkable and this checks it: a reference nothing backs is how a renumbered
    or never-written record goes unnoticed. The second half is not: a quoted sentence in the same
    sentence as a reference may belong to either record, so verifying attributions was measured,
    produced four false positives on 66 files and no true ones, and was left to review.
    """
    # A record's id carries an optional letter: AD-24a and AD-24b are two records, and a pattern
    # of digits alone matches neither, so the two ids most in need of the check would skip it.
    identifier = re.compile(r"\bAD-(\d+[a-z]?)\b")
    numbers = {
        path.name.split("-")[1].lstrip("0")
        for path in (ROOT / "docs/architecture/decisions").glob("ad-*.md")
    }
    dangling: dict[str, list[str]] = {}
    for path in TRACKED:
        payload = path.read_bytes()
        if b"\0" in payload:
            continue
        for number in identifier.findall(payload.decode("utf-8", errors="ignore")):
            if number.lstrip("0") not in numbers:
                dangling.setdefault(f"AD-{number}", []).append(str(path.relative_to(ROOT)))
    assert dangling == {}, f"a decision reference names no record under decisions/: {dangling}"
