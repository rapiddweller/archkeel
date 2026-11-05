# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the Studio API on a real server: 127.0.0.1, one token, read-only, versioned."""

import http.client
import json
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from test_explore import _repository, _tree_digest

from archkeel.cli import _decode_snapshot as _decode
from archkeel.cli import build_parser, main, studio_workspace
from archkeel.cli.config import load_config
from archkeel.ir.facts import SourceResolution
from archkeel.studio.api import API_VERSION, CallStatus, ContractState, ExploreState, graph_json
from archkeel.studio.graph import build_graph
from archkeel.studio.server import Studio
from archkeel.studio.workspace import Workspace
from fixtures.demo_catalog_typescript import VARIANTS as TYPESCRIPT_VARIANTS
from fixtures.reproduce_typescript import repository as typescript_repository

_SCHEMA = json.loads((Path(__file__).parents[1] / "schema/studio-api-1.5.schema.json").read_bytes())
# The real ArchKeel snapshot takes 95 to 124 s on a laptop and more on a loaded 4 vCPU runner.
_EXPLORE_SECONDS = 300


def _no_contract(_modules: Sequence[str]) -> list[tuple[str, str, list[str]]]:
    return []


def _workspace(root: Path, cache: Path, *options: str) -> Workspace:
    """The workspace that `archkeel studio --root ROOT OPTIONS` makes, with its cache in `cache`."""
    return studio_workspace(
        build_parser().parse_cli_args(["studio", "--root", str(root), *options]), cache
    )


def _start(root: Path, cache: Path, *options: str) -> Studio:
    server = Studio(_workspace(root, cache, *options))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _stop(server: Studio) -> None:
    server.shutdown()
    server.server_close()


@contextmanager
def running(root: Path, cache: Path, *options: str, explored: bool = False) -> Iterator[Studio]:
    """A started Studio that stops afterwards; `explored` waits for the snapshot first."""
    server = _start(root, cache, *options)
    try:
        if explored:
            assert explore(server, login(server))["explore"] == "done"
        yield server
    finally:
        _stop(server)


@pytest.fixture
def studio(tmp_path: Path) -> Iterator[Studio]:
    with running(_repository(tmp_path / "shop"), tmp_path / "cache") as server:
        yield server


def request(
    server: Studio,
    path: str,
    *,
    method: str = "GET",
    cookie: str | None = None,
    host: str | None = None,
) -> tuple[http.client.HTTPResponse, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=10)
    headers = {"Host": host or f"127.0.0.1:{server.port}"}
    if cookie is not None:
        headers["Cookie"] = cookie
    connection.request(method, path, headers=headers)
    response = connection.getresponse()
    return response, response.read()


def login(server: Studio) -> str:
    """Follow the start URL once and return the cookie that the browser keeps."""
    start = urlsplit(server.url)
    response, _ = request(server, f"{start.path}?{start.query}")
    assert response.status == 303
    assert response.getheader("Location") == "/"
    cookie = response.getheader("Set-Cookie")
    assert cookie is not None
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    return cookie.split(";", 1)[0]


def _validator(answer: str) -> Draft202012Validator:
    """The validator for one answer of the API: `state` or `graph`."""
    return Draft202012Validator({"$ref": f"#/$defs/{answer}", "$defs": _SCHEMA["$defs"]})


def validate(payload: object, name: str) -> None:
    """Check a JSON body against one definition of the API schema."""
    schema = {"$schema": _SCHEMA["$schema"], "$defs": _SCHEMA["$defs"], "$ref": f"#/$defs/{name}"}
    checked_schema = json.loads(
        (Path(__file__).parents[1] / "schema/view-check-1.3.schema.json").read_bytes()
    )
    candidate_schema = json.loads(
        (Path(__file__).parents[1] / "schema/view-spec.schema.json").read_bytes()
    )
    registry = (
        Registry()
        .with_resource(checked_schema["$id"], Resource.from_contents(checked_schema))
        .with_resource(candidate_schema["$id"], Resource.from_contents(candidate_schema))
    )
    Draft202012Validator(schema, registry=registry).validate(payload)


def state(server: Studio, cookie: str) -> dict:
    response, body = request(server, "/api/v1/state", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "application/json"
    payload = json.loads(body)
    _validator("state").validate(payload)
    return payload


def graph(server: Studio, cookie: str) -> dict:
    response, body = request(server, "/api/v1/graph", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "application/json"
    payload = json.loads(body)
    _validator("graph").validate(payload)
    return payload


def explore(server: Studio, cookie: str) -> dict:
    """Start the explore run of the workspace and wait until it ends."""
    server.workspace.start()
    deadline = time.monotonic() + _EXPLORE_SECONDS
    while (current := state(server, cookie))["explore"] == "running":
        assert time.monotonic() < deadline, current
        time.sleep(0.2)
    return current


def test_the_schema_has_the_version_of_the_server() -> None:
    Draft202012Validator.check_schema(_SCHEMA)
    assert {
        _SCHEMA["$defs"][name]["properties"]["api_version"]["const"]
        for name in ("state", "chat_response", "chat_error")
    } == {API_VERSION}
    assert _SCHEMA["$id"] == f"urn:archkeel:studio-api:{API_VERSION}"


def test_a_story_response_resolves_its_view_check_schema() -> None:
    check = {
        "result_schema_version": "1.3.0",
        "schema_version": "1.2.0",
        "title": "Example",
        "exit_code": 0,
        "strict": False,
        "snapshot": {"source_digest": "a" * 64, "contract_digest": "b" * 64},
        "view_snapshot": {"source_digest": "a" * 64, "contract_digest": "b" * 64},
        "snapshot_current": True,
        "snapshot_completeness": "complete",
        "nodes": [],
        "edges": [],
        "steps": [],
        "author_notes": [],
        "stops": [],
        "story": {
            "id": "example",
            "title": "Example",
            "chapters": [],
            "steps": [],
            "verdict": {
                "proven": 0,
                "declared": 0,
                "claim": 0,
                "unknown": 0,
                "missing": 0,
                "systems": [],
                "modules": 0,
            },
        },
    }
    validate(
        {
            "api_version": API_VERSION,
            "id": "example",
            "source": "local",
            "checked": check,
            "rebound": False,
            "created": {"created": None, "git_head": None, "author_kind": None, "agent": None},
            "head": None,
        },
        "story",
    )


def test_the_state_names_the_selected_agent(studio: Studio) -> None:
    answer = state(studio, login(studio))
    assert answer["agent"] == "claude"


def test_story_counts_and_incomplete_state_require_the_matching_api_schema() -> None:
    schema_folder = Path(__file__).parents[1] / "schema"
    old = json.loads((schema_folder / "studio-api-1.1.schema.json").read_bytes())
    previous = json.loads((schema_folder / "studio-api-1.2.schema.json").read_bytes())
    prior = json.loads((schema_folder / "studio-api-1.3.schema.json").read_bytes())
    row = {
        "id": "example",
        "title": "Example",
        "steps": 1,
        "source": "local",
        "created": None,
        "checked_counts": None,
    }
    old_row_schema = old["$defs"]["stories"]["properties"]["stories"]["items"]
    current_row_schema = _SCHEMA["$defs"]["stories"]["properties"]["stories"]["items"]

    assert not Draft202012Validator(old_row_schema).is_valid(row)
    assert Draft202012Validator(current_row_schema).is_valid(row)
    assert not Draft202012Validator(previous["$defs"]["explore"]).is_valid("incomplete")
    assert prior["$id"] == "urn:archkeel:studio-api:1.3.0"
    assert Draft202012Validator(_SCHEMA["$defs"]["explore"]).is_valid("incomplete")


def test_the_schema_rejects_a_field_that_it_does_not_name(studio: Studio) -> None:
    """Negative control: `additionalProperties: false` and fixed rows hold at every level."""
    cookie = login(studio)
    answer = state(studio, cookie)
    assert not _validator("state").is_valid({**answer, "extra": 1})
    assert not _validator("state").is_valid({**answer, "api_version": "1.0.0"})
    assert not _validator("graph").is_valid({"api_version": API_VERSION, "explore": "idle"})
    waiting = graph(studio, cookie)
    assert not _validator("graph").is_valid({**waiting, "extra": 1})
    empty = {name: [] for name in ("components", "modules", "symbols", "edges", "unknown")}
    empty["components_from"] = "layout"
    empty["totals"] = {"analyzed": 0, "resolved": 0, "partial": 0, "unresolved": 0}
    empty["snapshot"] = {"git_head": "", "source_digest": "", "dirty": False}
    full = {**waiting, "graph": empty}
    assert _validator("graph").is_valid(full)
    assert not _validator("graph").is_valid({**full, "graph": {**empty, "extra": []}})
    assert not _validator("graph").is_valid(
        {**full, "graph": {**empty, "edges": [[0, 1, False, 3]]}}
    )
    assert not _validator("graph").is_valid(
        {**full, "graph": {**empty, "edges": [[0, 1, False, 3, 0, "extra"]]}}
    )
    assert not _validator("graph").is_valid(
        {**full, "graph": {**empty, "symbols": [[0, "a", 1, "enum", "", 0, 0]]}}
    )
    assert not _validator("graph").is_valid(
        {**full, "graph": {**empty, "components_from": "guess"}}
    )
    assert not _validator("graph").is_valid({**full, "graph": {**empty, "totals": {"analyzed": 0}}})
    del empty["components_from"]
    assert not _validator("graph").is_valid({**full, "graph": empty})


def test_the_server_listens_on_127_0_0_1_on_a_free_port(studio: Studio) -> None:
    host, port = studio.server_address[:2]
    assert (host, port) == ("127.0.0.1", studio.port)
    assert port != 0
    assert studio.url.startswith(f"http://127.0.0.1:{port}/?token=")


@pytest.mark.parametrize(
    "path", ["/", "/api/v1/state", "/api/v1/graph", "/ui/studio.js", "/files/architecture.json"]
)
def test_a_request_without_the_token_gets_403(studio: Studio, path: str) -> None:
    assert request(studio, path)[0].status == 403
    assert request(studio, path, cookie=f"{studio.cookie}=wrong")[0].status == 403


def test_a_wrong_token_in_the_start_url_gets_403(studio: Studio) -> None:
    response, _ = request(studio, "/?token=wrong")
    assert response.status == 403
    assert response.getheader("Set-Cookie") is None


def test_another_host_header_gets_403_also_with_the_cookie(studio: Studio) -> None:
    cookie = login(studio)
    for host in (f"evil.test:{studio.port}", f"localhost:{studio.port}"):
        assert request(studio, "/", cookie=cookie, host=host)[0].status == 403


@pytest.mark.parametrize("path", ["/api/v1/state", "/api/v1/graph"])
@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_the_api_is_read_only(studio: Studio, method: str, path: str) -> None:
    cookie = login(studio)
    assert request(studio, path, method=method, cookie=cookie)[0].status == 405


def test_the_start_url_opens_the_shell_and_its_assets(studio: Studio) -> None:
    cookie = login(studio)
    response, body = request(studio, "/", cookie=cookie)
    assert response.status == 200
    assert "default-src 'none'" in response.getheader("Content-Security-Policy", "")
    assert b'<script src="/ui/studio.js"' in body
    for name in ("studio.js", "tokens.css", "studio.css"):
        assert request(studio, f"/ui/{name}", cookie=cookie)[0].status == 200, name
    for path in ("/ui/AGENTS.md", "/ui/main.tsx", "/unknown", "/api/v2/state"):
        assert request(studio, path, cookie=cookie)[0].status == 404, path


def test_two_servers_do_not_share_a_cookie(studio: Studio) -> None:
    other = Studio(studio.workspace)
    try:
        assert studio.cookie != other.cookie
    finally:
        other.server_close()


def test_the_contract_state_comes_from_the_root(tmp_path: Path) -> None:
    configured = _repository(tmp_path / "configured")
    assert main(["init", "--root", str(configured), "--json"]) == 0
    invalid = tmp_path / "invalid"
    invalid.mkdir()
    (invalid / "archkeel.toml").write_text("[scan\n")
    # A valid archkeel.toml with a contract that does not parse, or that the parser refuses.
    broken = {}
    for name, text in (("json", "{not json"), ("schema", '{"schema_version": "2.2.0"}')):
        broken[name] = _repository(tmp_path / f"broken-{name}")
        assert main(["init", "--root", str(broken[name]), "--json"]) == 0
        (broken[name] / load_config(broken[name]).contract).write_text(text)
    for folder, expected in (
        (_repository(tmp_path / "shop"), "not_configured"),
        (configured, "configured"),
        (invalid, "invalid"),
        (broken["json"], "invalid"),
        (broken["schema"], "invalid"),
    ):
        with running(folder, tmp_path / "cache") as server:
            assert state(server, login(server))["contract"] == expected


def test_explore_writes_only_the_cache_and_the_repository_stays_unchanged(
    studio: Studio, tmp_path: Path
) -> None:
    cookie = login(studio)
    before = _tree_digest(studio.workspace.root)
    outside = set(tmp_path.iterdir())
    assert state(studio, cookie)["explore"] == "idle"

    result = explore(studio, cookie)

    assert result["explore"] == "done", result
    assert result["exit_code"] == 0
    assert result["root_name"] == "shop"
    assert _tree_digest(studio.workspace.root) == before
    assert set(tmp_path.iterdir()) == outside | {tmp_path / "cache"}
    assert studio.workspace.folder.is_relative_to(tmp_path / "cache")
    response, body = request(studio, "/files/architecture.report.html", cookie=cookie)
    assert response.status == 200
    assert response.getheader("Content-Type") == "text/html"
    assert b"ArchKeel" in body


def test_the_graph_answers_like_the_state_until_the_snapshot_is_done(studio: Studio) -> None:
    cookie = login(studio)
    assert graph(studio, cookie) == {"api_version": API_VERSION, "explore": "idle", "graph": None}


@pytest.mark.parametrize("snapshot", ["missing", "corrupt"])
def test_a_missing_or_unreadable_snapshot_stays_failed_without_a_graph(
    tmp_path: Path, snapshot: str
) -> None:
    root = _repository(tmp_path / "shop")
    with running(root, tmp_path / "cache") as server:
        path = server.workspace.folder / "architecture.json"
        script = (
            "pass"
            if snapshot == "missing"
            else (f"from pathlib import Path; Path({str(path)!r}).write_text('{{not json')")
        )
        server.workspace._explore = (sys.executable, "-c", script)
        cookie = login(server)

        result = explore(server, cookie)
        answer = graph(server, cookie)

    assert result["explore"] == "failed"
    assert result["notes"] and "readable architecture.json" in result["notes"][-1]
    assert answer == {"api_version": API_VERSION, "explore": "failed", "graph": None}


def _names(rows: list, column: int = 0) -> list:
    return [row[column] for row in rows]


def test_the_graph_holds_the_calls_of_the_snapshot(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"

    answer = graph(studio, cookie)

    assert answer["explore"] == "done"
    body = answer["graph"]
    # No contract: the top-level packages of the explore layout; the root module has no owner.
    assert body["components_from"] == "layout"
    assert body["components"] == [
        ["app", ""],
        ["cli", ""],
        ["store", ""],
        ["(unowned)", "Modules without a single owning component."],
    ]
    modules = {row[0]: row for row in body["modules"]}
    assert modules["shop.app.orders"] == ["shop.app.orders", "shop/app/orders.py", 0, "orders"]
    assert modules["shop"][2:] == [3, "shop"]
    symbols = body["symbols"]
    place, save = (_names(symbols, 1).index(name) for name in ("place", "save"))
    assert symbols[place][2:4] == [4, "function"]
    assert symbols[place][4] == "def place() -> int:"
    # `place` calls `save` on line 5: a resolved call, so not partial.
    assert body["edges"] == [[place, save, False, 5, 0]]
    # Nothing is unknown or outside the scan in this repository.
    assert [row[5:] for row in symbols] == [[0, 0]] * len(symbols)
    assert body["unknown"] == []
    for module, *_ in symbols:
        assert 0 <= module < len(body["modules"])
    for _name, _file, component, _relative in body["modules"]:
        assert 0 <= component < len(body["components"])


def test_the_contract_names_the_components_and_their_responsibility(tmp_path: Path) -> None:
    root = _repository(tmp_path / "shop")
    assert main(["init", "--root", str(root), "--json"]) == 0
    path = root / load_config(root).contract
    contract = json.loads(path.read_text())
    app, cli, store = contract["components"]
    # One component owns two packages, which the explore layout keeps apart; one owns nothing.
    ghost = {**cli, "id": "COMP-GHOST", "label": "ghost", "packages": ["shop.ghost"]}
    app.update(label="services", packages=["shop.app", "shop.store"], public=[])
    app["responsibilities"] = ["Place orders and keep them."]
    store["packages"] = ["shop.store.unused"]
    path.write_text(json.dumps({**contract, "components": [app, cli, store, ghost]}))
    with running(root, tmp_path / "cache", explored=True) as server:
        body = graph(server, login(server))["graph"]
    assert body["components_from"] == "contract"
    assert body["components"] == [
        ["services", "Place orders and keep them."],
        ["cli", ""],
        ["(unowned)", "Modules without a single owning component."],
    ]
    owner = {row[0]: body["components"][row[2]][0] for row in body["modules"]}
    assert owner["shop.store.repository"] == "services"
    assert owner["shop.cli.__main__"] == "cli"
    assert owner["shop"] == "(unowned)"
    relative = {row[0]: row[3] for row in body["modules"]}
    # `services` shares the prefix `shop`; the unowned root module keeps its own name.
    assert relative["shop.store.repository"] == "store.repository"
    assert relative["shop"] == "shop"


def _synthetic_snapshot(modules: int, symbols_per_module: int, calls_per_symbol: int) -> dict:
    """A decoded snapshot with the size of a large repository: 1185 modules, 8000+ symbols."""
    names = [f"big.pkg{index % 40}.mod{index}" for index in range(modules)]
    symbols = [
        (f"{name}.f{number}", name, index * symbols_per_module + number)
        for index, name in enumerate(names)
        for number in range(symbols_per_module)
    ]
    evidence = [
        {"id": "EVD-1", "file": "big/x.py", "line": 7, "excerpt": "    def f(a, b):" + "x" * 90}
    ]
    calls = []
    for number, (qualified, _module, _) in enumerate(symbols):
        for step in range(calls_per_symbol):
            target = symbols[(number * 7 + step * 131 + 1) % len(symbols)][0]
            resolved = step == 0
            calls.append(
                {
                    "evidence_ids": ["EVD-1"],
                    "data": {
                        "source_scope": qualified,
                        "status": "resolved" if resolved else "partially_resolved",
                        "targets": [target] if resolved else [target, symbols[0][0], target],
                        "expression": "x" * 80,
                        "reason": "r" * 80,
                    },
                }
            )
    return {
        "modules": [
            {"title": name, "data": {"file": name.replace(".", "/") + ".py"}} for name in names
        ],
        "symbols": [
            {
                "kind": "method",
                "evidence_ids": ["EVD-1"],
                "data": {"module": module, "qualified_name": qualified},
            }
            for qualified, module, _ in symbols
        ],
        "calls": calls
        + [
            {
                "evidence_ids": ["EVD-1"],
                "data": {"source_scope": symbols[0][0], "status": "unresolved", "targets": []},
            }
        ]
        * 6,
        "evidence": evidence,
    }


def test_the_graph_of_a_large_repository_is_small_and_fast() -> None:
    # EE: 1185 modules, 8179 symbols, 14089 edges. Gate (issue #815): under 2 MB and 2 s.
    snapshot = _synthetic_snapshot(1185, 7, 2)
    started = time.perf_counter()
    built = build_graph(snapshot, _no_contract)
    body = graph_json(ExploreState.DONE, built)
    seconds = time.perf_counter() - started
    assert (len(built.modules), len(built.symbols)) == (1185, 8295)
    # One resolved edge and two partial edges for each symbol: 1.8 times the edges of EE.
    assert len(built.edges) == 3 * len(built.symbols)
    assert len(body) < 2_000_000, len(body)
    assert seconds < 2, seconds
    _validator("graph").validate(json.loads(body))
    # An unresolved call is kept up to four times for each symbol; the symbol holds the true number.
    assert len(built.unknown) == 4
    assert built.symbols[0].unknown == 6
    assert sum(edge.partial for edge in built.edges) == 2 * len(built.symbols)


def test_a_damaged_columnar_snapshot_stays_failed_without_a_graph(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    path = studio.workspace.folder / "architecture.json"
    damaged = json.loads(path.read_text())
    # A string reference past the end of the table raises IndexError inside the codec.
    damaged["string_table"] = damaged["string_table"][:2]
    server_script = (
        "from pathlib import Path; "
        f"Path({str(path)!r}).write_text({json.dumps(json.dumps(damaged))!r})"
    )
    studio.workspace._explore = (sys.executable, "-c", server_script)

    result = explore(studio, cookie)
    answer = graph(studio, cookie)

    assert result["explore"] == "failed"
    assert result["notes"] and "readable architecture.json" in result["notes"][-1]
    assert answer["graph"] is None


def test_a_restart_cannot_reuse_a_previous_snapshot(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    snapshot = studio.workspace.folder / "architecture.json"
    studio.workspace._explore = (sys.executable, "-c", "raise SystemExit(2)")

    studio.workspace.start()
    deadline = time.monotonic() + 10
    while studio.workspace.state().explore is ExploreState.RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)

    assert studio.workspace.state().explore is ExploreState.FAILED
    assert not snapshot.exists()
    assert studio.workspace.graph() is None


def test_a_nonzero_exit_stays_failed_even_if_it_writes_a_snapshot(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    snapshot = studio.workspace.folder / "architecture.json"
    contents = snapshot.read_bytes()
    script = (
        "from pathlib import Path; "
        f"Path({str(snapshot)!r}).write_bytes({contents!r}); "
        "raise SystemExit(7)"
    )
    studio.workspace._explore = (sys.executable, "-c", script)

    studio.workspace.start()
    deadline = time.monotonic() + 10
    while studio.workspace.state().explore is ExploreState.RUNNING and time.monotonic() < deadline:
        time.sleep(0.01)

    assert studio.workspace.state().explore is ExploreState.FAILED
    assert studio.workspace.graph() is None


def test_call_status_has_the_values_of_the_source_resolution_of_the_ir() -> None:
    # Studio may not import `ir`: its vocabulary is a copy, and this test ties it to the source.
    assert {member.value for member in CallStatus} == {member.value for member in SourceResolution}


def _tiny_snapshot(calls: list[dict]) -> dict:
    """One module `pkg.m` with the functions A, B, C and D, and the given calls."""
    names = ["A", "B", "C", "D"]
    return {
        "modules": [{"title": "pkg.m", "data": {"file": "pkg/m.py"}}],
        "symbols": [
            {
                "kind": "function",
                "evidence_ids": ["E"],
                "data": {"module": "pkg.m", "qualified_name": f"pkg.m.{name}"},
            }
            for name in names
        ],
        "calls": [{"evidence_ids": ["E"], "data": data} for data in calls],
        "evidence": [{"id": "E", "line": 3, "excerpt": "def f():"}],
    }


def _call(source: str, status: str, *targets: str) -> dict:
    return {
        "source_scope": f"pkg.m.{source}",
        "status": status,
        "targets": [t if "." in t else f"pkg.m.{t}" for t in targets],
        "expression": "x",
        "reason": "r",
    }


def test_the_graph_counts_call_sites_and_keeps_distinct_partial_targets() -> None:
    built = build_graph(
        _tiny_snapshot(
            [
                # One site, targets A, A, B: both A and B stay, as two edges of one site.
                _call("C", "partially_resolved", "A", "A", "B"),
                _call("C", "resolved", "A"),
                # Outside the scan: neither an edge nor unknown, resolved or partial alike.
                _call("C", "resolved", "os.getcwd"),
                _call("C", "partially_resolved", "os.getcwd", "re.sub"),
                _call("C", "resolved"),
                _call("C", "unresolved"),
                _call("D", "unresolved"),
            ]
        ),
        _no_contract,
    )

    assert [(e.target, e.partial, e.site) for e in built.edges] == [
        (0, True, 0),
        (1, True, 0),
        (0, False, 1),
    ]
    c, d = built.symbols[2], built.symbols[3]
    assert (c.outside, c.unknown) == (3, 1)
    assert (d.outside, d.unknown) == (0, 1)
    assert [row.symbol for row in built.unknown] == [2, 3]


def test_the_graph_of_real_code_has_partial_unknown_and_outside_calls(tmp_path: Path) -> None:
    files = {
        "shop/__init__.py": "",
        "shop/table.py": (
            "import os\n\n\nclass Table:\n    def add_column(self, name: str) -> None:\n"
            "        pass\n\n\ndef build() -> int:\n    verdicts = Table()\n"
            '    verdicts.add_column("check")\n    return len(os.getcwd())\n\n\n'
            "def run(callback) -> None:\n    callback()\n"
        ),
        "pyproject.toml": '[project]\nname = "shop"\nrequires-python = ">=3.11"\n',
    }
    with running(
        _repository(tmp_path / "shop", files), tmp_path / "cache", explored=True
    ) as server:
        body = graph(server, login(server))["graph"]
    by_name = {row[1]: index for index, row in enumerate(body["symbols"])}
    build, run, column = by_name["build"], by_name["run"], by_name["Table.add_column"]
    # A call on a receiver of a class of the scan is partly resolved: a claim, not a proof.
    assert [edge for edge in body["edges"] if edge[0] == build and edge[2]] == [
        [build, column, True, 11, 0]
    ]
    # `len` and `os.getcwd` lie outside the scan.
    assert body["symbols"][build][6] == 2
    assert body["symbols"][run][5:] == [1, 0]
    assert [row[:2] for row in body["unknown"]] == [[run, "callback"]]


def _large_repository(root: Path, modules: int = 1185, packages: int = 40) -> Path:
    """A repository of `modules` modules, each with 7 functions that call other modules."""
    files = {
        "pyproject.toml": '[project]\nname = "big"\nrequires-python = ">=3.11"\n',
        "big/__init__.py": "",
    }
    files |= {f"big/pkg{package}/__init__.py": "" for package in range(packages)}
    for index in range(modules):
        first, second = (index * 31 + 97) % modules, (index * 31 + 194) % modules
        lines = [f"from big.pkg{n % packages} import mod{n}" for n in (first, second)] + [""]
        for number in range(7):
            lines.append(
                f"def f{number}(x):\n    y = mod{first}.f{(number + 1) % 7}(x)\n"
                f"    return mod{second}.f{(number + 2) % 7}(y)\n"
            )
        files[f"big/pkg{index % packages}/mod{index}.py"] = "\n".join(lines)
    return _repository(root, files)


def test_decode_and_graph_of_a_real_snapshot_of_1185_modules(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _large_repository(tmp_path / "big")
    output = tmp_path / "out"
    assert main(["explore", "--root", str(root), "--output", str(output), "--json"]) == 0
    capsys.readouterr()
    raw = (output / "architecture.json").read_bytes()

    started = time.perf_counter()
    model = _decode(raw)
    decoded = time.perf_counter()
    built = build_graph(model, _no_contract)
    body = graph_json(ExploreState.DONE, built)
    finished = time.perf_counter()

    assert len(built.modules) >= 1185
    assert len(built.edges) > 10000
    assert len(body) < 2_000_000, len(body)
    _validator("graph").validate(json.loads(body))
    # The gate of issue #815 is 2 s for the route. Measured on 2026-11-04 (1185 modules, 17 MB):
    # decode 0.7 s, build 0.04 s. The bound here is wide, so a slow runner does not fail it.
    assert finished - started < 10, (decoded - started, finished - decoded)


def test_exit_two_with_a_snapshot_exposes_the_graph_and_diagnostic(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Keep the public alias fixture, then add one parse failure and one unknown call.
    root = tmp_path / "typescript-shop"
    shutil.copytree(Path(__file__).parents[1] / "fixtures/F-typescript-story", root)
    order = root / "src/app/order.ts"
    order.write_text(
        order.read_text() + "\nexport function uncertain() { return missingService.run(); }\n"
    )
    (root / "src/app/broken.ts").write_text("export function broken(: number { return 1; }\n")
    for command in (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "studio-test@example.invalid"),
        ("git", "config", "user.name", "Studio test"),
        ("git", "add", "-A"),
        ("git", "commit", "-qm", "generic TypeScript fixture"),
    ):
        subprocess.run(command, cwd=root, check=True, capture_output=True)
    options = (
        "--language",
        "typescript",
        "--source",
        "src",
        "--namespace",
        "demo",
        "--tsconfig",
        "tsconfig.json",
    )
    output = tmp_path / "preflight"
    code = main(["explore", "--root", str(root), *options, "--output", str(output), "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 2, payload
    assert (output / "architecture.json").is_file()
    partial = build_graph(_decode((output / "architecture.json").read_bytes()), _no_contract)
    assert partial.unknown

    with running(root, tmp_path / "cache", *options) as server:
        story_folder = root / ".archkeel/stories"
        story_folder.mkdir(parents=True)
        (story_folder / "partial.story.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.2.0",
                    "title": "Partial source flow",
                    "snapshot": {"source_digest": "a" * 64, "contract_digest": "b" * 64},
                    "nodes": ["demo.uncertain", "demo.missingService.run"],
                    "story": {"id": "partial", "title": "Partial source flow", "chapters": []},
                    "steps": [
                        {
                            "node": "demo.uncertain",
                            "note": "The function calls an unresolved alias.",
                        },
                        {"node": "demo.missingService.run", "note": "The unresolved target."},
                    ],
                }
            )
        )
        result = explore(server, login(server))
        cookie = login(server)
        answer = graph(server, cookie)
        listing = json.loads(_get(server, cookie, "/api/v1/stories")[1])["stories"]
        checked = json.loads(_get(server, cookie, "/api/v1/stories/partial")[1])
        draft_response, draft_body = _get(server, cookie, "/api/v1/draft?from=demo.uncertain")
        report_response, _ = request(server, "/files/architecture.report.html", cookie=cookie)
    assert result["explore"] == "incomplete"
    assert result["exit_code"] == 2
    assert result["notes"], result
    assert answer["explore"] == "incomplete"
    assert answer["graph"] is not None
    assert answer["graph"]["unknown"]
    assert listing[0]["checked_counts"]["unknown"] > 0
    assert checked["checked"]["snapshot_completeness"] == "incomplete"
    assert "unknown" in [step["status"] for step in checked["checked"]["steps"]]
    assert draft_response.status == 503
    assert b"incomplete snapshot" in draft_body
    assert report_response.status == 200


def test_a_runtime_mismatch_note_shows_current_and_required_python() -> None:
    from archkeel.studio.workspace import _notes

    notes = _notes(
        b'{"diagnostics":[{"kind":"runtime_mismatch",'
        b'"subject":"python 3.11.12 < requires-python >=3.12",'
        b'"unknown_claim":"AST may differ from target runtime",'
        b'"remedy":"uvx --python <compatible-version> archkeel <command>"}]}',
        b"",
    )

    assert notes == (
        "python 3.11.12 < requires-python >=3.12. "
        "AST may differ from target runtime. "
        "uvx --python <compatible-version> archkeel <command>",
    )


def test_a_story_route_reports_failed_explore_and_its_notes(tmp_path: Path) -> None:
    with running(_repository(tmp_path / "shop", commit=False), tmp_path / "cache") as server:
        cookie = login(server)
        result = explore(server, cookie)
        assert result["explore"] == "failed"
        response, body = _get(server, cookie, "/api/v1/stories/any-story")

    assert response.status == 503
    assert b"explore failed" in body.lower()
    assert any(note.encode() in body for note in result["notes"] if note)


@pytest.mark.parametrize(
    "name", ["../shop/pyproject.toml", "..%2Fshop%2Fpyproject.toml", "nothing.html", ""]
)
def test_files_serves_only_a_file_of_the_snapshot_folder(studio: Studio, name: str) -> None:
    assert request(studio, f"/files/{name}", cookie=login(studio))[0].status == 404


def test_the_studio_package_does_not_import_the_cli() -> None:
    loaded = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, archkeel.studio.server; "
            "print(sorted(m for m in sys.modules"
            " if m.startswith('archkeel.') or m == 'webbrowser'))",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "archkeel.studio.server" in loaded
    assert "archkeel.cli" not in loaded
    # The CLI opens the browser; the server starts no process.
    assert "'webbrowser'" not in loaded


def test_the_root_of_the_file_system_has_a_name() -> None:
    workspace = Workspace(
        Path("/"), Path("/nothing"), (), lambda: ContractState.NOT_CONFIGURED, _no_contract, _decode
    )
    assert workspace.state().root_name == "/"


def test_each_studio_run_has_its_own_private_cache_folder(tmp_path: Path) -> None:
    root = _repository(tmp_path / "shop")
    first, second = _workspace(root, tmp_path / "cache"), _workspace(root, tmp_path / "cache")
    assert first.folder != second.folder
    assert first.folder.parent == second.folder.parent
    assert first.folder.is_relative_to(tmp_path / "cache")
    assert first.folder.stat().st_mode & 0o777 == 0o700
    first.close()
    assert not first.folder.exists()
    assert second.folder.is_dir()


def test_studio_forwards_the_scope_options_to_explore(tmp_path: Path) -> None:
    clean = next(item for item in TYPESCRIPT_VARIANTS if item.id == "typescript-clean")
    root = typescript_repository(tmp_path, clean)
    options = ("--language", "typescript", "--source", "src", "--namespace", "shop")
    with running(root, tmp_path / "cache", *options, "--tsconfig", "tsconfig.json") as server:
        cookie = login(server)
        result = explore(server, cookie)
        page, _ = request(server, "/files/architecture.report.html", cookie=cookie)
    assert result["explore"] == "done", result
    assert page.status == 200


def _running_child(tmp_path: Path, script: str) -> Workspace:
    """A workspace whose explore child runs `script` and touches `ready` when it is set up."""
    workspace = Workspace(
        tmp_path,
        tmp_path / "run",
        (sys.executable, "-c", script),
        lambda: ContractState.CONFIGURED,
        _no_contract,
        _decode,
    )
    workspace.start()
    deadline = time.monotonic() + 30
    while not (tmp_path / "ready").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert (tmp_path / "ready").exists()
    return workspace


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_close_lets_explore_unwind_before_it_kills(tmp_path: Path) -> None:
    unwound = tmp_path / "unwound"
    workspace = _running_child(
        tmp_path,
        "import pathlib, time\n"
        "try:\n"
        f"    pathlib.Path({str(tmp_path / 'ready')!r}).touch()\n"
        "    time.sleep(60)\n"
        "finally:\n"
        f"    pathlib.Path({str(unwound)!r}).touch()\n",
    )
    workspace.close()
    assert unwound.exists()


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_close_kills_an_explore_that_ignores_the_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("archkeel.studio.workspace._UNWIND_SECONDS", 0.5)
    workspace = _running_child(
        tmp_path,
        "import pathlib, signal, time\n"
        "signal.signal(signal.SIGINT, signal.SIG_IGN)\n"
        f"pathlib.Path({str(tmp_path / 'ready')!r}).touch()\n"
        "time.sleep(60)\n",
    )
    child = workspace._child
    assert child is not None
    workspace.close()
    assert child.poll() is not None


_VIEW_CHECK = json.loads((Path(__file__).parents[1] / "schema/view-check.schema.json").read_bytes())
_PLACE = "shop.app.orders.place"


def _get(server: Studio, cookie: str, path: str) -> tuple[http.client.HTTPResponse, bytes]:
    return request(server, path, cookie=cookie)


def test_there_is_no_story_before_the_folder_has_one(studio: Studio) -> None:
    cookie = login(studio)
    response, body = _get(studio, cookie, "/api/v1/stories")
    assert response.status == 200
    assert json.loads(body) == {"api_version": API_VERSION, "stories": []}
    assert _get(studio, cookie, "/api/v1/stories/none")[0].status == 503  # snapshot not ready


def test_a_draft_spec_comes_from_the_trace_and_the_check_proves_it(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"

    response, body = _get(studio, cookie, f"/api/v1/draft?from={_PLACE}")
    assert response.status == 200
    validate(json.loads(body), "draft")
    spec = json.loads(body)["spec"]
    assert spec["schema_version"] == "1.2.0"
    assert spec["nodes"][0] == _PLACE
    assert [step["node"] for step in spec["steps"]] == spec["nodes"]
    assert all(set(step) == {"node"} for step in spec["steps"])  # no text: the agent adds it

    folder = _local(studio)
    folder.mkdir(parents=True)
    (folder / "place-draft.story.json").write_text(json.dumps(spec))
    (folder / "broken.story.json").write_text("{")
    validate(json.loads(_get(studio, cookie, "/api/v1/stories")[1]), "stories")
    listing = json.loads(_get(studio, cookie, "/api/v1/stories")[1])["stories"]
    story_answer = json.loads(_get(studio, cookie, "/api/v1/stories/place-draft")[1])
    checked_counts = story_answer["checked"]["story"]["verdict"]
    assert listing == [
        {
            "id": "broken",
            "title": "broken",
            "steps": 0,
            "source": "local",
            "created": None,
            "checked_counts": None,
        },
        {
            "id": "place-draft",
            "title": f"Story from {_PLACE}",
            "steps": len(spec["steps"]),
            "source": "local",
            "created": None,
            "checked_counts": {
                key: checked_counts[key]
                for key in ("proven", "declared", "claim", "unknown", "missing")
            },
        },
    ]

    response, body = _get(studio, cookie, "/api/v1/stories/place-draft")
    assert response.status == 200
    answer = json.loads(body)
    validate(answer, "story")
    assert answer["id"] == "place-draft"
    Draft202012Validator(_VIEW_CHECK).validate(answer["checked"])
    statuses = [step["status"] for step in answer["checked"]["steps"]]
    assert set(statuses) <= {"proven", "claim", "unknown"}
    assert "proven" in statuses  # `place` calls `save`: a resolved call
    assert [row["index"] for row in answer["checked"]["story"]["steps"]] == list(
        range(len(spec["steps"]))
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/stories/..%2Fstate",
        "/api/v1/stories/a.b",
        "/api/v1/stories/Upper",
        "/api/v1/stories/x/y",
    ],
)
def test_a_story_id_cannot_leave_the_folder(studio: Studio, path: str) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    assert _get(studio, cookie, path)[0].status == 404


def test_a_bad_draft_or_spec_gets_a_message_not_a_stack_trace(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    response, body = _get(studio, cookie, "/api/v1/draft?from=no.such.function")
    assert response.status == 422
    assert b"no.such.function" in body
    folder = _local(studio)
    folder.mkdir(parents=True)
    (folder / "bad.story.json").write_text('{"schema_version": "9"}')
    assert _get(studio, cookie, "/api/v1/stories/bad")[0].status == 422
    assert _get(studio, cookie, "/api/v1/draft")[0].status == 422


def _local(studio: Studio) -> Path:
    """The local stories folder of the server: below the cache, outside the run folder."""
    assert studio.workspace.stories is not None
    return studio.workspace.stories.folders[-1][1]


def test_the_stories_folder_lies_outside_the_run_folder(studio: Studio) -> None:
    assert _local(studio) == studio.workspace.folder.parent / "stories"


def _repository_folder(studio: Studio) -> Path:
    return studio.workspace.root / ".archkeel" / "stories"


def _story_spec(spec: dict, **changes: object) -> bytes:
    return json.dumps({**spec, **changes}).encode()


def test_a_committed_story_is_checked_on_the_current_snapshot_whatever_its_digests(
    studio: Studio,
) -> None:
    """AD-291: a stored spec does not depend on one snapshot: the digests are rebound in memory."""
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    spec = json.loads(_get(studio, cookie, f"/api/v1/draft?from={_PLACE}")[1])["spec"]
    other = {"source_digest": "a" * 64, "contract_digest": "b" * 64}
    folder = _repository_folder(studio)
    folder.mkdir(parents=True)
    path = folder / "place.story.json"
    stored = _story_spec(
        spec,
        snapshot=other,
        created="2026-11-04T10:00:00Z",
        git_head="c" * 40,
        author_kind="agent",
        agent="claude",
    )
    path.write_bytes(stored)

    answer = json.loads(_get(studio, cookie, "/api/v1/stories/place")[1])

    validate(answer, "story")
    assert answer["source"] == "repository"
    assert answer["rebound"] is True
    assert answer["checked"]["snapshot_current"] is True
    assert "proven" in [step["status"] for step in answer["checked"]["steps"]]
    assert answer["created"] == {
        "created": "2026-11-04T10:00:00Z",
        "git_head": "c" * 40,
        "author_kind": "agent",
        "agent": "claude",
    }
    assert len(answer["head"]) == 40  # the commit of the repository now
    assert path.read_bytes() == stored  # Studio rewrote nothing


def test_a_story_on_the_current_snapshot_is_not_rebound(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    spec = json.loads(_get(studio, cookie, f"/api/v1/draft?from={_PLACE}")[1])["spec"]
    folder = _repository_folder(studio)
    folder.mkdir(parents=True)
    (folder / "now.story.json").write_bytes(_story_spec(spec))
    answer = json.loads(_get(studio, cookie, "/api/v1/stories/now")[1])
    assert answer["rebound"] is False
    assert answer["created"] == dict.fromkeys(("created", "git_head", "author_kind", "agent"))


def test_a_node_that_is_gone_is_missing_and_not_dropped(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    spec = json.loads(_get(studio, cookie, f"/api/v1/draft?from={_PLACE}")[1])["spec"]
    gone = "shop.app.orders.vanished"
    spec["nodes"] = [*spec["nodes"], gone]
    spec["steps"] = [*spec["steps"], {"node": gone}]
    folder = _repository_folder(studio)
    folder.mkdir(parents=True)
    (folder / "gone.story.json").write_bytes(
        _story_spec(spec, snapshot={"source_digest": "a" * 64, "contract_digest": "b" * 64})
    )
    answer = json.loads(_get(studio, cookie, "/api/v1/stories/gone")[1])
    steps = answer["checked"]["steps"]
    assert len(steps) == len(spec["steps"])  # no step is dropped
    assert steps[-1]["status"] == "missing"
    assert answer["checked"]["exit_code"] == 1
    assert answer["rebound"] is True


def test_the_repository_story_wins_over_the_local_one_of_the_same_id(studio: Studio) -> None:
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    spec = json.loads(_get(studio, cookie, f"/api/v1/draft?from={_PLACE}")[1])["spec"]
    repository = _repository_folder(studio)
    repository.mkdir(parents=True)
    local = _local(studio)
    local.mkdir(parents=True)
    (repository / "same.story.json").write_bytes(_story_spec(spec, title="From the repository"))
    (local / "same.story.json").write_bytes(_story_spec(spec, title="From the cache"))
    (local / "only-local.story.json").write_bytes(_story_spec(spec, title="Only here"))
    rows = json.loads(_get(studio, cookie, "/api/v1/stories")[1])["stories"]
    assert [(row["id"], row["title"], row["source"]) for row in rows] == [
        ("only-local", "Only here", "local"),
        ("same", "From the repository", "repository"),
    ]
    answer = json.loads(_get(studio, cookie, "/api/v1/stories/same")[1])
    assert answer["source"] == "repository"
    assert answer["checked"]["title"] == "From the repository"


def test_a_root_without_a_stories_folder_lists_none_and_writes_none(studio: Studio) -> None:
    cookie = login(studio)
    assert json.loads(_get(studio, cookie, "/api/v1/stories")[1])["stories"] == []
    assert not _repository_folder(studio).exists()


def test_the_graph_carries_the_call_totals_and_the_revision_of_the_snapshot(studio: Studio) -> None:
    """The Briefing shows these numbers: they come from the coverage and the source of explore."""
    cookie = login(studio)
    assert explore(studio, cookie)["explore"] == "done"
    body = graph(studio, cookie)["graph"]
    totals = body["totals"]
    assert totals["analyzed"] == totals["resolved"] + totals["partial"] + totals["unresolved"]
    assert totals["resolved"] >= 1  # `place` calls `save`
    snapshot = body["snapshot"]
    assert len(snapshot["git_head"]) == 40 and len(snapshot["source_digest"]) == 64
    assert snapshot["dirty"] is False
    saved = json.loads(
        (studio.workspace.folder / "architecture.json").read_bytes()
    )  # the columnar file, decoded below
    assert saved["coverage"]["calls_analyzed"] == totals["analyzed"]
