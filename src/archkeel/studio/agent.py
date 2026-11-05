# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-292: the port to the coding agent of the owner: one read-only child process at a time."""

import contextlib
import os
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import IO, Final

from .api import AgentKind, ChatError, ChatFailure, ChatRequest, SnapshotCompleteness

_TIMEOUT_SECONDS: Final = 180.0
_OUTPUT_LIMIT: Final = 128 * 1024
_GRACE_SECONDS = 3.0
_TICK_SECONDS = 0.05
_GIT_SECONDS = 60
_PROMPT = Template(
    """\
You answer one question about the code in the current folder.
$tools

Reply with one JSON object and no other text. Use this shape:
{"blocks": [{"kind": "claim", "text": "...", "refs": ["module.qualified_name"]}]}

Rules:
1. Use kind "claim" for a statement about the code. Use kind "proposal" for a change that you
   suggest. Nothing applies a proposal.
2. Put in refs the qualified name of each function or class that a block is about. Write the
   module path and the name, for example shop.app.orders.place. Studio drops each name that its
   snapshot does not hold.
3. Write at most 10 blocks, at most 2000 characters in each text and at most 20 refs in each block.
4. Say what you could not check. Do not guess.

Snapshot completeness: $completeness

Question: $question

Selected node: $node
Facts that ArchKeel measured for the selected node:
$facts

An exact ref means only that the name is listed in this snapshot; it does not verify the meaning
of your text. Never infer that a missing ref is absent from the code. If completeness is incomplete,
this is an incomplete snapshot: it may omit files, symbols, or calls. Missing names and calls are
UNKNOWN, not evidence of absence. Do not make negative or exhaustive claims from these lists.
"""
)
# What each agent can do, in the words of its prompt. Codex runs shell commands of the model in
# its read-only sandbox and can read the whole disk: its prompt must not say "no commands".
_TOOLS: Final = {
    AgentKind.CLAUDE: (
        "You can read files and search them. You cannot run commands. You cannot change files."
    ),
    AgentKind.CODEX: (
        "You can read files and run read-only commands. Do not change any file. "
        "Do not read outside the current folder."
    ),
}
# Read-only by the tools of the agent: no shell and no write tool for claude, a read-only
# sandbox for codex. The prompt goes on stdin and the answer comes on stdout.
_COMMANDS: Final = {
    AgentKind.CLAUDE: (
        "-p",
        "--tools",
        "Read,Grep,Glob",
        "--permission-mode",
        "dontAsk",
        "--no-session-persistence",
        "--strict-mcp-config",
        "--setting-sources",
        "user",
    ),
    AgentKind.CODEX: (
        "exec",
        "--sandbox",
        "read-only",
        "--ephemeral",
        "--color",
        "never",
        "--ignore-user-config",
        "-",
    ),
}
# The child uses the sign-in of the owner. Claude has no shell, so it gets the environment of the
# server without the variables of a parent agent session (an inherited CLAUDE_CODE_SIMPLE makes
# `claude -p` accept API-key sign-in only) and without the four API key names. It keeps
# CLAUDE_CODE_OAUTH_TOKEN and the Bedrock and Vertex selectors: an owner may sign in with them.
_CLAUDE_WITHOUT = re.compile(
    r"CLAUDECODE|CLAUDE_CODE_(?!OAUTH_TOKEN$|USE_|SKIP_).*|CLAUDE_AGENT_SDK_.*"
    r"|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|OPENAI_API_KEY|CODEX_API_KEY"
)
# Codex runs shell commands of the model, which could read or send each variable. It gets only
# these: the basics, the folder of its own sign-in and the proxy and certificate settings.
_CODEX_WITH = re.compile(
    r"PATH|HOME|USER|LOGNAME|LANG|LC_.*|TERM|TMPDIR|XDG_.*|CODEX_HOME"
    r"|SSL_CERT_FILE|SSL_CERT_DIR|(?i:https?_proxy|all_proxy|no_proxy)"
)
_SIGN_IN_HINT = "Check that the agent is installed and signed in: run it once in a terminal."


@dataclass(frozen=True)
class Reply:
    kind: AgentKind
    text: str


def _prompt(
    kind: AgentKind,
    request: ChatRequest,
    neighborhood: str,
    completeness: SnapshotCompleteness,
) -> str:
    return _PROMPT.substitute(
        tools=_TOOLS[kind],
        question=request.question,
        node=request.context or "none",
        facts=neighborhood or "none",
        completeness=completeness.value,
    )


def _child_env(kind: AgentKind) -> dict[str, str]:
    if kind is AgentKind.CODEX:
        return {name: value for name, value in os.environ.items() if _CODEX_WITH.fullmatch(name)}
    return {
        name: value for name, value in os.environ.items() if not _CLAUDE_WITHOUT.fullmatch(name)
    }


def _tree_state(root: Path) -> tuple[bytes, tuple[tuple[int, int] | None, ...]]:
    """What git reports for the root, and size and mtime of each file listed; fail closed."""
    command = ["git", "--no-optional-locks", "-C", str(root), "status", "--porcelain", "-z"]
    command += ["--untracked-files=all", "--no-renames"]
    try:
        done = subprocess.run(
            command, capture_output=True, stdin=subprocess.DEVNULL, timeout=_GIT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ChatFailure(ChatError.AGENT_FAILED, f"git status did not run: {error}") from error
    if done.returncode != 0:
        raise ChatFailure(
            ChatError.AGENT_FAILED,
            "Studio cannot check the run: git status failed. The root must be a git repository.",
        )
    places: list[tuple[int, int] | None] = []
    for entry in filter(None, done.stdout.split(b"\0")):
        try:
            seen = (root / os.fsdecode(entry[3:])).lstat()
            places.append((seen.st_size, seen.st_mtime_ns))
        except OSError:
            places.append(None)
    return done.stdout, tuple(places)


def _end(child: "subprocess.Popen[bytes]") -> None:
    """Interrupt the process group of the child, kill it after the grace time and reap the child."""
    try:
        os.killpg(child.pid, signal.SIGINT)
    except ProcessLookupError:
        pass
    except AttributeError:  # Windows has no process groups: only the child ends
        child.terminate()
    with contextlib.suppress(subprocess.TimeoutExpired):
        child.wait(_GRACE_SECONDS)
    # The group can hold grandchildren after the child has gone.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except AttributeError:
        child.kill()
    child.wait()


def _size(stream: IO[bytes]) -> int:
    return os.fstat(stream.fileno()).st_size


class Agent:
    """Runs `claude -p` or `codex exec` in the root. The repository must stay unchanged."""

    def __init__(
        self,
        root: Path,
        kind: AgentKind = AgentKind.CLAUDE,
        *,
        timeout: float = _TIMEOUT_SECONDS,
        limit: int = _OUTPUT_LIMIT,
    ) -> None:
        self.root = root
        self._timeout = timeout
        self._limit = limit
        self.kind = kind
        self._run = threading.Lock()
        self._guard = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._closed = False

    @property
    def busy(self) -> bool:
        return self._run.locked()

    def ask(
        self,
        request: ChatRequest,
        neighborhood: str,
        completeness: SnapshotCompleteness = SnapshotCompleteness.COMPLETE,
    ) -> Reply:
        """Run the agent. Raise a `ChatFailure` for each break, also when the run changed a file."""
        if not self._run.acquire(blocking=False):
            raise ChatFailure(ChatError.BUSY, "Another question runs. Wait until it ends.")
        try:
            program = self._find()
            before = _tree_state(self.root)
            failure: ChatFailure | None = None
            text = ""
            try:
                text = self._execute(
                    program, _prompt(self.kind, request, neighborhood, completeness)
                )
            except ChatFailure as error:
                failure = error
            if _tree_state(self.root) != before:
                raise ChatFailure(
                    ChatError.REPOSITORY_CHANGED,
                    "The run changed a file in the repository. Studio discarded the answer. "
                    "The edit may stay on disk: review it with git status.",
                ) from failure
            if failure is not None:
                raise failure
            return Reply(self.kind, text)
        finally:
            self._run.release()

    def close(self) -> None:
        """Stop the running child, if any, and refuse each later run."""
        with self._guard:
            self._closed = True
            child = self._child
        if child is not None:
            _end(child)

    def _find(self) -> str:
        if (program := shutil.which(self.kind.value)) is None:
            raise ChatFailure(
                ChatError.AGENT_NOT_INSTALLED,
                f"Studio found no {self.kind.value} on the PATH. Install it and sign in, "
                "or start Studio with --agent for the other agent.",
            )
        return program

    def _execute(self, program: str, prompt: str) -> str:
        env = _child_env(self.kind)
        # Files, not pipes: a child that never reads its input cannot block the server.
        with tempfile.TemporaryFile() as stdin, tempfile.TemporaryFile() as out:
            stdin.write(prompt.encode())
            stdin.seek(0)
            with self._guard:
                if self._closed:
                    raise ChatFailure(ChatError.AGENT_FAILED, "Studio is stopping.")
                try:
                    self._child = subprocess.Popen(
                        [program, *_COMMANDS[self.kind]],
                        cwd=self.root,
                        env=env,
                        stdin=stdin,
                        stdout=out,
                        # Never kept: a log can hold secrets, and Studio shows no log.
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                    )
                except OSError as error:
                    raise ChatFailure(
                        ChatError.AGENT_FAILED, f"{program} did not start: {error}"
                    ) from error
                child = self._child
            try:
                self._wait(child, out)
            finally:
                _end(child)
                with self._guard:
                    self._child = None
            if _size(out) > self._limit:
                raise ChatFailure(
                    ChatError.OUTPUT_TOO_LARGE, f"The agent wrote more than {self._limit} bytes."
                )
            if child.returncode != 0:
                raise ChatFailure(
                    ChatError.AGENT_FAILED,
                    f"{self.kind.value} exited with {child.returncode}. {_SIGN_IN_HINT}",
                )
            out.seek(0)
            return out.read().decode("utf-8", "replace")

    def _wait(self, child: "subprocess.Popen[bytes]", stdout: IO[bytes]) -> None:
        deadline = time.monotonic() + self._timeout
        while child.poll() is None:
            if time.monotonic() > deadline:
                raise ChatFailure(
                    ChatError.AGENT_TIMEOUT, f"The agent did not answer in {self._timeout:g} s."
                )
            if _size(stdout) > self._limit:
                return
            time.sleep(_TICK_SECONDS)
