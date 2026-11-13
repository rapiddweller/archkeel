# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Regenerate parser probes exclusively from the unchanged main repository's public tests."""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

FILES = tuple(
    "tests/test_typescript_" + name + ".py"
    for name in (
        "array_constants",
        "decorated_inventory",
        "inner",
        "jsdoc_import",
        "jsx_attributes",
        "parameter_properties",
        "parse",
        "script_globals",
    )
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-worktree", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, output = args.main_worktree.resolve(), args.output.resolve()
    checkout = Path(__file__).resolve().parents[1]
    assert output.is_relative_to(checkout), "typescript_oracle_source_outside_public_roots"

    def git(*arguments):
        return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()

    sha = git("rev-parse", "HEAD")
    assert git("merge-base", sha, "origin/main") == sha
    assert not git("status", "--porcelain", "--untracked-files=no")
    sys.path.insert(0, str(root / "tests"))
    import pytest
    from archkeel.analyzer.typescript import collect, parse
    from test_collector_native_imports import _request, _view
    from test_collector_native_syntax import _c_locale, _python

    assert Path(parse.__file__).resolve().is_relative_to(root / "src")
    original = parse.parse
    cases: dict[str, list[dict]] = {}
    seen: set[tuple[str, str, bytes]] = set()
    probes: list[tuple[str, str, bytes]] = []
    base = checkout / "test-artifacts" / ("public-parser-" + str(os.getpid()))
    base.mkdir(parents=True)

    def recorded(rel, data, *a, **kw):
        result = original(rel, data, *a, **kw)
        test = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" (", 1)[0]
        if test.split("::", 1)[0] not in FILES:
            return result
        identity = (test, rel, data)
        if identity in seen:
            return result
        seen.add(identity)
        probes.append(identity)
        return result

    for module in list(sys.modules.values()):
        if (
            module.__name__.startswith("archkeel.analyzer.typescript")
            and getattr(module, "parse", None) is original
        ):
            module.parse = recorded
    status = pytest.main(["-q", "-n", "0", "--basetemp", str(base / "pytest"), *FILES])
    assert status == 0, "typescript_oracle_public_tests_failed"
    for test, rel, data in probes:
        relative = Path(rel)
        assert not relative.is_absolute() and ".." not in relative.parts
        relative = relative if relative.parts[0] == "src" else Path("src") / relative
        with tempfile.TemporaryDirectory(dir=base) as folder:
            project = Path(folder)
            source = project / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(data)
            (project / "tsconfig.json").write_text(
                '{"compilerOptions":{"allowJs":true},"include":["src"]}'
            )
            with _c_locale():
                syntax = _python(relative.as_posix(), data)
                facts = _view(collect.collect(_request(project, "app", "tsconfig.json")))
        cases.setdefault(test, []).append(
            {
                "rel": relative.as_posix(),
                "source": base64.b64encode(data).decode(),
                "syntax": syntax,
                "facts": facts,
            }
        )
    assert cases, "typescript_oracle_parser_cases_missing"
    content = json.dumps(cases, sort_keys=True, separators=(",", ":")).encode()
    output.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "main_sha": sha,
                    "python": platform.python_version(),
                    "public_tests": FILES,
                    "content_digest": hashlib.sha256(content).hexdigest(),
                    "cases": cases,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode(),
            mtime=0,
        )
    )
    print(f"Recorded {sum(map(len, cases.values()))} public parser probes.")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
