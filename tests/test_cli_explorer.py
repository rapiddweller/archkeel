# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Exercise the Explorer through its public CLI and localhost HTTP surface."""

import json
from concurrent.futures import ThreadPoolExecutor
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace

import pytest

from archkeel.cli import core_explorer, core_explorer_http, core_only
from archkeel.cli.core_arguments import parse
from archkeel.cli.core_frame import CoreCommand


def test_explorer_flags() -> None:
    options = parse(["explore", "--port", "9000", "--no-open", "--config", "system.json"])
    assert options.command is CoreCommand.EXPLORE
    assert options.port == 9000
    assert options.no_open and options.config_given
    with pytest.raises(ValueError, match="port"):
        parse(["explore", "--port", "65536"])


@pytest.mark.parametrize("command", ["explore", "studio"])
def test_explorer_accepts_a_project_path_and_rejects_two_roots(command: str) -> None:
    assert parse([command, "../repo", "--no-open"]).root == Path("../repo")
    assert parse([command, "--no-open", "../repo"]).root == Path("../repo")
    assert parse([command, "--root", "../repo"]).root == Path("../repo")
    with pytest.raises(ValueError, match="either a project path or --root"):
        parse([command, "../repo", "--root", "../other"])
    with pytest.raises(ValueError, match="either a project path or --root"):
        parse([command, "--root", "../other", "../repo"])


def test_studio_dispatches_and_shows_explorer_help(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        core_only, "_explore", lambda options, mode: 7 if options.root == Path("repo") else 8
    )
    assert core_only.run(["studio", "repo"]) == 7
    assert core_only.run(["studio", "--help"]) == 0
    assert "studio" in capsys.readouterr().out


def test_explorer_does_not_draft_a_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "unused")
    assert core_only.run(["explore", "--root", str(tmp_path), "--json"]) == 2
    assert "Git work tree" in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_report_builds_gap_link_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    (tmp_path / "archkeel.toml").write_text("")
    document = {"collection_gaps": [{"reason": "missing"}], "locations": {}}
    calls = []

    def exchange(
        options: object, project: object, binary: object, sink: object
    ) -> tuple[bytes, object]:
        calls.append(options)
        frame = SimpleNamespace(
            html='<section id="gap-records-file">Gap records file unavailable.</section>'
        )
        return json.dumps({**document, "html": frame.html}).encode(), frame

    def launch(
        options: object, mode: object, project: object, binary: object, scan: object, render: object
    ) -> int:
        assert not calls
        assert callable(render)
        page, (name, content) = render()
        assert name in page and "1 gap records" in page
        assert json.loads(content) == document
        return 0

    monkeypatch.setattr(core_only, "locate_core", lambda: tmp_path / "core")
    monkeypatch.setattr(core_only, "_exchange_scan", exchange)
    monkeypatch.setattr(core_explorer, "launch", launch)
    assert core_only.run(["explore", "--root", str(tmp_path), "--no-open"]) == 0
    assert len(calls) == 1
    assert not list(tmp_path.glob("archkeel-gaps-*.json"))


def test_explorer_queries_are_read_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def query(
        path: Path, root: Path, operation: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        assert path == tmp_path / "snapshot.sqlite3"
        assert root == tmp_path
        if operation == "source":
            raise ValueError("source changed since scan")
        assert operation == "children"
        return {"items": [arguments]}

    monkeypatch.setattr(core_explorer_http, "query", query)
    report = "<html><head><style>:root{--ink:black}</style></head><body>Report</body></html>"
    with (
        core_explorer._ExplorerServer(
            tmp_path / "snapshot.sqlite3",
            tmp_path,
            lambda: (report, ("archkeel-gaps-test.json", b'{"collection_gaps":[]}')),
            0,
        ) as server,
        ThreadPoolExecutor() as pool,
    ):
        running = pool.submit(server.serve_forever)
        try:
            client = HTTPConnection("127.0.0.1", server.server_port, timeout=3)

            def request(
                path: str, headers: dict[str, str] | None = None, method: str = "GET"
            ) -> tuple[int, bytes]:
                client.request(method, path, headers=headers or {})
                response = client.getresponse()
                return response.status, response.read()

            code, body = request("/")
            assert code == 200 and b'src="/explorer-story.js"' in body
            assert request("/explorer-story.js")[0] == 200
            assert b'src="/explorer-uml.js"' in body
            assert request("/explorer-uml.js")[0] == 200
            assert request("/report")[0] == 200
            assert request("/archkeel-gaps-test.json") == (200, b'{"collection_gaps":[]}')
            assert request("/archkeel-gaps-wrong.json")[0] == 404
            assert request("/report.css")[0] == 200
            assert b"--surface-0:" in request("/report.css")[1]
            code, body = request("/api/v1/children?parent=system")
            assert code == 200 and b'"parent": "system"' in body
            assert request("/api/children?parent=a&parent=b")[0] == 400
            code, body = request("/api/v1/source?reference=x")
            assert code == 409 and b"source changed since scan" in body
            assert request("/api/children", {"Host": "example.org"})[0] == 403
            assert request("/api/children", {"Origin": "https://example.org"})[0] == 403
            assert request("/api/children", {"Sec-Fetch-Site": "cross-site"})[0] == 403
            assert request("/api/children", method="POST")[0] == 405
            assert request("/api/anything")[0] == 404
        finally:
            server.shutdown()
            running.result(timeout=3)


@pytest.mark.parametrize(("limit", "expected_calls"), [(100, 1), (0, 2)])
def test_report_cache_is_bounded_and_checks_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, limit: int, expected_calls: int
) -> None:
    from contextlib import nullcontext

    identity = core_explorer.SnapshotIdentity("revision", "contract", "source")
    changed = core_explorer.SnapshotIdentity("changed", "contract", "source")
    state = [identity]
    snapshot_file = tmp_path / "snapshot"
    snapshot_file.touch()
    calls = []

    def render() -> tuple[str, tuple[str, bytes]]:
        calls.append(1)
        return "page", ("archkeel-gaps-test.json", b"gaps")

    class Server:
        server_port = 42

        def __init__(
            self, path: object, root: object, report: object, port: object, confirm: object
        ) -> None:
            self.report = report

        def __enter__(self) -> "Server":
            return self

        def __exit__(self, *args: object) -> None:
            pass

        def serve_forever(self) -> None:
            assert callable(self.report)
            assert self.report() == self.report()
            assert len(calls) == expected_calls
            state[0] = changed
            with pytest.raises(core_explorer.CoreError, match="changed after"):
                self.report()

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path.parent / "archkeel-test-cache"))
    monkeypatch.setattr(core_explorer, "_REPORT_CACHE_BYTES", limit)
    monkeypatch.setattr(core_explorer, "_fingerprint", lambda project, binary: (state[0], {}))
    monkeypatch.setattr(core_explorer, "cache_path", lambda *args: snapshot_file)
    monkeypatch.setattr(core_explorer, "open_snapshot", lambda *args: nullcontext())
    monkeypatch.setattr(core_explorer, "_ExplorerServer", Server)
    options = parse(["explore", "--no-open"])
    project = core_only.ProjectRoot.of(tmp_path, "archkeel.toml")
    assert (
        core_explorer.launch(options, core_only.OutputMode.TEXT, project, tmp_path, None, render)
        == 0
    )


def test_observed_scan_preserves_names_across_cold_builds(tmp_path: Path) -> None:
    from archkeel.cli.core_binding import ProjectRoot

    root = tmp_path.resolve() / "sample-rust"
    sources = {
        "Cargo.toml": '[package]\nname="sample-rust"\nversion="0.1.0"\nedition="2021"\n',
        "src/lib.rs": "pub struct Model;\n",
        "docs/architecture/architecture.md": "Owner notes",
        ".archkeel-observed": "Existing file",
    }
    digests = {}
    for name, content in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        digests[name] = core_explorer._file_digest(path)

    visits = []

    class ScanReached(Exception):
        pass

    def inspect(project: ProjectRoot) -> None:
        assert project.path.name == root.name
        assert project.path != root
        assert (project.path / "docs/architecture/architecture.md").read_text() == "Owner notes"
        visits.append((project.config, (project.path / project.config).read_text()))
        raise ScanReached

    for _ in range(2):
        with pytest.raises(ScanReached):
            core_explorer._observed_scan(ProjectRoot.top(root), digests, inspect)
    assert visits[0] == visits[1]
    assert not (root / visits[0][0]).exists()
