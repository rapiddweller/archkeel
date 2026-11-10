# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The dependency scope check parses only the records that the gap check asks for."""

from __future__ import annotations

import json
import random
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
from test_scoped_dependency_proof import RULE, _component, _project
from test_typescript_partial_uml import _TypeScriptCollector

import archkeel.check.observation as observation
from archkeel.check.observe import Observer
from archkeel.check.ports import ScanConfig
from archkeel.check.report import run_report
from archkeel.ir.facts import ProducerKind
from archkeel.ir.source_records import LazyParsed

CONFIG = ScanConfig(("src",), "demo", "architecture-contract.json", "unused", language="typescript")


def _eager(raw: Mapping[str, Any], parse: Callable[[Any], Any]) -> dict[str, Any]:
    """The earlier definition: parse every record before the first lookup."""
    return {key: parse(item) for key, item in raw.items()}


def _git(root: Path) -> None:
    for command in (
        ("git", "init", "-q", "-b", "main"),
        ("git", "config", "user.email", "test@example.invalid"),
        ("git", "config", "user.name", "Test"),
        ("git", "add", "-A"),
        ("git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)


def _generated(root: Path, seed: int, size: int | None = None) -> None:
    """A flat project with random imports and random dynamic imports; some are complete."""
    rng = random.Random(seed)
    names = [f"f{index}" for index in range(size or rng.randint(2, 6))]
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("A generated target.\n")
    dynamic = size is not None or rng.random() < 0.7
    for name in names:
        text = "export {};\n"
        if dynamic and rng.random() < 0.4:
            text += "export const load = (id: string) => import(id);\n"
        for other in rng.sample(names, k=rng.randint(0, 2)):
            if other != name:
                text += f"import './{other}';\n"
        (root / f"src/{name}.ts").write_text(text)
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"module": "commonjs"}, "include": ["src"]})
    )
    groups = [names[index::2] for index in range(2)]
    components = [
        _component(
            f"g{index}",
            group,
            requires=[
                {"component": f"g{1 - index}", "rationale": "Use it.", "decided_by": "architect"}
            ]
            if rng.random() < 0.5
            else [],
        )
        for index, group in enumerate(groups)
        if group
    ]
    (root / "architecture-contract.json").write_text(
        json.dumps({"schema_version": "2.2.0", "components": components, "rules": [RULE]})
    )
    _git(root)


def _encoded(root: Path) -> bytes:
    _, encoded = run_report(
        root, config=CONFIG, analyzer=Observer(_TypeScriptCollector(), producer=ProducerKind.PYTHON)
    )
    assert encoded is not None
    return encoded


def _parses(root: Path, *, lazy: bool) -> tuple[list[str], bytes]:
    """Return what observation.py parses itself, and the bytes of the report."""
    parsed: list[str] = []
    parse_record, parse_evidence = observation.parse_record, observation.parse_evidence

    def record(raw: Any, *args: Any) -> Any:
        parsed.append("record")
        return parse_record(raw, *args)

    def evidence(raw: Any, *args: Any) -> Any:
        parsed.append("evidence")
        return parse_evidence(raw, *args)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(observation, "parse_record", record)
        patch.setattr(observation, "parse_evidence", evidence)
        patch.setattr(observation, "LazyParsed", LazyParsed if lazy else _eager)
        return parsed, _encoded(root)


@pytest.mark.parametrize("seed", range(24))
def test_lazy_and_eager_certification_write_the_same_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: int
) -> None:
    root = tmp_path / "project"
    _generated(root, seed)
    lazy = _encoded(root)
    monkeypatch.setattr(observation, "LazyParsed", _eager)
    assert _encoded(root) == lazy


@pytest.mark.parametrize("options", [{}, {"dynamic_a": True}, {"forbidden": True}])
def test_lazy_and_eager_certification_agree_on_the_nested_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, options: dict[str, bool]
) -> None:
    _project(tmp_path / "project", **options)
    lazy = _encoded(tmp_path / "project")
    monkeypatch.setattr(observation, "LazyParsed", _eager)
    assert _encoded(tmp_path / "project") == lazy


def test_an_incomplete_scan_parses_fewer_records_than_the_eager_check(tmp_path: Path) -> None:
    _generated(tmp_path / "project", seed=3, size=60)
    lazy, lazy_bytes = _parses(tmp_path / "project", lazy=True)
    eager, eager_bytes = _parses(tmp_path / "project", lazy=False)
    assert lazy_bytes == eager_bytes
    # Other certifiers parse their own records; the check saves about six parses per file.
    assert len(eager) - len(lazy) > 5 * 60


def test_a_complete_scan_parses_the_same_for_both_paths(tmp_path: Path) -> None:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs/target.md").write_text("A target.\n")
    (root / "src/a.ts").write_text("export {};\n")
    (root / "src/b.ts").write_text("import './a';\n")
    (root / "tsconfig.json").write_text(
        json.dumps({"compilerOptions": {"module": "commonjs"}, "include": ["src"]})
    )
    (root / "architecture-contract.json").write_text(
        json.dumps(
            {
                "schema_version": "2.2.0",
                "components": [_component("all", ["a", "b"])],
                "rules": [RULE],
            }
        )
    )
    _git(root)
    lazy, lazy_bytes = _parses(root, lazy=True)
    eager, eager_bytes = _parses(root, lazy=False)
    assert lazy_bytes == eager_bytes
    assert len(lazy) == len(eager)  # a complete scan returns before the check parses anything


def _failure(root: Path, field: str, *, lazy: bool) -> tuple[int, str, str]:
    """Run with one broken internal record; return the exit code, the diagnostic kind and claim."""
    _project(root)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(observation, "LazyParsed", LazyParsed if lazy else _eager)
        evaluate = observation.evaluate_source

        def corrupt(*args: Any, **kwargs: Any) -> Any:
            scan = evaluate(*args, **kwargs)
            items = getattr(scan, field)
            assert items
            del items[-1]["id" if field == "evidence" else "area"]
            return scan

        patch.setattr(observation, "evaluate_source", corrupt)
        result, encoded = run_report(
            root,
            config=CONFIG,
            analyzer=Observer(_TypeScriptCollector(), producer=ProducerKind.PYTHON),
        )
    assert encoded is None
    (diagnostic,) = result.diagnostics
    return result.exit_code, str(diagnostic.kind), diagnostic.unknown_claim


@pytest.mark.parametrize(
    ("field", "claim"),
    [
        ("modules", "record fields mismatch"),
        ("unknowns", "record fields mismatch"),
        ("evidence", "'id'"),
    ],
)
def test_an_invalid_internal_record_fails_with_the_same_diagnostic_on_both_paths(
    tmp_path: Path, field: str, claim: str
) -> None:
    expected = (2, "parse_error", claim)
    assert _failure(tmp_path / "lazy", field, lazy=True) == expected
    assert _failure(tmp_path / "eager", field, lazy=False) == expected


def test_lazy_parsed_parses_a_key_once_and_only_when_asked() -> None:
    calls: list[str] = []

    def parse(raw: str) -> str:
        calls.append(raw)
        if raw == "bad":
            raise ValueError("invalid")
        return raw.upper()

    items = LazyParsed({"a": "x", "b": "y", "c": "bad"}, parse)
    assert len(items) == 3 and set(items) == {"a", "b", "c"}
    assert calls == []
    assert items["a"] == "X" and items["a"] == "X" and items.get("a") == "X" and "a" in items
    assert calls == ["x"]
    assert items.get("z") is None and items.get("z", "d") == "d" and "z" not in items
    with pytest.raises(KeyError):
        items["z"]
    with pytest.raises(ValueError, match="invalid"):
        items["c"]
    assert calls == ["x", "bad"]
