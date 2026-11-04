# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290, AD-292: the routes and typed bodies of the Studio API (`schema/studio-api-1.1`)."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

API_VERSION: Final = "1.1.0"
QUESTION_LIMIT: Final = 2000
CONTEXT_LIMIT: Final = 300


class Route(StrEnum):
    """The first path segment of a Studio URL; the empty segment is the shell."""

    SHELL = ""
    API = "api"
    UI = "ui"
    FILES = "files"


class ApiPath(StrEnum):
    """The path below `/api/`: the state is read-only; the chat takes a question by POST."""

    STATE = "v1/state"
    CHAT = "v1/chat"


class MediaType(StrEnum):
    """The one body type that the chat route accepts."""

    JSON = "application/json"


class AgentKind(StrEnum):
    """The coding agents that can answer, in the default order of trial."""

    CLAUDE = "claude"
    CODEX = "codex"


class ChatBlockKind(StrEnum):
    """What an agent block is: a statement about the code, or a change it suggests."""

    CLAIM = "claim"
    PROPOSAL = "proposal"


class CallStatus(StrEnum):
    """The call status of the snapshot that counts as proof; each other value is unknown."""

    RESOLVED = "resolved"


class ChatError(StrEnum):
    """Why the chat route gave no answer; the server maps each one to an HTTP status."""

    INVALID_REQUEST = "invalid_request"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    LENGTH_REQUIRED = "length_required"
    BODY_TOO_LARGE = "body_too_large"
    SNAPSHOT_NOT_READY = "snapshot_not_ready"
    BUSY = "busy"
    AGENT_NOT_INSTALLED = "agent_not_installed"
    AGENT_FAILED = "agent_failed"
    AGENT_TIMEOUT = "agent_timeout"
    OUTPUT_TOO_LARGE = "output_too_large"
    REPOSITORY_CHANGED = "repository_changed"
    INVALID_ANSWER = "invalid_answer"


class UiAsset(StrEnum):
    """The shell and the files it loads; no other file of the UI folder is served."""

    INDEX = "index.html"
    SCRIPT = "studio.js"
    TOKENS = "tokens.css"
    STYLE = "studio.css"


class ContractState(StrEnum):
    """What `archkeel.toml` at the root gives: no file, a file that does not load, or a file."""

    NOT_CONFIGURED = "not_configured"
    INVALID = "invalid"
    CONFIGURED = "configured"


class ExploreState(StrEnum):
    """The explore run that makes the snapshot in the cache folder.

    IDLE is the state between a new workspace and its start: `run_studio` starts the run before
    it serves, so a browser does not see IDLE, but a workspace does report it.
    """

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class StudioState:
    """`GET /api/v1/state`; `notes` explain a failed run."""

    root_name: str
    contract: ContractState
    explore: ExploreState = ExploreState.IDLE
    seconds: int = 0
    exit_code: int | None = None
    notes: tuple[str, ...] = ()


def state_json(state: StudioState) -> bytes:
    return json.dumps({"api_version": API_VERSION, **asdict(state)}, sort_keys=True).encode()


class ChatFailure(Exception):
    """A chat request that gets no answer."""

    def __init__(self, error: ChatError, detail: str) -> None:
        super().__init__(detail)
        self.error = error
        self.detail = detail


@dataclass(frozen=True)
class ChatRequest:
    """`POST /api/v1/chat`; `context` is the qualified name of the selected node."""

    question: str
    context: str | None = None


@dataclass(frozen=True)
class Fact:
    """OBSERVED: what Studio counts in the snapshot for one symbol; never agent text."""

    qualified_name: str
    file: str
    line: int
    resolved_callers: int
    resolved_callees: int
    unknown_calls: int


@dataclass(frozen=True)
class ChatBlock:
    """One block of agent text. `label` is set by Studio, never by the agent."""

    kind: ChatBlockKind
    text: str
    refs: tuple[str, ...]
    label: str | None = None


@dataclass(frozen=True)
class ChatAnswer:
    """`facts` hold one record for each valid ref; `dropped_refs` the refs the snapshot lacks."""

    agent: AgentKind
    blocks: tuple[ChatBlock, ...]
    facts: tuple[Fact, ...]
    dropped_refs: tuple[str, ...]


def parse_chat_request(raw: bytes) -> ChatRequest:
    """The request body, or a 400 that names the first break."""
    try:
        body = json.loads(raw)
    except ValueError as error:
        raise ChatFailure(ChatError.INVALID_REQUEST, f"The body is not JSON: {error}") from error
    if not isinstance(body, dict) or not body.keys() <= {"question", "context"}:
        raise ChatFailure(
            ChatError.INVALID_REQUEST, 'The body must be {"question": text, "context": name}.'
        )
    question, context = body.get("question"), body.get("context")
    if not isinstance(question, str) or not 0 < len(question) <= QUESTION_LIMIT:
        raise ChatFailure(
            ChatError.INVALID_REQUEST, f"question must be text of 1 to {QUESTION_LIMIT} characters."
        )
    if context is not None and (not isinstance(context, str) or len(context) > CONTEXT_LIMIT):
        raise ChatFailure(ChatError.INVALID_REQUEST, "context must be a qualified name or null.")
    return ChatRequest(question, context)


def chat_json(answer: ChatAnswer) -> bytes:
    return json.dumps({"api_version": API_VERSION, "applied": False, **asdict(answer)}).encode()


def failure_json(failure: ChatFailure) -> bytes:
    body = {"api_version": API_VERSION, "error": failure.error, "detail": failure.detail}
    return json.dumps(body).encode()
