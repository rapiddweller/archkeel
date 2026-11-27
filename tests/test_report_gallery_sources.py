# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Real projects of the gallery: a pinned source, fetched at build time (AD-462)."""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

import pytest
from test_report_gallery import _build

from tools import fixture_source, fixture_tree, report_gallery, report_gallery_page

FIXTURES = report_gallery.ROOT / "fixtures"
PINNED = ("N-fastapi-realworld", "O-bazel-worker-realworld")


def _git(root: Path, *arguments: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=q@example.invalid", "-c", "user.name=Q", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _upstream(tmp_path: Path) -> dict:
    """A local repository that stands in for the project, and the spec that pins its commit."""
    repo = tmp_path / "upstream"
    (repo / "pkg" / "sub").mkdir(parents=True)
    (repo / "pkg" / "a.py").write_text("x = 1\n")
    (repo / "pkg" / "sub" / "b.py").write_text("y = 2\n")
    (repo / "pkg" / "skip.py").write_text("z = 3\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "one")
    commit = _git(repo, "rev-parse", "HEAD")
    copy = [{"from": "pkg", "to": "pkg", "exclude": ["skip.py"]}]
    return {
        "name": "Up",
        "repo": str(repo),
        "ref": None,
        "commit": commit,
        "license": "MIT",
        "copy": copy,
    }


def test_the_pinned_commit_is_fetched_once_and_the_cache_serves_the_next_build(
    tmp_path: Path,
) -> None:
    spec = _upstream(tmp_path)
    cache = tmp_path / "cache"
    with fixture_source.checkout(spec, cache) as first:
        assert _git(first, "rev-parse", "HEAD") == spec["commit"]
    # The upstream is gone: a second build must come from the cache.
    (tmp_path / "upstream").rename(tmp_path / "moved")
    with fixture_source.checkout(spec, cache) as second:
        assert second == first and (second / "pkg" / "a.py").is_file()


def test_a_fetch_that_fails_raises_and_leaves_no_partial_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    waits: list[float] = []
    # Only the module's own name: `time.sleep` is global, and the wait loop of `subprocess` calls it
    # in tiny steps while git runs.
    monkeypatch.setattr(fixture_source, "time", types.SimpleNamespace(sleep=waits.append))
    spec = {**_upstream(tmp_path), "commit": "0" * 40}
    cache = tmp_path / "cache"
    with (
        pytest.raises(fixture_source.SourceError, match="fetch"),
        fixture_source.checkout(spec, cache),
    ):
        pass
    assert [p.name for p in cache.iterdir()] == ["CACHEDIR.TAG"]
    # AD-1062: three attempts, a wait of 5 s and 15 s between them, no wait after the last.
    assert waits == [5, 15]


def test_the_copy_takes_the_listed_parts_and_leaves_out_git_and_the_excluded(
    tmp_path: Path,
) -> None:
    spec = _upstream(tmp_path)
    root = tmp_path / "root"
    root.mkdir()
    with fixture_source.checkout(spec, tmp_path / "cache") as checked:
        fixture_source.copy_source(checked, spec, root)
    assert sorted(p.name for p in (root / "pkg").rglob("*.py")) == ["a.py", "b.py"]
    assert not (root / ".git").exists()
    missing = {**spec, "copy": [{"from": "nothing", "to": "x"}]}
    with pytest.raises(fixture_source.SourceError, match="no nothing"):
        fixture_source.copy_source(checked, missing, root)


def test_a_fixture_with_a_pin_runs_in_a_committed_copy_that_holds_its_own_files_too(
    tmp_path: Path,
) -> None:
    spec = _upstream(tmp_path)
    fixture = tmp_path / "fx"
    fixture.mkdir()
    (fixture / "archkeel.toml").write_text("[scan]\n")
    (fixture / "SOURCE.json").write_text(json.dumps(spec))
    assert fixture_tree.needs_copy(fixture)
    with fixture_tree.fixture_tree(fixture, None, tmp_path / "cache") as tree:
        tracked = _git(tree, "ls-files").splitlines()
    assert "pkg/a.py" in tracked and "archkeel.toml" in tracked and "pkg/skip.py" not in tracked


@pytest.mark.parametrize("name", PINNED)
def test_a_real_project_fixture_holds_only_our_files_and_a_full_pin(name: str) -> None:
    folder = FIXTURES / name
    spec = fixture_source.load(folder)
    assert spec is not None
    assert len(spec["commit"]) == 40 and spec["repo"].startswith("https://github.com/")
    assert spec["license"] and spec["copy"]
    files = sorted(str(path.relative_to(folder)) for path in folder.rglob("*") if path.is_file())
    # Our contract, config, graph, pin and README: no source of the project.
    assert not any(file.endswith((".py", ".dart", ".ts")) for file in files), files
    assert {"SOURCE.json", "archkeel.toml", "architecture-contract.json"} <= set(files)


def test_a_pinned_run_shows_its_pin_and_a_failed_fetch_is_no_result_and_fails_the_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = next(run for run in report_gallery.showcase_runs() if run["name"] == PINNED[0])
    ok = report_gallery.build_run([sys.executable, "-c", "pass"], run, tmp_path / "a")
    assert ok["source"]["commit"] == fixture_source.load(FIXTURES / PINNED[0])["commit"]

    def broken(spec: dict, cache: Path | None = None) -> None:
        raise fixture_source.SourceError("network down")

    monkeypatch.setattr(fixture_source, "checkout", broken)
    row = report_gallery.build_run([sys.executable, "-c", "pass"], run, tmp_path / "b")
    assert "network down" in row["error"] and not row["links"]
    code, out = _build(tmp_path, report_gallery.MATRIX)
    assert code == 1
    assert "no result: " in (out / "showcase" / "index.html").read_text()


def test_the_card_states_the_pin_the_licence_and_that_only_the_contract_is_ours() -> None:
    pin = fixture_source.pin_facts(fixture_source.load(FIXTURES / PINNED[0]) or {})
    run = {"name": "n", "section": "real", "intent": "PASS", "about": "a"}
    summary = {"status": "PASS", "counts": {"PASS": 3, "FAIL": 0, "UNKNOWN": 0}, "gaps": {}}
    row = {"run": run, "links": [], "summary": {**summary, "refusal": None}, "source": pin}
    page = report_gallery_page.index([row], "sha", "now")
    assert f'<a href="{pin["repo"]}">FastAPI</a> 0.163.0 (MIT)' in page
    assert f"pinned commit <code>{pin['commit'][:12]}</code>" in page
    assert "The contract is ours." in page


def test_the_matrix_lists_both_real_projects_with_their_decided_result() -> None:
    # Release 5 gives FastAPI 10 accepted trojan horse gaps (AD-1053, AD-1058): UNKNOWN on purpose.
    pinned = {"N-fastapi-realworld": "UNKNOWN", "O-bazel-worker-realworld": "PASS"}
    runs = {run["name"]: run for run in report_gallery.showcase_runs()}
    for name in PINNED:
        assert runs[name]["section"] == "real" and runs[name]["intent"] == pinned[name]


def test_the_cache_folder_gets_one_cachedir_tag(tmp_path: Path) -> None:
    """AD-1211: the cache is marked, so a scan of a repository that holds it skips it."""
    cache = tmp_path / "test-artifacts" / "source-cache"
    fixture_source.mark_cache(cache)
    fixture_source.mark_cache(cache)
    assert (cache / "CACHEDIR.TAG").read_text(encoding="utf-8") == fixture_source.CACHE_TAG
    assert fixture_source.CACHE_TAG.startswith("Signature: 8a477f597d28d172789f06886806bc55")
