# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290, AD-292: the routes and typed bodies of the Studio API (`schema/studio-api-1.1`)."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final, NamedTuple, TypeAlias, TypeVar

API_VERSION: Final = "1.1.0"
QUESTION_LIMIT: Final = 2000
CONTEXT_LIMIT: Final = 300

# The JSON shape of the decoded explore snapshot; the composition root injects the decoder.
Json: TypeAlias = str | int | float | bool | None | Sequence["Json"] | Mapping[str, "Json"]
# Decode the bytes of `architecture.json` into its canonical model, with the strings expanded.
Decode: TypeAlias = Callable[[bytes], Mapping[str, Json]]
# Given the module names, give (label, responsibility, owned modules) for each component of the
# contract at the root, in contract order; no contract gives nothing.
Declare: TypeAlias = Callable[[Sequence[str]], Sequence[tuple[str, str, Sequence[str]]]]

_Member = TypeVar("_Member", bound=StrEnum)


def member(kind: type[_Member], value: Json) -> _Member | None:
    """The member for a value, or None; `in` on an enum needs Python 3.12."""
    if not isinstance(value, str):
        return None
    try:
        return kind(value)
    except ValueError:
        return None


class Route(StrEnum):
    """The first path segment of a Studio URL; the empty segment is the shell."""

    SHELL = ""
    API = "api"
    UI = "ui"
    FILES = "files"


class ApiPath(StrEnum):
    """The path below `/api/`: the state is read-only; the chat takes a question by POST."""

    STATE = "v1/state"
    GRAPH = "v1/graph"
    STORIES = "v1/stories"  # also `v1/stories/<id>`: the checked result of one story
    DRAFT = "v1/draft"  # `?from=<qualified name>`: a draft spec; nothing is written
    CHAT = "v1/chat"


class MediaType(StrEnum):
    """The one body type that the chat route accepts; a rule forbids a string compare."""

    JSON = "application/json"


class AgentKind(StrEnum):
    """The coding agents that can answer. Claude is the default; codex is an opt-in."""

    CLAUDE = "claude"
    CODEX = "codex"


class ChatBlockKind(StrEnum):
    """What an agent block is: a statement about the code, or a change it suggests."""

    CLAIM = "claim"
    PROPOSAL = "proposal"


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


class SymbolKind(StrEnum):
    """The kinds of symbol that the graph keeps."""

    FUNCTION = "function"
    METHOD = "method"
    CLASS = "class"


class CallStatus(StrEnum):
    """How far the analysis resolved a call in `architecture.json`."""

    RESOLVED = "resolved"
    PARTIALLY_RESOLVED = "partially_resolved"
    UNRESOLVED = "unresolved"


class ComponentSource(StrEnum):
    """Where the components of the graph come from."""

    CONTRACT = "contract"
    LAYOUT = "layout"


class DeclarationKind(StrEnum):
    """The declaration of a top-level component in the explore layout."""

    COMPONENT = "component_responsibility"


class ScopeKind(StrEnum):
    """The scope record that lists the modules of a component in the explore layout."""

    DECLARED = "declared_component_scope_observation"


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


class ComponentRow(NamedTuple):
    id: str
    responsibility: str


class ModuleRow(NamedTuple):
    name: str
    file: str
    component: int  # index into `Graph.components`
    relative: str  # the name below the shared prefix of its component


class SymbolRow(NamedTuple):
    module: int  # index into `Graph.modules`
    name: str
    line: int
    kind: SymbolKind
    text: str  # the first source line, cut to a fixed length
    unknown: int  # the true number of unresolved calls; `Graph.unknown` keeps the first few
    outside: int  # resolved or partly resolved calls whose targets lie outside the scan


class EdgeRow(NamedTuple):
    source: int  # index into `Graph.symbols`
    target: int
    partial: bool
    line: int
    site: int  # one number for each call site: a partial call can give two edges


class UnknownRow(NamedTuple):
    symbol: int
    expression: str
    reason: str
    line: int


@dataclass(frozen=True)
class Graph:
    """The measured call graph of the snapshot, as rows; every cross reference is an index."""

    components_from: ComponentSource
    components: tuple[ComponentRow, ...]
    modules: tuple[ModuleRow, ...]
    symbols: tuple[SymbolRow, ...]
    edges: tuple[EdgeRow, ...]
    unknown: tuple[UnknownRow, ...]


def graph_json(explore: ExploreState, graph: Graph | None) -> bytes:
    """`GET /api/v1/graph`; `graph` is null while the explore run is not done."""
    body = None
    if graph is not None:
        body = {
            "components_from": graph.components_from,
            "components": graph.components,
            "modules": graph.modules,
            "symbols": graph.symbols,
            "edges": graph.edges,
            "unknown": graph.unknown,
        }
    return json.dumps(
        {"api_version": API_VERSION, "explore": explore, "graph": body}, sort_keys=True
    ).encode()


@dataclass(frozen=True)
class StoryRow:
    """One spec file of the stories folder."""

    id: str
    title: str
    steps: int


def stories_json(rows: Sequence[StoryRow]) -> bytes:
    """`GET /api/v1/stories`: the specs in the stories folder."""
    body = {"api_version": API_VERSION, "stories": [asdict(row) for row in rows]}
    return json.dumps(body, sort_keys=True).encode()


def story_json(story_id: str, checked: Mapping[str, Json]) -> bytes:
    """`GET /api/v1/stories/<id>`: the result of `archkeel view check`, as the CLI prints it."""
    body = {"api_version": API_VERSION, "id": story_id, "checked": checked}
    return json.dumps(body, sort_keys=True).encode()


def draft_json(spec: Mapping[str, Json]) -> bytes:
    """`GET /api/v1/draft?from=NAME`: a spec 1.2 with the traced path and no text; not written."""
    return json.dumps({"api_version": API_VERSION, "spec": spec}, sort_keys=True).encode()


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
    except (ValueError, RecursionError) as error:
        raise ChatFailure(ChatError.INVALID_REQUEST, "The body is not JSON.") from error
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
