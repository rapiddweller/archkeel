# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command shell: the Rust core decides each run and the shell prints its frame (AD-432).

The shell parses the arguments, finds the core binary, sends the scan identity, reads one frame
with `read_frame`, prints it as text or JSON, and maps the status to the exit code. It holds no
rule, fact or contract logic. `init` drafts the files of a new project (`init_draft`, AD-626) and
starts no core. A command that the core does not serve stays registered and gives a typed refusal
with exit 2; it never falls back and never reports success.
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

from .core_arguments import NotOnThisLine, Options, command_of, parse
from .core_baseline import as_json as baseline_json
from .core_binary import CoreBinaryNotFound, confirm, locate_core
from .core_binding import resolve_root
from .core_exit import exit_code
from .core_frame import CoreCommand as Command
from .core_frame import (
    CoreError,
    CoreFrame,
    GapKind,
    RefusalKind,
    Status,
    read_frame,
)
from .core_help import help_for
from .core_init import Created, prepare, run_init
from .core_json import Gap, RequestMismatch
from .core_output import write_output
from .core_text import header, refusal, render, summary
from .core_words import NOT_FOUND_PREFIX, fix_for, plain
from .init_draft import DOCUMENT
from .native_scan import SCAN_PROTOCOL, exchange, identity, ignored_by


def _wants_json(argv: Sequence[str]) -> bool:
    if "--summary" in argv:
        return False
    return "--json" in argv or (not sys.stdout.isatty() and "--text" not in argv)


def run(argv: Sequence[str]) -> int:
    """Run one command line and return its exit code. The core decides; the shell only maps."""

    as_json = _wants_json(argv)
    try:
        if not argv or argv[0] in {"-h", "--help"}:
            print(help_for(None), end="")
            return 0
        if argv[0] == "--version":
            print(f"archkeel {_version()}")
            return 0
        if {"-h", "--help"} & set(argv):
            print(help_for(_command_or_none(argv)), end="")
            return 0
        command_of(argv)
        options = parse(argv)
        if options.command is Command.SKILL:
            return _install_skill(options, as_json)
        if options.command is Command.INIT:
            return run_init("--json" in argv, resolve_root(options.root or Path.cwd()))
        return _decide(options, as_json)
    except (CoreError, OSError, ValueError) as error:
        message = str(error)
        if any(arg == "--output" or arg.startswith("--output=") for arg in argv):
            message += "; no report file was written"
        return _refused(_command_or_none(argv), _refusal_kind(error), message, as_json)
    except Exception as error:
        traceback.print_exc()
        return _refused(
            _command_or_none(argv),
            RefusalKind.INTERNAL_ERROR,
            f"{type(error).__name__}: {error}",
            as_json,
        )


def _command_or_none(argv: Sequence[str]) -> Command | None:
    """The command that the arguments name, if they name one that exists."""
    try:
        return Command(argv[0])
    except (ValueError, IndexError):
        return None


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


def _contract_files(document: Mapping[str, object]) -> list[str]:
    """The contract files that the scan read, as the core named them."""
    collect = (document.get("self_test") or {}).get("collect")  # type: ignore[attr-defined]
    files = collect.get("contract_files") if isinstance(collect, dict) else None
    return sorted(files) if isinstance(files, dict) else []


def _ignored_modules(
    frame: CoreFrame, document: Mapping[str, object], root: Path
) -> dict[str, str]:
    """For each imported module without a file: the Git ignore rule that covers the file, if any.

    The candidates are the paths that the module would have below each scan root.
    """
    names = sorted(
        {
            gap.reason.removeprefix(NOT_FOUND_PREFIX)
            for gap in frame.collection_gaps
            if gap.reason.startswith(NOT_FOUND_PREFIX)
        }
    )[:_IGNORE_CHECKS]
    if not names:
        return {}
    request = (document.get("self_test") or {}).get("collect", {}).get("request", {})  # type: ignore[attr-defined]
    scope = request.get("scope", {}) if isinstance(request, dict) else {}
    roots = [str(item) for item in scope.get("roots", [])] if isinstance(scope, dict) else []
    candidates: dict[str, str] = {}
    for name in names:
        path = name.replace(".", "/")
        below = path.partition("/")[2]
        for base in roots or ["."]:
            for tail in (path, below):
                for form in (f"{tail}.py", f"{tail}/__init__.py") if tail else ():
                    candidates[(Path(base) / form).as_posix()] = name
    found = ignored_by(root, list(candidates))
    return {candidates[path]: rule for path, rule in found.items() if path in candidates}


def _print_text(
    options: Options,
    frame: CoreFrame,
    document: Mapping[str, object],
    outcome: tuple[int, Gap | None, str | None],
    where: tuple[Path, Path],
) -> None:
    """Print one run as text: the problems first, then the summary, or one line for a report."""
    code, collected, file_error = outcome
    binary, root = where
    typed = (options.root, root)
    problems = [
        f"Problem: {plain(message, *typed)}"
        for message in (collected.reason if collected else None, file_error)
        if message is not None
    ]
    test = document.get("self_test")
    collect = test.get("collect") if isinstance(test, dict) else None
    target = collect.get("target") if isinstance(collect, dict) else None
    if options.output is not None and not options.text and file_error is None and not problems:
        detail = f"; {target}" if isinstance(target, str) else ""
        print(f"{header(options.command, frame, code)}; report written to {options.output}{detail}")
    elif collected is not None:
        message = plain(collected.reason, *typed)
        fix = fix_for(RefusalKind.COLLECTION_REFUSED, message)
        print("\n".join(refusal(options.command, code, message, fix)))
    elif options.summary:
        files = _contract_files(document)
        ignored = _ignored_modules(frame, document, root)
        print("\n".join(summary(options.command, frame, code, files, problems, ignored)))
    else:
        system = document.get("system")
        lines = render(
            options.command,
            frame,
            code,
            problems=problems,
            show_all=options.all,
            system=system if isinstance(system, dict) else None,
            contract_files=_contract_files(document),
            ignored=_ignored_modules(frame, document, root),
        )
        print("\n".join(lines))
        if isinstance(target, str):
            print(target)
        if options.output is not None and file_error is None:
            print(f"Report written to {options.output}")
        if options.verbose:
            print(f"Core: {binary}; engine: {frame.engine}; code digest: {frame.code_digest}")


def _decide(options: Options, as_json: bool) -> int:
    """Send the scan identity to the core and print the one frame that it gives."""
    options = _located(options)
    root = resolve_root(options.root or Path.cwd())
    first = prepare(options, root)  # AD-638: a project without archkeel.toml gets a draft
    if isinstance(first, str):
        return _refused(options.command, RefusalKind.INVALID_INPUT, first, as_json)
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
    code = exit_code(
        frame,
        baseline=options.baseline is not None,
        write_baseline=options.write_baseline is not None,
    )
    result: dict[str, object] = {
        "command": options.command,
        "status": frame.status,
        "exit_code": code,
        "frame": document,
        "core": {"path": str(binary), "engine": frame.engine, "code_digest": frame.code_digest},
        "gaps": [
            {"kind": gap.kind, "subject": gap.subject, "reason": gap.reason} for gap in frame.gaps
        ],
    }
    if frame.baseline is not None:
        result["baseline"] = baseline_json(frame.baseline)
    collected = next((gap for gap in frame.gaps if gap.kind is GapKind.COLLECT), None)
    if collected is not None and _NO_CONFIG in collected.reason:
        # The core names the cause; the way forward is the shell's to name (#1314).
        collected = replace(collected, reason=_config_reason(options, root, collected.reason))
    if collected is not None:
        result["refusal"] = {"kind": RefusalKind.COLLECTION_REFUSED, "message": collected.reason}
    if isinstance(first, Created):
        result["init"] = first.as_json()
    file_error = _deliver(options, frame, stdout, root)
    if file_error is not None:
        code = 2
        result["exit_code"] = code
        result["refusal"] = {"kind": RefusalKind.IO_ERROR, "message": file_error}
    if as_json and (options.json or options.output is None):
        print(json.dumps(result))
        return code
    if isinstance(first, Created):
        print("\n".join(first.lines()), end="\n\n")
    _print_text(options, frame, document, (code, collected, file_error), (binary, root))
    return code


_IGNORE_CHECKS: Final = 50
_NO_CONFIG: Final = "config: cannot read"
_MISSING_FIX: Final = (
    "create it (`archkeel init` drafts one) or name another file with --config PATH."
)


def _config_reason(options: Options, root: Path, reason: str) -> str:
    """Say whether the configuration file is missing, a folder or unreadable, and what to do."""
    path = root / options.config
    where = options.root or "the current folder"
    if not path.exists():
        return (
            f"{reason}: the file does not exist in {where}. A new project: run `archkeel init` to "
            "draft it, or name another file with --config PATH. "
            f"Guide: {DOCUMENT}"
        )
    if path.is_dir():
        return f"{reason}: {options.config} is a folder, not a file; name the file with --config."
    return f"{reason}: the file exists but cannot be read; check its permissions and encoding."


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


def _refused(command: Command | None, kind: RefusalKind, message: str, as_json: bool) -> int:
    """The refusal of a command that could not run: JSON, or the problem and the fix as text."""
    if as_json:
        print(
            json.dumps(
                {
                    "status": Status.UNKNOWN,
                    "exit_code": 2,
                    "refusal": {"kind": kind, "message": message},
                }
            )
        )
    else:
        print("\n".join(refusal(command, 2, plain(message), fix_for(kind, plain(message)))))
    return 2
