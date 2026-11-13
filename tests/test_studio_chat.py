# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-292: the Studio chat, on a real server, with a fake agent in place of claude and codex."""

import http.client
import json
import os
import shutil
import stat
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_explore import _repository
from test_studio import explore, login, running, validate

from archkeel.cli import build_parser
from archkeel.studio.agent import Agent
from archkeel.studio.answer import Snapshot
from archkeel.studio.api import (
    API_VERSION,
    AgentKind,
    ChatError,
    ChatFailure,
    ChatRequest,
)
from archkeel.studio.server import Studio

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")

_FILES = {
    "shop/__init__.py": "",
    "shop/app/__init__.py": "",
    "shop/app/orders.py": (
        "from shop.store.repository import save\n\n\n"
        "def place(callback) -> int:\n    callback()\n    return save(1)\n"
    ),
    "shop/store/__init__.py": "",
    "shop/store/repository.py": (
        "class Store:\n    def put(self, value: int) -> int:\n        return value\n\n\n"
        "def save(value: int) -> int:\n    return Store().put(value)\n"
    ),
    "shop/cli/__init__.py": "",
    "shop/cli/__main__.py": "from shop.app.orders import place\n\nplace(print)\n",
    "pyproject.toml": '[project]\nname = "shop"\nrequires-python = ">=3.11"\n',
}
PLACE = "shop.app.orders.place"
SAVE = "shop.store.repository.save"
STORE_CLASS = "shop.store.repository.Store"
STORE_PUT = "shop.store.repository.Store.put"

# The fake reads the question from the prompt, so the tests need no variable of the environment:
# the agent starts without the variables of its parent.
_FAKE = """#!PYTHON
import json, os, pathlib, signal, subprocess, sys, time
work = pathlib.Path("WORK")
prompt = sys.stdin.read()
call = {"argv": sys.argv[1:], "prompt": prompt, "cwd": os.getcwd(), "env": dict(os.environ)}
(work / "call.json").write_text(json.dumps(call))
question = next(line[10:] for line in prompt.splitlines() if line.startswith("Question: "))
answer = {"blocks": [
    {"kind": "claim", "text": "place calls save.", "refs": ["PLACE", "shop.nothing.here"]},
    {"kind": "proposal", "text": "Split place.", "refs": ["SAVE"]},
]}
if question == "ok":
    print(json.dumps(answer))
elif question == "fenced":
    print("```json\\n" + json.dumps(answer) + "\\n```")
elif question == "badjson":
    print("place calls save.")
elif question == "badkind":
    print(json.dumps({"blocks": [{"kind": "fact", "text": "t", "refs": []}]}))
elif question == "forged":
    print(json.dumps({"blocks": [{"kind": "claim", "text": "t", "refs": [], "observed": True}]}))
elif question == "big":
    sys.stdout.write("x" * 400000)
elif question == "nested":
    print("[" * 5000)
elif question == "noisy":
    sys.stderr.write("x" * 1000000)
    print(json.dumps(answer))
elif question == "fails":
    sys.stderr.write("boom sk-secret-in-a-log")
    sys.exit(3)
elif question == "writes":
    pathlib.Path(os.getcwd(), "agent-wrote.txt").write_text("x")
    print(json.dumps(answer))
elif question == "edits":
    with open("shop/app/orders.py", "a") as handle:
        handle.write("# edited\\n")
    print(json.dumps(answer))
elif question == "story method draft":
    print(json.dumps({"title": "Store puts a value", "steps": [
        {"node": "STORE_PUT", "note": "Stores the value."},
    ]}))
elif question == "story draft":
    print(json.dumps({"title": "Place an order", "steps": [
        {"node": "shop.app.orders.place", "note": "Start at the entry point."},
        {"node": "shop.missing.invented", "note": "This node was suggested by the agent."},
    ]}))
elif question == "story wrong start":
    print(json.dumps({"title": "Wrong starting point", "steps": [
        {"node": "shop.store.repository.save", "note": "Different valid node."},
        {"node": "shop.app.orders.place", "note": "Requested node appears later."},
    ]}))
elif question == "story empty note":
    print(json.dumps({"title": "Place an order", "steps": [
        {"node": "shop.app.orders.place", "note": ""},
    ]}))
elif question == "story whitespace note":
    print(json.dumps({"title": "Place an order", "steps": [
        {"node": "shop.app.orders.place", "note": " \t "},
    ]}))
elif question == "story malformed":
    print(json.dumps({"title": "Place an order", "steps": [], "verdict": "proven"}))
elif question == "story bad json":
    print("{not json")
elif question == "wait":
    (work / "started").touch()
    while not (work / "release").exists():
        time.sleep(0.05)
    print(json.dumps(answer))
elif question == "hang":
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
    (work / "grandchild.pid").write_text(str(child.pid))
    time.sleep(300)
"""


class Fakes:
    """A PATH with a fake `claude` or `codex` and `git`; its markers live outside the root."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.bin = tmp_path / "bin"
        self.work = tmp_path / "work"
        self.bin.mkdir()
        self.work.mkdir()
        git = shutil.which("git")
        assert git is not None
        (self.bin / "git").symlink_to(git)
        monkeypatch.setenv("PATH", str(self.bin))

    def install(self, *names: str) -> None:
        script = _FAKE.replace("PYTHON", sys.executable).replace("WORK", str(self.work))
        script = script.replace("PLACE", PLACE).replace("SAVE", SAVE)
        script = script.replace("STORE_PUT", STORE_PUT)
        for name in names:
            (self.bin / name).write_text(script)
            (self.bin / name).chmod(stat.S_IRWXU)

    def call(self) -> dict:
        return json.loads((self.work / "call.json").read_text())


@pytest.fixture
def fakes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Fakes:
    return Fakes(tmp_path, monkeypatch)


@pytest.fixture(scope="module")
def studio(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Studio]:
    base = tmp_path_factory.mktemp("chat")
    with running(_repository(base / "shop", _FILES), base / "cache", explored=True) as server:
        yield server


@pytest.fixture
def chat(studio: Studio, fakes: Fakes) -> Iterator[Studio]:
    """The explored server with a fresh agent; `fakes` already put the fake CLI on the PATH."""
    fakes.install("claude")
    studio.agent = Agent(studio.workspace.root)
    yield studio
    studio.agent.close()


@pytest.fixture
def incomplete_chat(tmp_path: Path, fakes: Fakes) -> Iterator[Studio]:
    """A real exit-2 snapshot whose malformed source leaves observation coverage incomplete."""
    fakes.install("claude", "codex")
    files = {**_FILES, "shop/app/broken.py": "def broken(: int\n    return 1\n"}
    root = _repository(tmp_path / "shop", files)
    with running(root, tmp_path / "cache") as server:
        assert explore(server, login(server))["explore"] == "incomplete"
        server.agent.close()
        server.agent = Agent(server.workspace.root)
        yield server
        server.agent.close()


def post(
    server: Studio,
    cookie: str | None,
    body: object,
    *,
    headers: dict[str, str | None] | None = None,
    path: str = "/api/v1/chat",
    method: str = "POST",
) -> tuple[int, dict[str, str], bytes]:
    origin = f"http://127.0.0.1:{server.port}"
    sent: dict[str, str | None] = {
        "Host": f"127.0.0.1:{server.port}",
        "Origin": origin,
        "X-Archkeel-Studio": "1",
        "Content-Type": "application/json",
        "Cookie": cookie,
        **(headers or {}),
    }
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=60)
    connection.request(method, path, body=raw, headers={k: v for k, v in sent.items() if v})
    response = connection.getresponse()
    return response.status, dict(response.getheaders()), response.read()


def ask(
    server: Studio,
    question: str,
    context: str | None = PLACE,
    mode: str | None = None,
) -> tuple[int, dict]:
    body = {"question": question, "context": context}
    if mode is not None:
        body["mode"] = mode
    status, _, raw = post(server, login(server), body)
    payload = json.loads(raw)
    defined = "chat_response" if status == 200 else "chat_error"
    validate(payload, defined)
    return status, payload


def _gone(pid: int, seconds: float = 10) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def test_a_root_that_is_not_a_git_repository_gives_a_clear_error(
    tmp_path: Path, fakes: Fakes
) -> None:
    fakes.install("claude")
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(ChatFailure) as raised:
        Agent(plain).ask(ChatRequest("ok", None), "")
    assert raised.value.error is ChatError.AGENT_FAILED
    assert "git repository" in raised.value.detail
    assert not (fakes.work / "call.json").exists()


def test_the_chat_waits_for_the_snapshot(tmp_path: Path, fakes: Fakes) -> None:
    fakes.install("claude")
    with running(_repository(tmp_path / "shop", _FILES), tmp_path / "cache") as server:
        status, payload = ask(server, "ok")
    assert (status, payload["error"]) == (503, "snapshot_not_ready")


def test_the_cli_option_accepts_only_known_agents() -> None:
    parser = build_parser()
    assert parser.parse_cli_args(["studio"]).chat_agent.value == "claude"
    assert parser.parse_cli_args(["studio", "--agent", "codex"]).chat_agent.value == "codex"
    with pytest.raises(ValueError, match="invalid choice"):
        parser.parse_cli_args(["studio", "--agent", "gpt"])


def _model() -> dict[str, object]:
    def call(scope: str, status: str, *targets: str, expression: str = "x") -> dict[str, object]:
        data = {"source_scope": scope, "status": status, "targets": list(targets)}
        return {"kind": "call", "data": {**data, "expression": expression}}

    return {
        "symbols": [
            {"kind": "function", "evidence_ids": ["E1"], "data": {"qualified_name": "a.f"}},
            {"kind": "class", "evidence_ids": ["E2"], "data": {"qualified_name": "a.C"}},
            {"kind": "function", "evidence_ids": [], "data": {"qualified_name": "a.g"}},
        ],
        "evidence": [
            {"id": "E1", "file": "a.py", "line": 3},
            {"id": "E2", "file": "a.py", "line": 9},
        ],
        "calls": [
            call("a.f", "resolved", "a.g"),
            call("a.f", "resolved", "a.g"),
            call("a.f", "partially_resolved", expression="maybe"),
            call("a.f", "unresolved", expression="dynamic"),
            call("a.h", "resolved", "a.f"),
            call("a.g", "resolved", "a.f"),
            call("a.g", "resolved", "a.f"),
        ],
    }


def test_the_facts_count_distinct_resolved_neighbors_and_every_unproven_call() -> None:
    snapshot = Snapshot(_model())
    answer = snapshot.check(
        json.dumps(
            {"blocks": [{"kind": "claim", "text": "t", "refs": ["a.f", "a.C", "a.g", "a.f"]}]}
        ),
        AgentKind.CLAUDE,
    )
    f, c, g = answer.facts
    assert (f.resolved_callers, f.resolved_callees, f.unknown_calls) == (2, 1, 2)
    assert (c.file, c.line, c.resolved_callers, c.resolved_callees) == ("a.py", 9, 0, 0)
    # A symbol without evidence still counts; its place is unknown.
    assert (g.qualified_name, g.file, g.line) == ("a.g", "", 0)
    assert snapshot.neighborhood("a.f").splitlines()[1:] == [
        "callers: a.g, a.h",
        "callees: a.g",
        "unknown calls (2): maybe, dynamic",
    ]


def test_the_neighborhood_is_capped() -> None:
    model = _model()
    calls = model["calls"]
    assert isinstance(calls, list)
    calls.extend(
        {
            "kind": "call",
            "data": {"source_scope": f"b.c{n}", "status": "resolved", "targets": ["a.f"]},
        }
        for n in range(40)
    )
    callers = Snapshot(model).neighborhood("a.f").splitlines()[1].removeprefix("callers: ")
    names = callers.split(", ")
    assert len(names) == 31
    assert names[:2] == ["a.g", "a.h"]
    assert names[30] == "and 12 more"


@pytest.mark.parametrize(
    "answer",
    [
        '{"blocks": [], "extra": 1}',
        '{"blocks": "x"}',
        '{"blocks": [{"kind": "claim", "text": "t"}]}',
        '{"blocks": [{"kind": "claim", "text": 5, "refs": []}]}',
        '{"blocks": [{"kind": "claim", "text": "t", "refs": [5]}]}',
        '{"blocks": [{"kind": "claim", "text": "' + "x" * 2001 + '", "refs": []}]}',
        '{"blocks": [' + ", ".join(['{"kind": "claim", "text": "t", "refs": []}'] * 11) + "]}",
        '{"blocks": [{"kind": "claim", "text": "t", "refs": ' + json.dumps(["a.f"] * 21) + "}]}",
        "[]",
    ],
)
def test_a_malformed_answer_is_refused(answer: str) -> None:
    with pytest.raises(ChatFailure) as raised:
        Snapshot(_model()).check(answer, AgentKind.CODEX)
    assert raised.value.error is ChatError.INVALID_ANSWER


def test_a_model_without_the_sections_has_no_symbols() -> None:
    snapshot = Snapshot({})
    assert not snapshot.has("a.f")


@pytest.mark.parametrize(
    "ref",
    ["a.", "a.f ", "A.F", "a.\u0066", "\u0430.f", "a.f\u200b", "a.f.extra", "a"],
    ids=["prefix", "space", "case", "escape-of-f", "cyrillic-a", "zero-width", "longer", "package"],
)
def test_only_an_exact_qualified_name_is_a_ref(ref: str) -> None:
    # "a.\u0066" is the text "a.f" after the JSON decode, so it must stay valid.
    answer = json.dumps({"blocks": [{"kind": "claim", "text": "t", "refs": [ref]}]})
    checked = Snapshot(_model()).check(answer, AgentKind.CLAUDE)
    valid = ref == "a.\u0066"
    assert [fact.qualified_name for fact in checked.facts] == (["a.f"] if valid else [])
    assert checked.dropped_refs == (() if valid else (ref,))


def test_the_dropped_refs_are_capped_in_count_and_length() -> None:
    refs = [f"{n}" + "x" * 400 for n in range(20)]
    block = {"kind": "claim", "text": "t", "refs": refs}
    answer = json.dumps({"blocks": [block] * 10})
    checked = Snapshot(_model()).check(answer, AgentKind.CLAUDE)
    assert 0 < len(checked.dropped_refs) <= 50
    assert all(len(ref) <= 300 for ref in checked.dropped_refs)
    validate(
        {
            "api_version": API_VERSION,
            "agent": "claude",
            "snapshot_completeness": "complete",
            "blocks": [],
            "facts": [],
            "dropped_refs": list(checked.dropped_refs),
            "story": None,
            "applied": False,
        },
        "chat_response",
    )
