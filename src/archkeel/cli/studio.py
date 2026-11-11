# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Serve ArchKeel Studio: the workspace, its stories and the single-instance launch (AD-290).

Only the `studio` command imports this module: it pulls in the HTTP server and the file lock.
"""

from __future__ import annotations

import os
import re
import signal
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable, Sequence
from contextlib import ExitStack
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

from ..check.report import read_saved_snapshot
from ..check.snapshot import resolve_commit
from ..ir.codec import RawJson, decode_canonical_model, decode_json, parse_contract
from ..ir.facts_codec import DEFAULT_RESPONSE_LIMIT_BYTES
from ..ir.story import trace_flow
from ..ir.view_spec import (
    ViewCheckSession,
    check_view,
    parse_view_spec,
    snapshot_identity,
    view_check_json,
)
from ..studio.api import AgentKind, ContractState, StorySource
from ..studio.server import run_studio
from ..studio.stories import CheckResult, Stories
from ..studio.workspace import Workspace
from .arguments import CLIArguments, Command, cache_folder, root_digest
from .config import ConfigFileMissingError, load_config
from .launcher import (
    StudioLockTimeout,
    StudioProcess,
    StudioScope,
    _recovery_hint,
    forget_state,
    running_studio,
    stop_studio,
    studio_lock,
    write_state,
)

_DRAFT_HOPS: Final = 12
# Where the committed stories of a root lie; Studio reads them and never writes there (AD-291).
_REPOSITORY_STORIES: Final = Path(".archkeel") / "stories"


def _contract_state(root: Path) -> ContractState:
    """AD-290: the contract as `report` loads it: missing, invalid or configured."""
    try:
        config = load_config(root)
        parse_contract(decode_json((root / config.contract).read_bytes()))
    except ConfigFileMissingError:
        return ContractState.NOT_CONFIGURED
    except (OSError, ValueError):
        return ContractState.INVALID
    return ContractState.CONFIGURED


def _declared_components(root: Path, modules: Sequence[str]) -> list[tuple[str, str, list[str]]]:
    """AD-290: (label, first responsibility, owned modules) for each component of the contract.

    The contract decides who owns a module, as `check` does. No contract gives no component.
    """
    try:
        config = load_config(root)
        contract = parse_contract(decode_json((root / config.contract).read_bytes()))
    except (ConfigFileMissingError, OSError, ValueError):
        return []
    owned: dict[str, list[str]] = {component.id: [] for component in contract.components}
    for module in modules:
        if (owner := contract.component_for(module)) is not None:
            owned[owner.id].append(module)
    return [
        (
            component.label,
            component.responsibilities[0] if component.responsibilities else "",
            owned[component.id],
        )
        for component in contract.components
    ]


def _decode_snapshot(raw: bytes) -> dict[str, RawJson]:
    """AD-290: the canonical model of a saved `architecture.json`, strings expanded."""
    decoded = decode_json(raw)
    if not isinstance(decoded, dict):
        raise ValueError("architecture.json must be an object")
    try:
        return decode_canonical_model(decoded)
    except (IndexError, KeyError, TypeError) as error:
        # A damaged columnar file can fail outside the codec checks: one error for the caller.
        raise ValueError(f"architecture.json is damaged: {error!r}") from error


def _check_story(
    spec: bytes, snapshot: Path, session: ViewCheckSession | None = None
) -> CheckResult:
    """AD-291: `archkeel view check SPEC --snapshot SNAPSHOT`, bound to this snapshot.

    A stored spec names the digests of the snapshot it was written on. Studio checks it against
    the current snapshot by node name: the digests are replaced in memory, never in the file.
    """
    observation = session.observation if session is not None else read_saved_snapshot(snapshot)
    parsed = parse_view_spec(decode_json(spec))
    identity = snapshot_identity(observation)
    rebound = parsed.snapshot != identity
    checked_spec = replace(parsed, snapshot=identity) if rebound else parsed
    checked = (
        session.check(checked_spec, strict=False)
        if session is not None
        else check_view(checked_spec, observation, strict=False)
    )
    decoded = decode_json(view_check_json(checked).encode())
    if not isinstance(decoded, dict):
        raise ValueError("the view check must be an object")
    return CheckResult(decoded, rebound)


def _head_of(root: Path) -> str | None:
    """The commit of the root now, or None without Git."""
    try:
        return resolve_commit(root, "HEAD")
    except RuntimeError:  # SnapshotError: no Git, or no commit
        return None


def _draft_story(snapshot: Path, source: str) -> dict[str, RawJson]:
    """AD-291: a spec 1.2 along the first traced path from `source`, with no text; not written."""
    observation = read_saved_snapshot(snapshot)
    trace = trace_flow(observation, source, None, max_paths=1, max_hops=_DRAFT_HOPS)
    names = [source, *(hop.node.name for path in trace.paths[:1] for hop in path.hops)]
    story_id = re.sub(r"[^a-z0-9]+", "-", source.rsplit(".", 1)[-1].lower()).strip("-") or "story"
    return {
        "schema_version": "1.2.0",
        "title": f"Story from {source}",
        "snapshot": {
            "source_digest": trace.snapshot.source_digest,
            "contract_digest": trace.snapshot.contract_digest,
        },
        "nodes": names,
        "story": {"id": f"{story_id}-draft", "title": f"Story from {source}", "chapters": []},
        "steps": [{"node": name} for name in names],
    }


def _story_checker() -> tuple[Callable[[bytes, Path], CheckResult], Callable[[], None]]:
    """Reuse a Workspace snapshot session; Workspace clears it before every new run."""
    cached_snapshot: Path | None = None
    cached_session: ViewCheckSession | None = None
    generation = 0
    cache_lock = threading.Lock()

    def check(spec: bytes, snapshot: Path) -> CheckResult:
        nonlocal cached_snapshot, cached_session
        with cache_lock:
            requested_generation = generation
            session = cached_session if cached_snapshot == snapshot else None
        if session is None:
            built_session = ViewCheckSession(read_saved_snapshot(snapshot))
            with cache_lock:
                if generation == requested_generation:
                    if cached_snapshot != snapshot or cached_session is None:
                        cached_snapshot = snapshot
                        cached_session = built_session
                    session = cached_session
                else:
                    # The Workspace invalidated this build while the snapshot was loading.
                    session = built_session
        return _check_story(spec, snapshot, session=session)

    def clear() -> None:
        nonlocal cached_snapshot, cached_session, generation
        with cache_lock:
            generation += 1
            cached_snapshot = None
            cached_session = None

    return check, clear


def studio_workspace(args: CLIArguments, cache: Path) -> Workspace:
    """AD-290: each run explores with the scope options into a private folder of `cache`."""
    root = args.root.resolve()
    cache.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="studio-", dir=cache))
    scope = [
        f"--language={args.language.value}",
        *(f"--source={item}" for item in args.source or ()),
    ]
    scope += [
        f"--{name}={value}"
        for name, value in (("namespace", args.namespace), ("tsconfig", args.tsconfig))
        if value is not None
    ]
    if args.collector_output_limit_bytes is not None:
        scope.append(f"--collector-output-limit-bytes={args.collector_output_limit_bytes}")
    explore = (sys.executable, "-m", "archkeel.cli", Command.EXPLORE.value, "--root", str(root))
    check_story, clear_story_check = _story_checker()
    return Workspace(
        root,
        folder,
        (*explore, *scope, "--output", str(folder), "--json"),
        lambda: _contract_state(root),
        lambda modules: _declared_components(root, modules),
        _decode_snapshot,
        # Outside `folder`: the run deletes `folder` at its end, and the specs must stay.
        Stories(
            [
                (StorySource.REPOSITORY, root / _REPOSITORY_STORIES),
                (StorySource.LOCAL, cache / "stories"),
            ],
            check_story,
            _draft_story,
            lambda: _head_of(root),
            clear_story_check,
        ),
    )


def _studio_scope(args: CLIArguments) -> StudioScope:
    return StudioScope(
        args.language.value,
        tuple(args.source or ()),
        args.namespace,
        args.tsconfig,
        AgentKind(args.chat_agent.value),
        (
            args.collector_output_limit_bytes
            if args.collector_output_limit_bytes is not None
            else DEFAULT_RESPONSE_LIMIT_BYTES
        ),
    )


def serve_studio(args: CLIArguments) -> int:
    """AD-290: reuse the running Studio of the root, stop it, or serve a new one."""
    root = args.root.resolve()
    cache = cache_folder(Command.EXPLORE, root_digest(root))
    if args.stop:
        return stop_studio(cache)

    requested_scope = _studio_scope(args)
    agent = requested_scope.agent
    lock: ExitStack = ExitStack()
    session_lock = studio_lock(cache)
    try:
        lock.enter_context(session_lock)
    except StudioLockTimeout:
        print(
            "ArchKeel Studio: another start or stop has held the session lock for "
            f"{session_lock.timeout:g} seconds; "
            "no session was started. Retry when it finishes, or interrupt the stuck CLI process.",
            file=sys.stderr,
        )
        return 1
    previous = None
    try:
        if (live := running_studio(cache)) is not None:
            if live.stopping:
                print(
                    "ArchKeel Studio: the previous session is still cleaning up; no new session "
                    "was started. Retry after `archkeel studio --stop` finishes. "
                    f"{_recovery_hint(cache)}"
                )
                return 1
            if live.scope != requested_scope:
                active = "unknown" if live.scope is None else repr(live.scope)
                print(
                    "ArchKeel Studio: an active session has a different or unknown scope "
                    f"({active}); requested {requested_scope!r}. Run `archkeel studio --stop` "
                    "before starting with this scope.",
                    flush=True,
                )
                return 2
            print(f"ArchKeel Studio: {live.url} (already running)", flush=True)
            if not args.no_open:
                webbrowser.open(live.url)
            return 0

        def ready(url: str) -> None:
            port = urlsplit(url).port
            started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            write_state(
                cache,
                StudioProcess(os.getpid(), url, port, str(root), started, requested_scope),
            )
            if not args.no_open:
                webbrowser.open(url)

        # SIGTERM stops the server like Ctrl-C: the workspace and the state file are cleaned up.
        # A shell starts a background job with SIGINT ignored; the explore child would inherit that
        # and could not unwind on the SIGINT of `Workspace.close`. A Python handler resets on exec.
        previous = {
            number: signal.signal(number, signal.default_int_handler)
            for number in (signal.SIGTERM, signal.SIGINT)
        }
        return run_studio(
            studio_workspace(args, cache),
            ready=ready,
            serving=lock.close,
            idle_seconds=args.idle_exit * 60,
            agent=agent,
        )
    finally:
        if previous is not None:
            for number, handler in previous.items():
                signal.signal(number, handler)
            forget_state(cache, os.getpid())
        lock.close()
