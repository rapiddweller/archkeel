# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The Python engine as one side of the dual run (AD-360). Delete this file with the engine.

The adapter calls the `report` command in process and writes no HTML page. It returns the
architecture.json bytes and the rule assessments of the JSON result. A case can name its own
collector; a Rust case without one uses the Rust collector of the workspace. A pinned collector
gets the digest of its program, as the tests pin it (AD-344).

Every run sees one identity of the engine, whatever is installed: the version `PINNED_VERSION`
and the code digest `PINNED_DIGEST`. The host expects the pinned version and digests the pinned
package source; the reply of a collector of this install carries the pinned version and code
digest. The binding of a member inventory proof reads these values. Without the pin the oracles
hold for one install (CI installs `4.0.2.dev293+g...`) and one state of the Python source only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest import mock

from archkeel.analyzer import process
from archkeel.analyzer.process import ProcessCollector
from archkeel.analyzer.runtime import package_version
from archkeel.check import observation
from archkeel.check.ports import Language
from archkeel.check.report import render_result, run_report_with_observation
from archkeel.cli.config import load_config
from archkeel.cli.observe import configured_observer, observer_for
from archkeel.ir.profiles import profile_for

# The engine identity that every dual run sees, for record and compare alike (AD-360).
PINNED_VERSION = "0.0.0"
PINNED_DIGEST = "0" * 64
# The first byte of a zlib stream; a plain JSON reply never starts with it.
ZLIB_HEADER = b"x"


def with_pinned_version(reply: bytes, installed: str) -> bytes:
    """The reply with the adapter version and code digest of a collector of this install set to
    the pin. A reply of another producer, or one that is not JSON, stays as it is."""
    compressed = reply[:1] == ZLIB_HEADER
    try:
        value = json.loads(zlib.decompress(reply) if compressed else reply)
    except (ValueError, zlib.error):
        return reply
    facts = value.get("facts") if isinstance(value, dict) else None
    adapter = facts.get("adapter") if isinstance(facts, dict) else None
    if not isinstance(adapter, dict) or adapter.get("version") != installed:
        return reply
    adapter["version"] = PINNED_VERSION
    adapter["code_digest"] = PINNED_DIGEST
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return zlib.compress(text) if compressed else text


@contextmanager
def pinned_version() -> Iterator[None]:
    """The one place of the pin: the host and the collector replies see the pinned identity."""
    installed = package_version()
    decode = ProcessCollector._decode_response

    def pinned(collector: ProcessCollector, stdout: bytes, request: Any) -> Any:
        return decode(collector, with_pinned_version(stdout, installed), request)

    with (
        mock.patch.object(process, "package_version", lambda: PINNED_VERSION),
        mock.patch.object(observation, "package_digest", lambda: PINNED_DIGEST),
        mock.patch.object(ProcessCollector, "_decode_response", pinned),
    ):
        yield


def run_python_engine(
    root: Path,
    config: str,
    baseline: str | None,
    collector_argv: tuple[str, ...] | None = None,
    pinned: bool = False,
    rust_collector: str | None = None,
    replies: list[bytes] | None = None,
) -> dict[str, Any]:
    """Return the engine frame: `rules` (id to kind and status) and `architecture`. With
    `replies`, each raw collector reply of the run is appended to it."""
    if replies is not None:
        decode = ProcessCollector._decode_response

        def captured(collector: ProcessCollector, stdout: bytes, request: Any) -> Any:
            replies.append(stdout)
            return decode(collector, stdout, request)

        with mock.patch.object(ProcessCollector, "_decode_response", captured):
            return run_python_engine(root, config, baseline, collector_argv, pinned, rust_collector)
    scan = load_config(root, config)
    argv = collector_argv
    if argv is None and scan.language == Language.RUST and scan.collector_argv is None:
        argv, pinned = (rust_collector or "archkeel-rust-collector",), True
    factory: Callable[..., Any] = observer_for
    if argv is not None:
        if not Path(argv[0]).is_file():
            return {"error": f"the collector {argv[0]} is missing: build it (`make dual-run`)"}
        digest = "sha256:" + hashlib.sha256(Path(argv[0]).read_bytes()).hexdigest()

        def factory(*args: Any, **options: Any) -> Any:
            options["collector_argv"] = argv
            options["pinned_digest"] = digest if pinned else None
            return observer_for(*args, **options)

    observer = configured_observer(scan, factory)
    with pinned_version():
        result, architecture, _ = run_report_with_observation(
            root,
            config=scan,
            analyzer=observer,
            baseline=None if baseline is None else Path(baseline),
        )
    rendered = json.loads(render_result(result))
    assessments = rendered["rule_assessments"] or []
    return {
        "rules": {row["id"]: [row["kind"], row["status"]] for row in assessments},
        # The run status of the reference engine; the core status is checked against it (AD-378).
        "declared_rules": rendered.get("declared_rules"),
        "architecture": None if architecture is None else json.loads(architecture),
    }


def reply_profile(reply: bytes) -> tuple[str, list[str]]:
    """The profile of a reply and the top-level standard library names of that profile (AD-372).
    The shell owns the table of profiles; the core names no language and checks that the
    profile is the profile of the reply. A reply that is not JSON gives no profile."""
    try:
        value = json.loads(zlib.decompress(reply) if reply[:1] == ZLIB_HEADER else reply)
        profile = value["facts"]["profile"]
        return profile, core_standard_library(profile_for(profile).standard_library)
    except (ValueError, KeyError, TypeError, zlib.error):
        return "", []


def core_standard_library(names: frozenset[str]) -> list[str]:
    """The standard library that the shell sends to the core (AD-388). The core pins
    `sys.stdlib_module_names`, which CPython defines the same on each platform. A built-in module
    of this build that is not in that set (a test module of a standalone build) is left out: an
    import of it is then external for the core, which is only stricter."""
    builds = frozenset(sys.builtin_module_names) - frozenset(sys.stdlib_module_names)
    return sorted(names - builds)
