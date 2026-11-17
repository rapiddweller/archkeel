# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The quick start of the README, end to end, on a fresh TypeScript project (#1754).

`archkeel validate`, `archkeel report --output report.html`, `archkeel validate` again: the page
that ArchKeel wrote into the project must not change the verdict of the next run. The draft never
takes ArchKeel's own outputs (`report.html`, `test-artifacts/`) into the scan.
"""

import json
import subprocess
from pathlib import Path

import pytest

from archkeel.cli import core_only
from archkeel.cli.init_draft import draft

GIT = ["git", "-c", "user.email=a@b", "-c", "user.name=a"]
PROJECT = {
    "package.json": '{"name": "app", "private": true}',
    "tsconfig.json": json.dumps({"compilerOptions": {"strict": True}, "include": ["src"]}),
    "src/a/index.ts": 'import { b } from "../b";\nexport const a = b;\n',
    "src/b/index.ts": "export const b = 1;\n",
}


def _project(root: Path, extra: dict[str, str] | None = None) -> Path:
    for name, text in {**PROJECT, **(extra or {})}.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=root, check=True)
    subprocess.run([*GIT, "commit", "-qm", "plant"], cwd=root, check=True)
    return root


def _verdict(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = core_only.run(list(argv))
    out = capsys.readouterr().out
    return code, next(line for line in out.splitlines() if line.startswith(f"{argv[0]}:"))


def test_the_quick_start_gives_the_same_verdict_before_and_after_the_report_page(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _project(tmp_path / "app")
    monkeypatch.chdir(root)
    first = _verdict(capsys, "validate", "--text")
    code, _ = _verdict(capsys, "report", "--output", "report.html", "--text")
    assert (root / "report.html").is_file() and code == first[0]
    again = _verdict(capsys, "validate", "--text")
    assert again == first, (first, again)


def test_the_draft_never_takes_archkeels_own_outputs_into_the_scan(tmp_path: Path) -> None:
    root = _project(
        tmp_path / "app",
        {"report.html": "<script>1</script>\n", "test-artifacts/r.html": "<script>1</script>\n"},
    )
    config = next(f for f in draft(root).files if f.path == "archkeel.toml").text
    roots = json.loads(config.split("roots = ", 1)[1].splitlines()[0])
    assert "report.html" not in roots and "test-artifacts" not in roots, roots
    assert roots == ["src"], roots
