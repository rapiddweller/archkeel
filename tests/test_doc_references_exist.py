# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Find broken explicit repository paths and decision numbers in documentation."""

from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = re.compile(r"`([^`\n]+)`")
AD = re.compile(r"\bAD-(\d+)\b")
PATH = re.compile(
    r"(?:docs|native|src|tests|tools|schema|fixtures)/[\w./-]+\.(?:py|rs|md|json|toml|js|css)"
)
WORD = re.compile(r"[A-Za-z_]\w*")
SYMBOL = re.compile(r"\bPython `([A-Za-z_]\w*)`")
DEFINITION = re.compile(
    r"\b(?:def|class|fn|struct|enum|trait|type|const|static|mod)\s+([A-Za-z_]\w*)"
)
ASSIGNMENT = re.compile(r"^\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=", re.M)
# A line that names the past says so with one of these words; the reference is then history.
HISTORY = re.compile(
    r"\b(deleted|removed|replaced|formerly|former|retired|previously|history|"
    r"4\.\d\.\d|no longer|renamed|dropped|sample|the user's project|your project)\b",
    re.I,
)
DECISIONS = "docs/architecture/decisions/"


def python_docs(path: Path) -> list[tuple[int, str]]:
    """Extract docstrings without treating Python code as documentation."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr):
                value = body[0].value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.append((value.lineno, value.value))
    return found


def documents(root: Path) -> list[tuple[Path, int, str]]:
    """Return Markdown, Rust doc comments and Python docstrings."""
    found = []
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")
    for name in tracked:
        path = root / name
        if name.endswith(".md") and (
            name.startswith("docs/") or name in ("README.md", "CONTRIBUTING.md")
        ):
            found.extend(
                (path, line, text) for line, text in enumerate(path.read_text().splitlines(), 1)
            )
        elif name.startswith("native/") and name.endswith(".rs"):
            found.extend(
                (path, line, text)
                for line, text in enumerate(path.read_text().splitlines(), 1)
                if re.match(r"^\s*//[/!]", text)
            )
        elif (
            name.startswith("native/report/assets/")
            and name.endswith((".js", ".css"))
            # Third-party code that we vendor unchanged: its comments name the paths of its
            # own repository.
            and ".bundled." not in name
        ):
            found.extend(
                (path, line, text)
                for line, text in enumerate(path.read_text().splitlines(), 1)
                if re.match(r"^\s*(//|/\*|\*)", text)
            )
        elif name.startswith("src/") and name.endswith(".py"):
            found.extend((path, line, text) for line, text in python_docs(path))
    return found


def history_paths(root: Path) -> set[str]:
    """Return every path that any commit of this repository ever held."""
    out = subprocess.check_output(
        ["git", "log", "--all", "--name-only", "--pretty=format:"], cwd=root
    ).decode()
    return set(out.split("\n"))


def defined_symbols(root: Path) -> set[str]:
    """Return every identifier that code, a schema or a contract uses outside of comments."""
    found: set[str] = set()
    patterns = ("src/**/*.py", "tools/**/*.py", "native/**/*.rs", "schema/*.json", "native/*.json")
    for pattern in patterns:
        for path in root.glob(pattern):
            if "target" in path.parts:
                continue
            for text in path.read_text(encoding="utf-8").splitlines():
                if not text.lstrip().startswith(("//", "#")):
                    found.update(WORD.findall(text))
    return found


def missing(root: Path, documents_: list[tuple[Path, int, str]]) -> list[str]:
    """List each missing path, decision or symbol with its location.

    A line that names the past (a HISTORY word) may name what no longer exists. A decision
    record is history as a whole: a path in it passes when some commit held that path, so a
    typo still fails. No other exception exists.
    """
    decisions = {
        int(match.group(1))
        for path in (root / "docs/architecture/decisions").glob("ad-*.md")
        if (match := re.match(r"ad-(\d+)-", path.name))
    }
    problems = []
    symbols = defined_symbols(root)
    past: set[str] | None = None
    for path, line, text in documents_:
        where = f"{path.relative_to(root)}:{line}"
        history = bool(HISTORY.search(text))
        for number in AD.findall(text):
            if int(number) not in decisions and not history:
                problems.append(f"{where}: missing AD-{number}")
        for code in CODE.findall(text) + (
            PATH.findall(text) if path.suffix in (".js", ".css") else []
        ):
            if PATH.fullmatch(code) and not (root / code).is_file() and not history:
                if where.startswith(DECISIONS):
                    past = history_paths(root) if past is None else past
                    if code in past:
                        continue
                problems.append(f"{where}: missing {code}")
        for symbol in SYMBOL.findall(text):
            if symbol not in symbols and not history:
                problems.append(f"{where}: missing symbol {symbol}")
    return problems


def test_missing_explicit_path_and_decision_are_reported(tmp_path: Path) -> None:
    decisions = tmp_path / "docs/architecture/decisions"
    decisions.mkdir(parents=True)
    (decisions / "ad-123-example.md").write_text("# Example\n")
    doc = tmp_path / "docs/example.md"
    problems = missing(
        tmp_path,
        [(doc, 4, "AD-123 `docs/missing.md` AD-124")],
    )
    assert problems == [
        "docs/example.md:4: missing AD-124",
        "docs/example.md:4: missing docs/missing.md",
    ]


def test_explicit_documentation_references_exist() -> None:
    problems = missing(ROOT, documents(ROOT))
    assert not problems, "\n".join(problems)


def test_a_history_word_or_a_commit_in_history_excuses_only_what_it_names(tmp_path: Path) -> None:
    """A deleted path passes on a history line, and a typo in a decision record fails."""
    decisions = tmp_path / "docs/architecture/decisions"
    decisions.mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    old = tmp_path / "tools/old.py"
    old.parent.mkdir()
    old.write_text("x = 1\n")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run([*git, "add", "."], cwd=tmp_path, check=True)
    subprocess.run([*git, "commit", "-qm", "add"], cwd=tmp_path, check=True)
    old.unlink()
    doc = tmp_path / "docs/example.md"
    record = decisions / "ad-2-record.md"
    problems = missing(
        tmp_path,
        [
            (doc, 1, "`tools/old.py` is deleted."),
            (doc, 2, "`tools/old.py` runs it."),
            (record, 3, "`tools/old.py` ran it."),
            (record, 4, "`tools/typo.py` ran it."),
            (doc, 5, "The deleted Python `_gone` and Python `_also`."),
            (doc, 6, "Python `_nope` is not defined anywhere."),
        ],
    )
    assert problems == [
        "docs/example.md:2: missing tools/old.py",
        "docs/architecture/decisions/ad-2-record.md:4: missing tools/typo.py",
        "docs/example.md:6: missing symbol _nope",
    ]


def test_the_flow_runtime_names_the_hash_of_its_source() -> None:
    """The generator of `flow.runtime.js` is gone, so its stated source hash is the only check."""
    import hashlib

    assets = ROOT / "native/report/assets/explorer"
    stated = re.search(r"source-sha256=([0-9a-f]{64})", (assets / "flow.runtime.js").read_text())
    assert stated, "flow.runtime.js names no source hash"
    assert stated.group(1) == hashlib.sha256((assets / "flow.js").read_bytes()).hexdigest()
