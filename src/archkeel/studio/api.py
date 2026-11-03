# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-290: the routes and the typed state of the Studio API; `schema/studio-api-1.0` pins it."""

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Final

API_VERSION: Final = "1.0.0"


class Route(StrEnum):
    """The first path segment of a Studio URL; the empty segment is the shell."""

    SHELL = ""
    API = "api"
    UI = "ui"
    FILES = "files"


class ApiPath(StrEnum):
    """The path below `/api/`: one read-only resource for each version."""

    STATE = "v1/state"


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
    """The explore run that makes the snapshot in the cache folder."""

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
