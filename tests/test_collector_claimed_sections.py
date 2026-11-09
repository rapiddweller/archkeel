# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-344: a claimed section with no record needs the statement that each file was examined.

Consumer: the host (`run_report`, `validate_source_facts`). A collector that claims `calls`,
`references`, `constructs` or `unknowns` and sends no record says one of two things: the source has
none, or the collector did not look. The reply separates them with `capabilities.examined`, a digest
of the paths that the collector examined. The host never reads an empty claimed section as a PASS
without the statement.
"""

from __future__ import annotations

import dataclasses
import sys
from pathlib import Path

import pytest

from archkeel.analyzer.typescript.collect import collect
from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from archkeel.ir.claimed_sections import CHECKED_SECTIONS, check_examined, examined_digest
from archkeel.ir.facts import FactSection, SourceSectionName
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository

CLAIM = str(Path(__file__).with_name("claim_collector.py"))
SECTIONS = sorted(item.value for item in CHECKED_SECTIONS)


def _verdict(root: Path, *mode: str) -> tuple[str, int]:
    config = load_config(root)
    argv = (sys.executable, "-I", "-B", CLAIM, *mode) if mode else None
    observer = observer_for(
        config.language, collector_argv=argv, tsconfig=config.tsconfig or "tsconfig.json"
    )
    result, _ = run_report(root, config=config, analyzer=observer)
    return str(result.observation_complete.value), result.exit_code


@pytest.fixture(scope="module")
def passing_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A catalog case that the default collector passes."""
    workspace = tmp_path_factory.mktemp("claimed")
    for index, variant in enumerate(VARIANTS):
        root = repository(workspace / str(index), variant)
        if _verdict(root) == ("PASS", 0):
            return root
    raise AssertionError("no catalog case passes")


@pytest.mark.parametrize("section", SECTIONS)
def test_an_empty_claimed_section_without_the_statement_is_not_a_pass(
    passing_root: Path, section: str
) -> None:
    assert _verdict(passing_root, "plain") == ("PASS", 0)
    complete, exit_code = _verdict(passing_root, "empty", section)
    assert complete != "PASS", section
    assert exit_code != 0, section


@pytest.mark.parametrize("mode", ["partial", "forged"])
def test_a_statement_for_another_set_of_files_is_not_a_pass(passing_root: Path, mode: str) -> None:
    for section in SECTIONS:
        complete, exit_code = _verdict(passing_root, mode, section)
        assert complete != "PASS" and exit_code != 0, (mode, section)


def test_the_collector_states_each_empty_checked_section(passing_root: Path) -> None:
    from test_collector_native_typescript import _request

    facts = collect(_request(passing_root))
    states = dict(facts.capabilities.examined)
    paths = [file.rel_path for file in facts.files]
    empty = [s.name for s in facts.sections if s.name in CHECKED_SECTIONS and not s.records]
    assert empty
    assert set(states) == set(empty)
    assert all(value == examined_digest(paths) for value in states.values())


def test_the_digest_binds_the_set_of_paths_and_not_their_order() -> None:
    assert examined_digest(["b.ts", "a.ts"]) == examined_digest(["a.ts", "b.ts"])
    assert examined_digest(["a.ts"]) != examined_digest(["a.ts", "b.ts"])
    assert examined_digest(["a b.ts"]) != examined_digest(["a", "b.ts"])


def test_a_scan_without_a_parsed_file_needs_no_statement(passing_root: Path) -> None:
    from test_collector_native_typescript import _request

    facts = collect(_request(passing_root))
    bare = dataclasses.replace(
        facts,
        files=(),
        capabilities=dataclasses.replace(facts.capabilities, examined=()),
        sections=tuple(FactSection(item.name, ()) for item in facts.sections),
    )
    check_examined(bare)


def test_the_check_names_the_section_that_lacks_the_statement(passing_root: Path) -> None:
    from test_collector_native_typescript import _request

    facts = collect(_request(passing_root))
    section = SourceSectionName.CALLS
    emptied = tuple(
        FactSection(item.name, ()) if item.name is section else item for item in facts.sections
    )
    kept = tuple((name, value) for name, value in facts.capabilities.examined if name != section)
    damaged = dataclasses.replace(
        facts,
        sections=emptied,
        capabilities=dataclasses.replace(facts.capabilities, examined=kept),
    )
    with pytest.raises(ValueError, match="claimed section calls"):
        check_examined(damaged)
