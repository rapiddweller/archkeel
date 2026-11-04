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
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from test_explore import _repository, _tree_digest
from test_studio import _start, _stop, explore, login, validate

from archkeel.cli import build_parser
from archkeel.studio.agent import Agent
from archkeel.studio.answer import Snapshot
from archkeel.studio.api import AgentKind, ChatError, ChatFailure, ChatRequest
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
    server = _start(_repository(base / "shop", _FILES), base / "cache")
    assert explore(server, login(server))["explore"] == "done"
    yield server
    _stop(server)


@pytest.fixture
def chat(studio: Studio, fakes: Fakes) -> Iterator[Studio]:
    """The explored server with a fresh agent; `fakes` already put the fake CLI on the PATH."""
    fakes.install("claude")
    studio.agent = Agent(studio.workspace.root)
    yield studio
    studio.agent.close()


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


def ask(server: Studio, question: str, context: str | None = PLACE) -> tuple[int, dict]:
    status, _, raw = post(server, login(server), {"question": question, "context": context})
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


def test_an_answer_is_checked_and_its_facts_come_from_the_snapshot(
    chat: Studio, fakes: Fakes
) -> None:
    before = _tree_digest(chat.workspace.root)

    status, answer = ask(chat, "ok")

    assert status == 200, answer
    assert answer["agent"] == "claude"
    assert answer["applied"] is False
    claim, proposal = answer["blocks"]
    assert (claim["kind"], claim["refs"], claim["label"]) == ("claim", [PLACE], None)
    assert (proposal["kind"], proposal["refs"]) == ("proposal", [SAVE])
    assert proposal["label"] == "PROPOSED - NOT APPLIED"
    assert answer["dropped_refs"] == ["shop.nothing.here"]
    facts = {fact["qualified_name"]: fact for fact in answer["facts"]}
    assert list(facts) == [PLACE, SAVE]
    assert facts[PLACE] == {
        "qualified_name": PLACE,
        "file": "shop/app/orders.py",
        "line": 4,
        "resolved_callers": 1,
        "resolved_callees": 1,
        "unknown_calls": 1,
    }
    assert (facts[SAVE]["resolved_callers"], facts[SAVE]["unknown_calls"]) == (1, 1)
    assert _tree_digest(chat.workspace.root) == before
    call = fakes.call()
    assert call["cwd"] == str(chat.workspace.root)
    assert call["argv"][0] == "-p"
    assert call["argv"][call["argv"].index("--tools") + 1] == "Read,Grep,Glob"
    assert "dontAsk" in call["argv"]
    assert "Bash" not in " ".join(call["argv"])
    assert "Question: ok" in call["prompt"]
    # Direct neighborhood of the selected node, measured by ArchKeel.
    assert f"Selected node: {PLACE}" in call["prompt"]
    assert "callers: shop.cli.__main__" in call["prompt"]
    assert f"callees: {SAVE}" in call["prompt"]
    assert "unknown calls (1): callback" in call["prompt"]


def test_one_fenced_block_is_accepted(chat: Studio) -> None:
    assert ask(chat, "fenced")[0] == 200


def test_the_question_works_without_a_selected_node(chat: Studio, fakes: Fakes) -> None:
    assert ask(chat, "ok", None)[0] == 200
    assert "Selected node: none" in fakes.call()["prompt"]


@pytest.mark.parametrize(
    "question",
    ["badjson", "badkind", "forged", "nested"],
    ids=["not-json", "wrong-kind", "forged-field", "nested-json"],
)
def test_a_broken_or_forged_answer_is_refused(chat: Studio, question: str) -> None:
    status, payload = ask(chat, question)
    assert (status, payload["error"]) == (502, "invalid_answer")


def test_an_answer_that_is_too_large_stops_the_agent(chat: Studio) -> None:
    status, payload = ask(chat, "big")
    assert (status, payload["error"]) == (502, "output_too_large")


def test_an_agent_that_fails_gives_its_error(chat: Studio) -> None:
    status, payload = ask(chat, "fails")
    assert (status, payload["error"]) == (502, "agent_failed")
    # The log of the agent can hold secrets: Studio shows a fixed hint, never the log.
    assert "boom" not in payload["detail"] and "secret" not in payload["detail"]
    assert "signed in" in payload["detail"]


def test_a_noisy_log_does_not_count_against_the_answer(chat: Studio) -> None:
    assert ask(chat, "noisy")[0] == 200


@pytest.mark.parametrize(
    ("question", "dirty_before"), [("writes", False), ("edits", False), ("edits", True)]
)
def test_a_run_that_changes_the_repository_is_discarded(
    chat: Studio, question: str, dirty_before: bool
) -> None:
    root = chat.workspace.root
    orders = root / "shop/app/orders.py"
    if dirty_before:  # git reports the file before and after: only its size and time differ
        orders.write_text(orders.read_text() + "# dirty\n")
    try:
        status, payload = ask(chat, question)
    finally:
        (root / "agent-wrote.txt").unlink(missing_ok=True)
        orders.write_text(orders.read_text().replace("# edited\n", "").replace("# dirty\n", ""))
    assert (status, payload["error"]) == (502, "repository_changed")
    assert "may stay on disk" in payload["detail"]
    assert "blocks" not in payload
    # Negative control: the same agent with no write gives an answer.
    assert ask(chat, "ok")[0] == 200


def test_a_timeout_kills_the_whole_process_group(
    chat: Studio, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("archkeel.studio.agent._GRACE_SECONDS", 0.2)
    chat.agent = Agent(chat.workspace.root, timeout=1)

    status, payload = ask(chat, "hang")

    assert (status, payload["error"]) == (504, "agent_timeout")
    # The fake and its child ignore SIGINT: only the kill of the group ends them.
    assert _gone(int((fakes.work / "grandchild.pid").read_text()))


def test_stopping_the_agent_kills_a_running_child(
    chat: Studio, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("archkeel.studio.agent._GRACE_SECONDS", 0.2)
    outcome: list[ChatFailure] = []

    def run() -> None:
        try:
            chat.agent.ask(ChatRequest("hang", None), "")
        except ChatFailure as failure:
            outcome.append(failure)

    thread = threading.Thread(target=run)
    thread.start()
    deadline = time.monotonic() + 30
    while not (fakes.work / "grandchild.pid").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    chat.agent.close()
    thread.join(30)

    assert not thread.is_alive()
    assert outcome and outcome[0].error is ChatError.AGENT_FAILED
    assert _gone(int((fakes.work / "grandchild.pid").read_text()))


def test_a_second_question_while_one_runs_gets_409(chat: Studio, fakes: Fakes) -> None:
    results: list[tuple[int, dict]] = []
    first = threading.Thread(target=lambda: results.append(ask(chat, "wait")))
    first.start()
    deadline = time.monotonic() + 30
    while not (fakes.work / "started").exists() and time.monotonic() < deadline:
        time.sleep(0.05)

    status, payload = ask(chat, "ok")
    (fakes.work / "release").touch()
    first.join(30)

    assert (status, payload["error"]) == (409, "busy")
    assert results[0][0] == 200


def test_no_installed_agent_gives_a_clear_error(chat: Studio, fakes: Fakes) -> None:
    (fakes.bin / "claude").unlink()
    status, payload = ask(chat, "ok")
    assert (status, payload["error"]) == (503, "agent_not_installed")
    assert "claude" in payload["detail"]


def test_claude_is_the_default_and_codex_is_an_explicit_opt_in(chat: Studio, fakes: Fakes) -> None:
    fakes.install("codex")
    root = chat.workspace.root
    assert ask(chat, "ok")[1]["agent"] == "claude"
    claude_prompt = fakes.call()["prompt"]

    args = build_parser().parse_cli_args(["studio", "--agent", "codex"])
    chat.agent = Agent(root, AgentKind(args.chat_agent.value))
    status, answer = ask(chat, "ok")

    assert (status, answer["agent"]) == (200, "codex")
    call = fakes.call()
    assert call["argv"][0] == "exec"
    assert call["argv"][call["argv"].index("--sandbox") + 1] == "read-only"
    # Codex runs shell commands: its prompt must not claim that it cannot.
    assert "cannot run commands" in claude_prompt
    assert "cannot run commands" not in call["prompt"]
    assert "read-only commands" in call["prompt"]
    # An explicit choice has no fallback: with no codex, claude does not answer instead.
    (fakes.bin / "codex").unlink()
    status, payload = ask(chat, "ok")
    assert (status, payload["error"]) == (503, "agent_not_installed")
    assert "codex" in payload["detail"]


def test_the_agent_gets_no_key_no_parent_session_and_no_secret_in_the_prompt(
    chat: Studio, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-sentinel-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-sentinel-openai")
    monkeypatch.setenv("CLAUDE_CODE_SIMPLE", "1")
    monkeypatch.setenv("CLAUDECODE", "1")
    monkeypatch.setenv("DEPLOY_PASSWORD", "sentinel-password")

    assert ask(chat, "ok")[0] == 200

    call = fakes.call()
    for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "CLAUDE_CODE_SIMPLE", "CLAUDECODE"):
        assert name not in call["env"], name
    assert "PATH" in call["env"]
    assert "sentinel" not in call["prompt"] and "sentinel" not in " ".join(call["argv"])


def test_claude_keeps_the_sign_in_variables_of_the_owner(
    chat: Studio, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "own-sign-in")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    monkeypatch.setenv("CLAUDE_CODE_SIMPLE", "1")
    assert ask(chat, "ok")[0] == 200
    env = fakes.call()["env"]
    assert (env["CLAUDE_CODE_OAUTH_TOKEN"], env["CLAUDE_CODE_USE_BEDROCK"]) == ("own-sign-in", "1")
    assert "CLAUDE_CODE_SIMPLE" not in env


def test_codex_gets_only_an_allow_list_of_the_environment(
    chat: Studio, fakes: Fakes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Codex runs shell commands of the model: each variable could be read or sent.
    fakes.install("codex")
    chat.agent = Agent(chat.workspace.root, AgentKind.CODEX)
    secrets = {
        "GITHUB_TOKEN": "ghp-sentinel",
        "SSH_AUTH_SOCK": "sentinel-agent-socket",
        "AWS_SECRET_ACCESS_KEY": "sentinel-aws",
        "ANTHROPIC_API_KEY": "sk-sentinel",
        "DEPLOY_PASSWORD": "sentinel-password",
    }
    for name, value in secrets.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("LC_ALL", "C")
    monkeypatch.setenv("CODEX_HOME", str(fakes.work / "codex-home"))

    assert ask(chat, "ok")[0] == 200

    env = fakes.call()["env"]
    assert not set(secrets) & set(env)
    assert not any("sentinel" in value for value in env.values())
    assert {"PATH", "HOME", "LC_ALL", "CODEX_HOME"} <= set(env)


@pytest.mark.parametrize(
    ("headers", "status"),
    [
        ({"Cookie": None}, 403),
        ({"Cookie": "archkeel_studio_1=wrong"}, 403),
        ({"Origin": "http://evil.test"}, 403),
        ({"Origin": "null"}, 403),
        ({"Origin": None}, 403),
        ({"X-Archkeel-Studio": None}, 403),
        ({"Host": "evil.test"}, 403),
        ({"Content-Type": "text/plain"}, 415),
        ({"Content-Type": None}, 415),
        ({"Content-Length": "999999"}, 413),
    ],
)
def test_a_request_that_fails_a_check_is_refused_before_the_agent_runs(
    chat: Studio, fakes: Fakes, headers: dict[str, str | None], status: int
) -> None:
    cookie = None if headers.get("Cookie", "x") is None else login(chat)
    got, _, _ = post(chat, cookie, {"question": "ok"}, headers=headers)
    assert got == status
    assert not (fakes.work / "call.json").exists()


def test_a_request_without_a_length_gets_411(chat: Studio) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", chat.port, timeout=10)
    connection.request(
        "POST",
        "/api/v1/chat",
        body=iter([b"{}"]),
        encode_chunked=True,
        headers={
            "Host": f"127.0.0.1:{chat.port}",
            "Origin": f"http://127.0.0.1:{chat.port}",
            "X-Archkeel-Studio": "1",
            "Content-Type": "application/json",
            "Cookie": login(chat),
            "Transfer-Encoding": "chunked",
        },
    )
    assert connection.getresponse().status == 411


def test_a_length_that_is_no_ascii_number_gets_411(chat: Studio) -> None:
    status, _, raw = post(
        chat, login(chat), {"question": "ok"}, headers={"Content-Length": "\u00b2"}
    )
    assert status == 411
    validate(json.loads(raw), "chat_error")


def test_the_explorer_pages_are_sandboxed_to_an_opaque_origin(chat: Studio) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", chat.port, timeout=10)
    connection.request(
        "GET",
        "/files/architecture.report.html",
        headers={"Host": f"127.0.0.1:{chat.port}", "Cookie": login(chat)},
    )
    response = connection.getresponse()
    response.read()
    csp = response.getheader("Content-Security-Policy", "")
    assert response.status == 200
    assert "sandbox allow-scripts;" in csp
    assert "allow-same-origin" not in csp
    assert "form-action 'none'" in csp


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


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b"[" * 5000,
        b"[]",
        {},
        {"question": ""},
        {"question": 5},
        {"question": "x" * 2001},
        {"question": "ok", "extra": 1},
        {"question": "ok", "context": 5},
        {"question": "ok", "context": "shop.nothing.here"},
        {"question": "ok", "context": "shop.app.orders"},
    ],
)
def test_a_bad_body_gets_400(chat: Studio, fakes: Fakes, body: object) -> None:
    status, _, raw = post(chat, login(chat), body)
    assert status == 400
    validate(json.loads(raw), "chat_error")
    assert not (fakes.work / "call.json").exists()


def test_the_chat_waits_for_the_snapshot(tmp_path: Path, fakes: Fakes) -> None:
    fakes.install("claude")
    server = _start(_repository(tmp_path / "shop", _FILES), tmp_path / "cache")
    try:
        status, payload = ask(server, "ok")
    finally:
        _stop(server)
    assert (status, payload["error"]) == (503, "snapshot_not_ready")


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_the_chat_route_takes_only_post(chat: Studio, method: str) -> None:
    status, headers, _ = post(chat, login(chat), b"", method=method)
    assert (status, headers["Allow"]) == (405, "POST")


@pytest.mark.parametrize("path", ["/api/v1/state", "/api/v1/nothing", "/files/architecture.json"])
def test_another_post_and_the_other_methods_stay_405(chat: Studio, path: str) -> None:
    cookie = login(chat)
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        status, headers, _ = post(chat, cookie, b"{}", path=path, method=method)
        assert (status, headers["Allow"]) == (405, "GET"), (method, path)


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
            "api_version": "1.1.0",
            "agent": "claude",
            "blocks": [],
            "facts": [],
            "dropped_refs": list(checked.dropped_refs),
            "applied": False,
        },
        "chat_response",
    )
