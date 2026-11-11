# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Write the false-PASS probes as dual-run cases into `tests/dual_run/cases.json` (AD-360).

Run `uv run python -m tools.dual_run_capture`. It runs the probe tests with this module as a
pytest plugin. Each scan of a probe (`rust_repository.validate`, `false_pass_support.verdict`) is
captured: the tree as a fixture plus overlay, and the collector of the probe. A case of the file
that is not a probe (an id outside `probe/`) stays. Then run `make dual-run-record`.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

REPOSITORY = Path(__file__).resolve().parent.parent
CASES_FILE = REPOSITORY / "tests" / "dual_run" / "cases.json"
PROBE_FILES = (
    "tests/test_collector_false_pass_gate.py",
    "tests/test_collector_false_pass_full.py",
    "tests/test_collector_false_pass_sources.py",
    "tests/test_collector_false_pass_rust_impls.py",
    "tests/test_collector_false_pass_rust_layout.py",
    "tests/test_collector_false_pass_rust_test_targets.py",
)
SKIPPED = {".git", "node_modules", "__pycache__", ".dart_tool", "build"}
LONG_TEXT = 1000
CAPTURED: list[dict[str, Any]] = []
CURRENT = {"node": ""}


def _tree(root: Path) -> dict[str, str]:
    files = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_file() and not SKIPPED.intersection(relative.parts):
            try:
                files[relative.as_posix()] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
    return files


@functools.cache
def _fixtures() -> tuple[tuple[str, dict[str, str]], ...]:
    found = [("", {})]
    for directory in sorted((REPOSITORY / "fixtures").iterdir()):
        if (directory / "archkeel.toml").is_file():
            found.append((f"fixtures/{directory.name}", _tree(directory)))
    return tuple(found)


def _overlay(base: dict[str, str], tree: dict[str, str]) -> dict[str, str | None]:
    changed: dict[str, str | None] = {p: t for p, t in tree.items() if base.get(p) != t}
    changed.update({path: None for path in base if path not in tree})
    return changed


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def capture(root: Path, argv: list[str] | None, pinned: bool, strip_argv: bool) -> None:
    tree = _tree(root)
    if strip_argv and "archkeel.toml" in tree:
        lines = tree["archkeel.toml"].splitlines(keepends=True)
        tree["archkeel.toml"] = "".join(x for x in lines if not x.startswith("collector_argv"))
    fixture, files = min(
        ((name, _overlay(base, tree)) for name, base in _fixtures()),
        key=lambda pair: len(json.dumps(pair[1])),
    )
    if argv is not None:
        names = {sys.executable: "{python}"}
        argv = [names.get(item, item.replace(str(REPOSITORY), "{repository}")) for item in argv]
    stem, _, name = CURRENT["node"].partition("::")
    stem = Path(stem).stem.removeprefix("test_collector_false_pass_")
    CAPTURED.append(
        {
            "id": f"probe/{stem}-{_slug(name)}",
            "fixture": fixture,
            # The probe committed its tree, so the overlay is committed too.
            "base_files": dict(sorted(files.items())),
            "collector_argv": argv,
            "pinned": pinned and argv is not None,
        }
    )


def pytest_configure() -> None:
    sys.path.insert(0, str(REPOSITORY / "tests"))
    import false_pass_support
    import rust_repository

    validate = rust_repository.validate
    verdict = false_pass_support.verdict

    def captured_validate(root: Path, capsys: Any) -> Any:
        capture(root, ["{rust_collector}"], True, strip_argv=True)
        return validate(root, capsys)

    def captured_verdict(
        root: Path, language: str, argv: tuple[str, ...] | None, *, pinned: bool = False
    ) -> Any:
        capture(root, None if argv is None else list(argv), pinned, strip_argv=False)
        return verdict(root, language, argv, pinned=pinned)

    rust_repository.validate = captured_validate
    false_pass_support.verdict = captured_verdict


def pytest_runtest_setup(item: pytest.Item) -> None:
    CURRENT["node"] = item.nodeid
    module = getattr(item, "module", None)
    original = getattr(module, "_verdict", None)
    if module is None or original is None or getattr(original, "captured", False):
        return
    if not module.__name__.endswith("false_pass_sources"):
        return

    def captured_verdict(root: Path, argv: Any, directory: Path | None = None) -> Any:
        if directory is None:  # the Python collector; the native one is not a Python engine run
            capture(root, None, False, strip_argv=False)
        return original(root, argv, directory)

    captured_verdict.captured = True  # type: ignore[attr-defined]
    module._verdict = captured_verdict


def unique(captured: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One case for each distinct input; a repeated id gets a number."""
    seen: set[str] = set()
    ids: set[str] = set()
    cases = []
    for case in captured:
        key = json.dumps({k: v for k, v in case.items() if k != "id"}, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        identifier, number = case["id"], 2
        while identifier in ids:
            identifier, number = f"{case['id']}-{number}", number + 1
        ids.add(identifier)
        cases.append({**case, "id": identifier})
    return cases


def shared(case: dict[str, Any], texts: dict[str, str]) -> dict[str, Any]:
    """A long file text moves to the shared table: many probes share one contract."""
    files: dict[str, Any] = {}
    for path, text in case["base_files"].items():
        if text is not None and len(text) > LONG_TEXT:
            key = hashlib.sha256(text.encode()).hexdigest()[:16]
            texts[key] = text
            files[path] = {"text": key}
        else:
            files[path] = text
    return {**case, "base_files": files}


def main() -> int:
    status = pytest.main(
        ["-q", "-p", "no:randomly", "-p", "no:xdist", *PROBE_FILES], plugins=[sys.modules[__name__]]
    )
    stored = json.loads(CASES_FILE.read_text())
    kept = [c for c in stored["cases"] if not c["id"].startswith("probe/")]
    texts: dict[str, str] = {}
    cases = sorted(
        [*kept, *map(lambda c: shared(c, texts), unique(CAPTURED))], key=lambda c: c["id"]
    )
    lines = ",\n".join(json.dumps(case, sort_keys=True, ensure_ascii=False) for case in cases)
    table = json.dumps(dict(sorted(texts.items())), indent=0, ensure_ascii=False)
    CASES_FILE.write_text(f'{{"cases": [\n{lines}\n],\n"texts": {table}}}\n')
    print(f"{len(cases)} cases in {CASES_FILE.relative_to(REPOSITORY)}; pytest exit {status}")
    return 0 if status == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
