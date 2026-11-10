# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-340: the verdicts of the host with the native collector equal those with the Python one.

Consumer: the host (`run_report`). The native collector gives every section of the Python default
collector, script globals included (PR 4.3a-5). So every verdict, cycle, dependency edge, count and
gap must be equal on the four fixtures and on the demo variants. A damaged native reply must fail
the same way as a damaged Python reply.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from collector_pin import pin_of

from archkeel.analyzer import process as process_owner
from archkeel.analyzer.runtime import package_version
from archkeel.analyzer.typescript.collect import collect
from archkeel.check.report import run_report
from archkeel.cli import observe as bundled
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
from fixtures.demo_catalog_typescript import VARIANTS
from fixtures.reproduce_typescript import repository

ROOT = Path(__file__).parents[1]
FIXTURES = (
    "fixtures/H-typescript",
    "fixtures/H-uml-typescript",
    "fixtures/F-typescript-story",
    "fixtures/L-nest-realworld",
)
# Artifact sections that name the producer, and how the host started it (AD-344). The string table
# and the observations of the scope hold digests of the producer (the member inventory proof binds
# them), so they are compared by the kinds of their records, not by their bytes.
PRODUCER = (
    "analyzer",
    "runtime",
    "producer",
    "producer_kind",
    "string_table",
    "scope_observations",
)


def _commit(root: Path) -> None:
    for command in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"],
    ):
        subprocess.run(["git", *command], cwd=root, check=True, capture_output=True)


@pytest.fixture(scope="session")
def bundled_directory(native_binary: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An install of the native collector as a platform wheel has it (AD-317, AD-352): the binary
    and the file with its digest. The host launches this binary as the bundled producer."""
    directory = tmp_path_factory.mktemp("native") / "_native"
    directory.mkdir()
    binary = shutil.copy2(
        native_binary, bundled.executable(bundled.TYPESCRIPT_COLLECTOR, directory)
    )
    digest = pin_of(binary).removeprefix("sha256:")
    Path(f"{binary}{bundled.DIGEST_SUFFIX}").write_text(digest, encoding="ascii")
    return directory


def _scope_kinds(sections: dict[str, Any]) -> list[str]:
    """The kinds of the records of `scope_observations`, read through the string table."""
    table = sections.get("string_table", [])
    kinds = [row[3] for row in sections.get("scope_observations") or ()]
    return [
        table[int(kind[1:])] if kind.startswith("$") and kind[1:].isdigit() else kind
        for kind in kinds
    ]


def _verdict(
    root: Path, argv: tuple[str, ...] | None, native_directory: Path | None = None
) -> dict[str, object]:
    config = load_config(root)
    observer = observer_for(
        config.language,
        collector_argv=argv,
        tsconfig=config.tsconfig or "tsconfig.json",
        # AD-344: a configured collector is capped at UNKNOWN unless it is pinned.
        pinned_digest=None if argv is None else pin_of(argv[0]),
        # AD-352: the launcher of the native collector of an install.
        native_directory=native_directory,
    )
    # The debug binary has no build version; a wheel sets it to the version of the host (AD-317).
    version = "0+unknown" if native_directory is not None else package_version()
    with mock.patch.object(process_owner, "package_version", lambda: version):
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
        "scope_kinds": _scope_kinds(sections),
    }


def _short(verdict: dict[str, object]) -> tuple[object, object, object]:
    return verdict["declared"], verdict["complete"], verdict["exit"]


def _fixture(tmp_path: Path, name: str) -> Path:
    root = tmp_path / "repo"
    ignore = shutil.ignore_patterns("node_modules", ".git")
    shutil.copytree(ROOT / name, root, ignore=ignore)
    _commit(root)
    return root


def test_verdicts_equal_the_python_collector_on_the_fixtures(
    tmp_path: Path, bundled_directory: Path
) -> None:
    for index, name in enumerate(FIXTURES):
        root = _fixture(tmp_path / str(index), name)
        assert _verdict(root, None, bundled_directory) == _verdict(root, None), name


@pytest.mark.parametrize("index", range(len(VARIANTS)))
def test_verdicts_equal_the_python_collector_on_the_demo_variants(
    tmp_path: Path, bundled_directory: Path, index: int
) -> None:
    variant = VARIANTS[index]
    root = repository(tmp_path, variant)
    assert _verdict(root, None, bundled_directory) == _verdict(root, None), variant.id


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
    reason="the host accepts a declared section that is present and empty as complete. The "
    "native collector cannot lose an import node silently since PR 4.3a-5 (the `unextracted` "
    "gap, AD-352); an emptied section of a reply stays open until protocol 10",
)
def test_a_section_that_is_emptied_is_never_a_pass(tmp_path: Path) -> None:
    name, root = _passing_variant(tmp_path)
    for section in _filled_sections(root):
        emptied = _replayed(root, "python", "empty", section)
        assert emptied["complete"] != "PASS", (name, section)


def test_the_host_notices_a_damaged_native_reply(
    tmp_path: Path, native_binary: Path, bundled_directory: Path
) -> None:
    """The host must say that a reply is damaged: the diagnostics differ from the plain reply. A
    damaged reply of the native collector is judged as the same damage of the Python collector."""
    name, root = _passing_variant(tmp_path)
    plain = _replayed(root, str(native_binary), "plain")
    assert plain["diagnostics"] == _verdict(root, None, bundled_directory)["diagnostics"], name
    assert _short(plain) == _short(_replayed(root, "python", "plain")), name
    for section in ("symbols", "calls", "references", "bindings", "constructs"):
        damaged = _replayed(root, str(native_binary), "drop", section)
        assert damaged["complete"] != "PASS" and damaged["exit"] != 0, section
        assert damaged["diagnostics"] != plain["diagnostics"], section
    claimed = _replayed(root, str(native_binary), "claim", "symbols")
    assert claimed["diagnostics"] != plain["diagnostics"]
    # The host takes an emptied section as it takes it from the Python collector (the xfail test
    # above pins that); the extraction invariant (`test_collector_native_unextracted.py`) is what
    # keeps a lost node from being silent in the native collector.
    for section in ("symbols", "calls", "references", "bindings", "constructs"):
        emptied = _replayed(root, str(native_binary), "empty", section)
        assert _short(emptied) == _short(_replayed(root, "python", "empty", section)), section
