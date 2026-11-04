# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the routes and the typed answers of the Studio API; `schema/studio-api-1.1` pins them."""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final, NamedTuple, TypeAlias, TypeVar

API_VERSION: Final = "1.1.0"

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
    """The path below `/api/`: one read-only resource for each version."""

    STATE = "v1/state"
    GRAPH = "v1/graph"
    STORIES = "v1/stories"  # also `v1/stories/<id>`: the checked result of one story
    DRAFT = "v1/draft"  # `?from=<qualified name>`: a draft spec; nothing is written


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
