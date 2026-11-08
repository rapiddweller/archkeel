# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-320: the verdicts of the host with the native collector, against two Python collectors.

Consumer: the host (`run_report`). The native collector has the legacy capability: module-level
imports, no symbols and no script globals. Against the Python collector in the same legacy mode
(`native_oracle`) every verdict, cycle, dependency edge and gap must be equal. Against the Python
default collector the native verdict is the same or more cautious: UNKNOWN where the default
collector gives a fact, never complete where the default collector says UNKNOWN.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from archkeel.check.report import run_report
from archkeel.cli.config import load_config
from archkeel.cli.observe import observer_for
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
# Sections that count symbols or calls. The native scan does not measure them: the artifact says
# `None` where the legacy mode of Python says a measured zero. Every other section must be equal.
UNMEASURED = ("bindings", "calls", "references", "symbols", "metrics", "modules", "coverage")
NOT_MEASURED = ("bindings", "calls", "references", "symbols")
# A rule on symbols (a named port of a dependency or an interface) needs `symbols_known`, which the
# legacy capability does not carry. The host reads it as UNKNOWN instead of PASS or FAIL.
# These ids are the symbol-level rules that degrade to UNKNOWN.
SYMBOL_LEVEL = {
    "typescript-unsupported-target-symbol",
    "typescript-unsupported-symbol-interface",
    "typescript-unsupported-symbol-requires",
}
# The Python collector declares a partial construct capability and a reference inventory. The native
# scan declares neither, so its UNKNOWN records have another text. The verdict, the diagnostics, the
# violations and the cycles are equal.
CAPABILITY_TEXT = {
    "typescript-unsupported-catalog_use",
    "typescript-unsupported-forbidden_construct",
}


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
    skipped = (*PRODUCER, *UNMEASURED)
    kept = {key: value for key, value in sections.items() if key not in skipped}
    if argv is not None and argv[0] != sys.executable:
        # The native scan: each section of symbols and calls reads "not measured", not zero.
        assert all(sections.get(key) is None for key in NOT_MEASURED), sorted(sections)
        assert sections["coverage"]["calls_analyzed"] is None
    return {
        "declared": str(result.declared_rules.value),
        "complete": str(result.observation_complete.value),
        "exit": result.exit_code,
        "diagnostics": sorted(str(item.kind.value) for item in result.diagnostics),
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


def test_verdicts_equal_the_legacy_python_collector_on_the_fixtures(
    tmp_path: Path, native_binary: Path
) -> None:
    for index, name in enumerate(FIXTURES):
        root = _fixture(tmp_path / str(index), name)
        oracle = _verdict(root, (sys.executable, "-I", "-B", ORACLE))
        native = _verdict(root, (str(native_binary),))
        assert native == oracle, name


@pytest.mark.parametrize("index", range(len(VARIANTS)))
def test_verdicts_equal_the_legacy_python_collector_on_the_demo_variants(
    tmp_path: Path, native_binary: Path, index: int
) -> None:
    variant = VARIANTS[index]
    root = repository(tmp_path, variant)
    oracle = _verdict(root, (sys.executable, "-I", "-B", ORACLE))
    native = _verdict(root, (str(native_binary),))
    if variant.id in SYMBOL_LEVEL:
        # The oracle declares the symbol capability of the Python collector; the native scan cannot
        # judge a rule on symbols, so it says UNKNOWN and names the rule as unsupported.
        assert native["declared"] == native["complete"] == "UNKNOWN", variant.id
        assert "rule_unsupported_by_profile" in native["diagnostics"], variant.id
    elif variant.id in CAPABILITY_TEXT:
        assert _short(native) == _short(oracle), variant.id
        assert native["diagnostics"] == oracle["diagnostics"], variant.id
        for key in ("violations", "cycles"):
            assert native["artifact"][key] == oracle["artifact"][key], (variant.id, key)  # type: ignore[index]
    else:
        assert native == oracle, variant.id


def test_native_is_never_less_cautious_than_the_default_collector(
    tmp_path: Path, native_binary: Path
) -> None:
    more_cautious: set[str] = set()
    for index, variant in enumerate(VARIANTS):
        root = repository(tmp_path / str(index), variant)
        default = _verdict(root, None)
        native = _verdict(root, (str(native_binary),))
        # Missing evidence is UNKNOWN: a scan that the default collector cannot complete is never
        # complete here, and a verdict is the default verdict or UNKNOWN.
        if default["complete"] == "UNKNOWN":
            assert native["complete"] == "UNKNOWN", variant.id
        assert native["declared"] in (default["declared"], "UNKNOWN"), variant.id
        assert native["exit"] in (default["exit"], 2), variant.id
        if _short(default) != _short(native):
            more_cautious.add(variant.id)
    # The native collector examines no script global yet, so every scan with a file in the global
    # dependency scope has a gap. Only a scan of declaration files alone can match the default.
    assert len(more_cautious) >= 1
    print(sorted(more_cautious))
