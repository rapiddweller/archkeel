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

from .api import AgentKind, ChatError, ChatFailure, ChatRequest

_TIMEOUT_SECONDS: Final = 180.0
_OUTPUT_LIMIT: Final = 128 * 1024
_GRACE_SECONDS = 3.0
_TICK_SECONDS = 0.05
_GIT_SECONDS = 60
_ERROR_TAIL = 500
_PROMPT = Template(
    """\
You answer one question about the code in the current folder.
You can read files and search them. You cannot run commands. You cannot change files.

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

Question: $question

Selected node: $node
Facts that ArchKeel measured for the selected node:
$facts
"""
)
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
# The child uses the sign-in of the owner. It gets no API key, and no variable of a parent agent
# session: an inherited CLAUDE_CODE_SIMPLE makes `claude -p` accept API-key sign-in only.
_NOT_FOR_THE_CHILD = re.compile(
    r"CLAUDECODE|CLAUDE_CODE_.*|CLAUDE_AGENT_SDK_.*|CODEX_(THREAD|SESSION|TOOL|SANDBOX|CI).*"
    r"|ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|OPENAI_API_KEY|CODEX_API_KEY"
)


@dataclass(frozen=True)
class Reply:
    kind: AgentKind
    text: str


def build_prompt(request: ChatRequest, neighborhood: str) -> str:
    return _PROMPT.substitute(
        question=request.question, node=request.context or "none", facts=neighborhood or "none"
    )


def _tree_state(root: Path) -> bytes:
    """What git reports for the root, every untracked file listed; fail closed."""
    command = ["git", "--no-optional-locks", "-C", str(root)]
    command += ["status", "--porcelain", "-z", "--untracked-files=all"]
    try:
        done = subprocess.run(
            command, capture_output=True, stdin=subprocess.DEVNULL, timeout=_GIT_SECONDS
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ChatFailure(ChatError.AGENT_FAILED, f"git status did not run: {error}") from error
    if done.returncode != 0:
        raise ChatFailure(ChatError.AGENT_FAILED, "git status failed: Studio cannot check the run.")
    return done.stdout


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
        prefer: AgentKind | None = None,
        *,
        timeout: float = _TIMEOUT_SECONDS,
        limit: int = _OUTPUT_LIMIT,
    ) -> None:
        self.root = root
        self._timeout = timeout
        self._limit = limit
        self._order = (*([prefer] if prefer else []), *(k for k in AgentKind if k is not prefer))
        self._run = threading.Lock()
        self._guard = threading.Lock()
        self._child: subprocess.Popen[bytes] | None = None
        self._closed = False

    @property
    def busy(self) -> bool:
        return self._run.locked()

    def ask(self, prompt: str) -> Reply:
        """Run one agent. Raise a `ChatFailure` for each break, also when the run changed a file."""
        if not self._run.acquire(blocking=False):
            raise ChatFailure(ChatError.BUSY, "Another question runs. Wait until it ends.")
        try:
            kind, program = self._find()
            before = _tree_state(self.root)
            failure: ChatFailure | None = None
            text = ""
            try:
                text = self._execute(kind, program, prompt)
            except ChatFailure as error:
                failure = error
            if _tree_state(self.root) != before:
                raise ChatFailure(
                    ChatError.REPOSITORY_CHANGED,
                    "The run changed a file in the repository. Studio discarded the answer.",
                ) from failure
            if failure is not None:
                raise failure
            return Reply(kind, text)
        finally:
            self._run.release()

    def close(self) -> None:
        """Stop the running child, if any, and refuse each later run."""
        with self._guard:
            self._closed = True
            child = self._child
        if child is not None:
            _end(child)

    def _find(self) -> tuple[AgentKind, str]:
        for kind in self._order:
            if (program := shutil.which(kind.value)) is not None:
                return kind, program
        raise ChatFailure(
            ChatError.AGENT_NOT_INSTALLED,
            "Studio found neither claude (Claude Code) nor codex (Codex) on the PATH. "
            "Install one of them and sign in.",
        )

    def _execute(self, kind: AgentKind, program: str, prompt: str) -> str:
        env = {
            name: value
            for name, value in os.environ.items()
            if not _NOT_FOR_THE_CHILD.fullmatch(name)
        }
        # Files, not pipes: a child that never reads its input cannot block the server.
        with (
            tempfile.TemporaryFile() as stdin,
            tempfile.TemporaryFile() as out,
            tempfile.TemporaryFile() as err,
        ):
            stdin.write(prompt.encode())
            stdin.seek(0)
            with self._guard:
                if self._closed:
                    raise ChatFailure(ChatError.AGENT_FAILED, "Studio is stopping.")
                try:
                    self._child = subprocess.Popen(
                        [program, *_COMMANDS[kind]],
                        cwd=self.root,
                        env=env,
                        stdin=stdin,
                        stdout=out,
                        stderr=err,
                        start_new_session=True,
                    )
                except OSError as error:
                    raise ChatFailure(
                        ChatError.AGENT_FAILED, f"{program} did not start: {error}"
                    ) from error
                child = self._child
            try:
                self._wait(child, out, err)
            finally:
                _end(child)
                with self._guard:
                    self._child = None
            if max(_size(out), _size(err)) > self._limit:
                raise ChatFailure(
                    ChatError.OUTPUT_TOO_LARGE, f"The agent wrote more than {self._limit} bytes."
                )
            if child.returncode != 0:
                err.seek(max(0, _size(err) - _ERROR_TAIL))
                tail = err.read().decode("utf-8", "replace").strip()
                raise ChatFailure(
                    ChatError.AGENT_FAILED, f"{kind.value} exited with {child.returncode}: {tail}"
                )
            out.seek(0)
            return out.read().decode("utf-8", "replace")

    def _wait(self, child: "subprocess.Popen[bytes]", *streams: IO[bytes]) -> None:
        deadline = time.monotonic() + self._timeout
        while child.poll() is None:
            if time.monotonic() > deadline:
                raise ChatFailure(
                    ChatError.AGENT_TIMEOUT, f"The agent did not answer in {self._timeout:g} s."
                )
            if max(_size(stream) for stream in streams) > self._limit:
                return
            time.sleep(_TICK_SECONDS)
