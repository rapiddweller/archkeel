# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command shell: the Rust core decides each run and the shell prints its frame (AD-432).

The shell parses the arguments, finds the core binary, sends the scan identity, reads one frame
with `read_frame`, prints it as text or JSON, and maps the status to the exit code. It holds no
rule, fact or contract logic. A command that the core does not serve stays registered and gives a
typed refusal with exit 2; it never falls back and never reports success.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from time import time_ns
from typing import Final

from .core_arguments import HELP, NotOnThisLine, Options, command_of, parse
from .core_baseline import as_json as baseline_json
from .core_baseline import lines as baseline_lines
from .core_binary import CoreBinaryNotFound, confirm, locate_core
from .core_binding import resolve_root
from .core_frame import CoreCommand as Command
from .core_frame import (
    CoreError,
    CoreFrame,
    GapKind,
    RefusalKind,
    Status,
    read_frame,
)
from .core_json import RequestMismatch
from .core_output import write_output
from .native_scan import SCAN_PROTOCOL, exchange, identity

# The process exit of the core is not a command verdict (0 and 3 describe frame completeness).
EXIT_CODES: Final[Mapping[Status, int]] = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 2}


def _wants_json(argv: Sequence[str]) -> bool:
    return "--json" in argv or (not sys.stdout.isatty() and "--text" not in argv)


def run(argv: Sequence[str]) -> int:
    """Run one command line and return its exit code. The core decides; the shell only maps."""

    as_json = _wants_json(argv)
    try:
        if not argv or argv[0] in {"-h", "--help"}:
            print(HELP, end="")
            return 0
        if argv[0] == "--version":
            print(f"archkeel {_version()}")
            return 0
        command_of(argv)
        if {"-h", "--help"} & set(argv):
            print(HELP, end="")
            return 0
        options = parse(argv)
        if options.command is Command.SKILL:
            return _install_skill(options, as_json)
        return _decide(options, as_json)
    except (CoreError, OSError, ValueError) as error:
        message = str(error)
        if any(arg == "--output" or arg.startswith("--output=") for arg in argv):
            message += "; no report file was written"
        return _refused(_refusal_kind(error), message, as_json)
    except Exception as error:
        traceback.print_exc()
        return _refused(RefusalKind.INTERNAL_ERROR, f"{type(error).__name__}: {error}", as_json)


def _refusal_kind(error: Exception) -> RefusalKind:
    kinds: tuple[tuple[type[Exception], RefusalKind], ...] = (
        (RequestMismatch, RefusalKind.REQUEST_MISMATCH),
        (NotOnThisLine, RefusalKind.NOT_ON_THIS_LINE),
        (CoreBinaryNotFound, RefusalKind.CORE_BINARY_NOT_FOUND),
        (CoreError, RefusalKind.CORE_ERROR),
        (OSError, RefusalKind.IO_ERROR),
    )
    return next(
        (kind for form, kind in kinds if isinstance(error, form)), RefusalKind.INVALID_INPUT
    )


def _version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("archkeel")
    except PackageNotFoundError:
        return "unknown"


def _install_skill(options: Options, as_json: bool) -> int:
    from .skill import InstallationAgent, install_skill

    path = install_skill((options.root or Path.cwd()).resolve(), options.agent)
    if as_json:
        print(json.dumps({"command": Command.SKILL, "exit_code": 0, "path": str(path)}))
    else:
        name = "$archkeel" if options.agent == InstallationAgent.CODEX else "/archkeel"
        print(f"Installed Archkeel instructions: {path}")
        print(f"Use {name} in your agent session; start a new session if needed.")
    return 0


def _request(options: Options, root: Path) -> dict[str, object]:
    """The scan identity that the core answers, with the parts of the page and the baseline."""
    request: dict[str, object] = {
        "protocol": SCAN_PROTOCOL,
        "root": str(root),
        "config": options.config,
        "discover_root": options.root is None,
    }
    if (claim := identity(root)) is not None:
        request["git_head"], request["dirty"] = claim
    # AD-496: the page draws the architecture, so the core also builds the topology for it. The
    # section is transport for the page: stdout shows it only when the user asked for it.
    page = options.output is not None and options.format == "html"
    if options.topology or page:
        request["topology"] = True
    if page:
        request["html"] = True
    if options.baseline is not None:
        request["baseline"] = options.baseline
    if options.write_baseline is not None:
        request["write_baseline"] = True
    return request


def _exit_code(options: Options, frame: CoreFrame) -> int:
    """The status maps to the exit code. With a baseline, the core decided the code (AD-546)."""
    asked = options.baseline is not None or options.write_baseline is not None
    collect_refused = any(gap.kind is GapKind.COLLECT for gap in frame.gaps)
    if asked and frame.baseline is None and not collect_refused:
        raise CoreError("the core frame lacks the baseline part that the request asked for")
    if frame.baseline is not None:
        return frame.baseline.exit_code
    if options.baseline is not None and collect_refused:
        return 1  # AD-546: a refused scan has nothing to compare; exit 2 means all accepted
    return EXIT_CODES[frame.status]


def _deliver(options: Options, frame: CoreFrame, stdout: bytes, root: Path) -> str | None:
    """Write each requested file. The message of the last failure, or `None`."""
    failure: str | None = None
    try:
        _write_report(options, frame, stdout)
    except OSError as error:
        failure = f"cannot write report file {options.output}: {error}; no report file was written"
    try:
        _write_baseline(options, frame, root)
    except OSError as error:
        failure = f"cannot write the baseline file {error}; no baseline file was written"
    return failure


def _located(options: Options) -> Options:
    """Without `--root`, a configuration outside the repository of the working directory names
    its own repository: the root is the Git root above the file, and the path is relative to it."""
    if options.root is not None:
        return options
    config = Path(options.config)
    path = (config if config.is_absolute() else Path.cwd() / config).resolve()
    if not path.is_file():
        return options
    top = next((folder for folder in path.parents if (folder / ".git").exists()), None)
    if top is None or (not config.is_absolute() and Path.cwd().resolve().is_relative_to(top)):
        return options
    located = Options(**vars(options))
    located.root = top
    located.config = path.relative_to(top).as_posix()
    return located


def _decide(options: Options, as_json: bool) -> int:
    """Send the scan identity to the core and print the one frame that it gives."""
    options = _located(options)
    root = resolve_root(options.root or Path.cwd())
    request = _request(options, root)
    binary = locate_core()
    confirm(binary)  # a bundled core is checked again immediately before it starts (#1095)
    started_ns = time_ns()
    stdout, status_code = exchange(str(binary), "scan", json.dumps(request).encode())
    frame = read_frame(
        stdout,
        status_code,
        scan=True,
        require_protocol=True,
        request=request,
        started_ns=started_ns,
    )
    document = json.loads(stdout)
    document.pop("html", None)
    if isinstance(document.get("baseline"), dict):
        document["baseline"].pop("file", None)  # the bytes are written, not printed
    if "topology" in request and not options.topology:
        document.pop("topology", None)
        frame = replace(frame, topology=None)
    exit_code = _exit_code(options, frame)
    result: dict[str, object] = {
        "command": options.command,
        "status": frame.status,
        "exit_code": exit_code,
        "frame": document,
        "core": {"path": str(binary), "engine": frame.engine, "code_digest": frame.code_digest},
        "gaps": [
            {"kind": gap.kind, "subject": gap.subject, "reason": gap.reason} for gap in frame.gaps
        ],
    }
    if frame.baseline is not None:
        result["baseline"] = baseline_json(frame.baseline)
    collected = next((gap for gap in frame.gaps if gap.kind is GapKind.COLLECT), None)
    if collected is not None:
        result["refusal"] = {"kind": RefusalKind.COLLECTION_REFUSED, "message": collected.reason}
    file_error = _deliver(options, frame, stdout, root)
    if file_error is not None:
        exit_code = 2
        result["exit_code"] = exit_code
        result["refusal"] = {"kind": RefusalKind.IO_ERROR, "message": file_error}
    if as_json:
        print(json.dumps(result))
    else:
        if collected is None:
            render_text(options.command, frame)
        else:
            _refused(RefusalKind.COLLECTION_REFUSED, collected.reason, False)
        print(f"Core: {binary}; engine: {frame.engine}; code digest: {frame.code_digest}")
        if file_error is not None:
            _refused(RefusalKind.IO_ERROR, file_error, False)
    return exit_code


def _write_baseline(options: Options, frame: CoreFrame, root: Path) -> None:
    """Write the bytes that the core gave for `--write-baseline`. The shell adds nothing."""
    if options.write_baseline is None:
        return
    if frame.baseline is None or frame.baseline.file is None:
        raise CoreError(
            "the run cannot be written as a baseline: a part of it is refused, and no baseline "
            "accepts a refused part; no baseline file was written"
        )
    base = next((path for path in (root, *root.parents) if (path / ".git").exists()), root)
    target = base / options.write_baseline
    try:
        write_output(target, frame.baseline.file.encode("utf-8"))
    except OSError as error:
        raise OSError(f"{options.write_baseline}: {error}") from error


def _write_report(options: Options, frame: CoreFrame, stdout: bytes) -> None:
    if options.output is None:
        return
    if options.format == "html":
        if frame.html is None:
            raise CoreError("the core frame lacks the requested HTML")
        payload = frame.html.encode("utf-8")
    else:
        payload = stdout
    write_output(options.output, payload)


def _refused(kind: RefusalKind, message: str, as_json: bool) -> int:
    refusal = {
        "status": Status.UNKNOWN,
        "exit_code": 2,
        "refusal": {"kind": kind, "message": message},
    }
    print(json.dumps(refusal) if as_json else f"REFUSED: {kind}: {message}")
    return 2


_MAX_PLACES = 3


def _places(frame: CoreFrame, evidence: Sequence[str]) -> str:
    places = [
        f"{location.path}:{location.line}" if location.line else location.path
        for key in evidence
        if (location := frame.locations.get(key))
    ]
    # A gap that cites many places (AD-540: the uses behind a blocking form) names the first few.
    shown = places[:_MAX_PLACES]
    more = f", +{len(places) - len(shown)} more" if len(places) > len(shown) else ""
    return f" ({', '.join(shown)}{more})" if places else ""


def render_text(command: Command, frame: CoreFrame) -> None:
    """Print a frame as text."""
    print(f"{command}: {frame.status}")
    if frame.premise is not None:
        print(f"Assumption: {frame.premise}")
    if (topology := frame.topology) is not None:
        print(
            f"Topology: {len(topology.modules)}/{topology.total['modules']} modules, "
            f"{len(topology.edges)}/{topology.total['edges']} edges; "
            f"complete: {topology.complete}; truncated: {topology.truncated}"
        )
    if frame.baseline is not None:
        for line in baseline_lines(frame.baseline):
            print(line)
    if not frame.complete_scope:
        print(f"Scope: {frame.scope}")
        print("Action: Resolve the named scope gap and run again.")
    for source_gap in frame.collection_gaps:
        detail = f" ({source_gap.detail})" if source_gap.detail else ""
        print(
            f"Source gap: {source_gap.kind}: {', '.join(source_gap.subjects)}: "
            f"{source_gap.reason}{detail}{_places(frame, source_gap.evidence)}"
        )
        print("Action: Resolve the collector cause and run again.")
    for rule, rows in frame.details.items():
        for row in rows:
            edge = row.source if row.target is None else f"{row.source} -> {row.target}"
            print(f"{rule}: FAIL: {row.cause}: {edge}{_places(frame, row.evidence)}")
            print("Action: Remove the violation or review the declared restriction.")
    for rule, reason in frame.explained.items():
        print(f"{rule}: UNKNOWN: {frame.unknown_kinds[rule]}: {reason}")
        print("Action: Resolve the named gap and run again.")
    for gap in frame.gaps:
        if gap.kind is GapKind.RULE_KIND_NOT_PORTED:
            print(f"{gap.subject}: UNKNOWN: rule kind not decided by the core: {gap.reason}")
            print(
                "Action: Do not treat this rule as passed. The core has no port of its kind (#880)."
            )
        else:
            print(f"{gap.subject}: UNKNOWN: {gap.kind}: {gap.reason}")
            print("Action: Resolve the named part and run again (#880).")
