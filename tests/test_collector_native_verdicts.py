# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340: the verdicts of the host with the native collector, against two Python collectors.

Consumer: the host (`run_report`). The native collector has the inner-UML capability: imports with
their bound names, symbols, calls, references, bindings and constructs. It does not analyse script
globals yet, so it has the 4.2 gap in each file that can use a browser global, and it does not
declare `script-globals-v1`. Against the Python collector with the same gap (`native_oracle`) every
verdict, cycle, dependency edge, count and gap must be equal. Against the Python default collector
the native verdict is the same or more cautious, and a more cautious verdict is explained by a gap:
never complete where the default collector says UNKNOWN, never PASS where it says FAIL or UNKNOWN.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.typescript.collect import collect
from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.protocol import CollectionError
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository

ROOT = Path(__file__).parents[1]
ORACLE = str(Path(__file__).with_name("native_oracle.py"))
FIXTURES = (
    "fixtures/H-typescript",
    "fixtures/H-uml-typescript",
    "fixtures/F-typescript-story",
    "fixtures/L-nest-realworld",
)
# Artifact sections that name the producer.
PRODUCER = ("analyzer", "runtime", "producer")
# The reason that explains a more cautious native scan: the script analysis is not ported yet.
GLOBALS_GAP = "Script-global dependencies are not examined by the native collector"


def _commit(root: Path) -> None:
    for command in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
    ):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)


def _verdict(root: Path, argv: tuple[str, ...] | None) -> dict[str, object]:
    config = load_config(root)
    observer = observer_for(
        config.language, collector_argv=argv, tsconfig=config.tsconfig or "tsconfig.json"
    )
    result, artifact = run_report(root, config=config, analyzer=observer)
    sections: dict[str, object] = json.loads(artifact) if artifact else {}
    kept = {key: value for key, value in sections.items() if key not in PRODUCER}
    return {
        "declared": str(result.declared_rules.value),
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(str(item.kind.value) for item in result.diagnostics),
        "rules": {item.id: str(item.status.value) for item in result.rule_assessments or ()},
        "artifact": kept,
    }


def _short(verdict: dict[str, object]) -> tuple[object, object, object]:
    return verdict["declared"], verdict["complete"], verdict["exit"]


def _fixture(tmp_path: Path, name: str) -> Path:
    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("node_modules", ".git")
    shutil.copytree(ROOT / name, root, ignore=ignore)
    _commit(root)
    return root


def test_verdicts_equal_the_python_collector_with_the_same_gap_on_the_fixtures(
    tmp_path: Path, native_binary: Path
) -> None:
    for index, name in enumerate(FIXTURES):
        root = _fixture(tmp_path / str(index), name)
        oracle = _verdict(root, (sys.executable, "-I", "-B", ORACLE))
        native = _verdict(root, (str(native_binary),))
        assert native == oracle, name


@pytest.mark.parametrize("index", range(len(VARIANTS)))
def test_verdicts_equal_the_python_collector_with_the_same_gap_on_the_demo_variants(
    tmp_path: Path, native_binary: Path, index: int
) -> None:
    variant = VARIANTS[index]
    root = repository(tmp_path, variant)
    oracle = _verdict(root, (sys.executable, "-I", "-B", ORACLE))
    native = _verdict(root, (str(native_binary),))
    assert native == oracle, variant.id


def _gap_titles(root: Path, binary: Path) -> set[str]:
    """The titles of the coverage gaps in the reply of the native collector."""
    from test_collector_native_typescript import _request

    result = ProcessCollector((str(binary),)).collect(_request(root))
    assert not isinstance(result, CollectionError), result
    return {gap.title for gap in result.coverage.gaps}


def _cases(tmp_path: Path) -> list[tuple[str, Path]]:
    found = [(name, _fixture(tmp_path / f"f{index}", name)) for index, name in enumerate(FIXTURES)]
    found += [
        (variant.id, repository(tmp_path / f"v{index}", variant))
        for index, variant in enumerate(VARIANTS)
    ]
    return found


def test_native_is_never_less_cautious_than_the_default_collector(
    tmp_path: Path, native_binary: Path
) -> None:
    """Every rule has the verdict of the default collector or UNKNOWN, and UNKNOWN is explained.

    The only gap that explains a more cautious verdict is the one of the script analysis, which is
    ported in PR 4.3a-4 and 4.3a-5. A rule that the default collector fails stays FAIL or becomes
    UNKNOWN; a rule that it passes stays PASS or becomes UNKNOWN; a rule that it cannot judge is
    never judged here.
    """
    rows: list[str] = []
    for name, root in _cases(tmp_path):
        default = _verdict(root, None)
        native = _verdict(root, (str(native_binary),))
        assert default["rules"].keys() == native["rules"].keys(), name  # type: ignore[attr-defined]
        for rule, status in native["rules"].items():  # type: ignore[attr-defined]
            before = default["rules"][rule]  # type: ignore[index]
            assert status in (before, "UNKNOWN"), (name, rule, before, status)
            if status != before:
                rows.append(f"{name} | {rule} | {before} | {status}")
        if default["complete"] == "UNKNOWN":
            assert native["complete"] == "UNKNOWN", name
        assert native["declared"] in (default["declared"], "UNKNOWN"), name
        assert native["exit"] in (default["exit"], 2), name
        if _short(default) != _short(native) or native["rules"] != default["rules"]:
            assert GLOBALS_GAP in _gap_titles(root, native_binary), name
    # A scan of declaration files alone has no script global, so some verdicts are equal.
    print("VERDICT DIFFERENCES (case | rule | default | native)")
    print("\n".join(sorted(rows)))


REPLAY = str(Path(__file__).with_name("replay_collector.py"))
# The sections that the host takes as complete when they are present and empty (measured).
UNCHECKED_WHEN_EMPTY = ("calls", "references", "constructs")
INNER_SECTIONS = ("symbols", "calls", "references", "bindings", "constructs", "imports")


def _replayed(root: Path, inner: str, *mode: str) -> dict[str, object]:
    return _verdict(root, (sys.executable, "-I", "-B", REPLAY, inner, *mode))


def _passing_variant(tmp_path: Path) -> tuple[str, Path]:
    """A case that the default collector passes: the host judges a damaged reply against it."""
    for index, variant in enumerate(VARIANTS):
        root = repository(tmp_path / str(index), variant)
        verdict = _replayed(root, "python", "plain")
        if verdict["complete"] == "PASS" and verdict["exit"] == 0:
            return variant.id, root
    raise AssertionError("no catalog variant passes with the default collector")


def _filled_sections(root: Path) -> list[str]:
    """The sections that hold records in the reply of the default collector for `root`."""
    from test_collector_native_typescript import _request

    facts = collect(_request(root))
    return [item.name.value for item in facts.sections if item.records]


def test_a_reply_that_lacks_a_declared_section_is_never_a_pass(tmp_path: Path) -> None:
    """The host fails closed: a section that the capability declares must be in the reply.

    The native collector declares the same sections as the default collector, so what the host
    does with a damaged reply of one is what it does with a damaged reply of the other.
    """
    name, root = _passing_variant(tmp_path)
    filled = _filled_sections(root)
    assert filled, name
    for section in INNER_SECTIONS:
        damaged = _replayed(root, "python", "drop", section)
        assert damaged["complete"] != "PASS", (name, section)
        assert damaged["exit"] != 0, (name, section)
    for section in filled:
        emptied = _replayed(root, "python", "empty", section)
        if section in UNCHECKED_WHEN_EMPTY:
            # The host accepts these sections present and empty as a complete scan. This pins what
            # it does today; the next test says what it must do (AD-340).
            assert emptied["complete"] == "PASS" and emptied["exit"] == 0, (name, section)
        else:
            assert emptied["complete"] != "PASS", (name, section)
    claimed = _replayed(root, "python", "claim", "symbols")
    assert claimed["complete"] != "PASS", name


@pytest.mark.xfail(
    strict=True,
    reason="the host accepts a declared section that is present and empty as complete; the "
    "native collector is safe only while the 4.2 gap makes every scan incomplete (AD-340): the "
    "host must refuse it before PR 4.3a-5 removes the gap",
)
def test_a_section_that_is_emptied_is_never_a_pass(tmp_path: Path) -> None:
    name, root = _passing_variant(tmp_path)
    for section in _filled_sections(root):
        emptied = _replayed(root, "python", "empty", section)
        assert emptied["complete"] != "PASS", (name, section)


def test_the_host_notices_a_damaged_native_reply(tmp_path: Path, native_binary: Path) -> None:
    """No catalog scan completes with the native collector yet (the 4.2 gap is in every `.ts`
    file), so the verdict of a damaged reply cannot fall from PASS. The host must still say that
    the reply is damaged: the diagnostics differ from the diagnostics of the plain reply."""
    name, root = _passing_variant(tmp_path)
    plain = _replayed(root, str(native_binary), "plain")
    assert plain == _verdict(root, (str(native_binary),)), name
    for section in ("symbols", "calls", "references", "bindings", "constructs"):
        damaged = _replayed(root, str(native_binary), "drop", section)
        assert damaged["complete"] != "PASS" and damaged["exit"] != 0, section
        assert damaged["diagnostics"] != plain["diagnostics"], section
    claimed = _replayed(root, str(native_binary), "claim", "symbols")
    assert claimed["diagnostics"] != plain["diagnostics"]
    # An emptied section is not refused by the host (see the xfail test above); no scan of the
    # native collector is complete only because of the 4.2 gap.
    for section in ("symbols", "calls", "references", "bindings", "constructs"):
        emptied = _replayed(root, str(native_binary), "empty", section)
        assert emptied["complete"] != "PASS", section
