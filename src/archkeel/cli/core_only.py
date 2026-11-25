# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The command shell: the Rust core decides each run and the shell prints its frame (AD-432).

The shell parses the arguments, finds the core binary, sends the scan identity, reads one frame
with `read_frame`, prints it as text or JSON, and maps the status to the exit code. It holds no
rule, fact or contract logic. `init` drafts the files of a new project (`init_draft`, AD-626) and
starts no core. A command that the core does not serve stays registered and gives a typed refusal
with exit 2; it never falls back and never reports success. Each exit code comes from `exit_for`
(AD-731): with `--baseline`, only a verdict can exit 2.
"""

from __future__ import annotations

import copy
import json
import traceback
from collections.abc import Mapping, Sequence
from dataclasses import replace
from pathlib import Path
from time import time_ns
from typing import Final

from .core_arguments import NotOnThisLine, Options, OutputMode, command_of, output_mode, parse
from .core_baseline import as_json as baseline_json
from .core_binary import CoreBinaryNotFound, confirm, locate_core
from .core_binding import ProjectRoot, RootMode, resolve_root
from .core_delivery import _deliver, _explorer_report, _Refusal, _refuse_timings_target
from .core_exit import Outcome, envelope, exit_for, outcome_of, require_baseline_part
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
from .core_init import Created, InitOutcome, _prepare, _run_init
from .core_json import Gap, RequestMismatch
from .core_output import read_timings
from .core_text import header, refusal, render, summary
from .core_words import NOT_FOUND_PREFIX, fix_for, plain
from .init_draft import DOCUMENT, SYSTEM
from .native_scan import SCAN_PROTOCOL, exchange, identity, ignored_by, scan_progress


def run(argv: Sequence[str]) -> int:
    """Run one command line and return its exit code. The core decides; the shell only maps."""

    mode = output_mode(argv)  # AD-735: one output mode for the result and each refusal
    baseline = any(arg == "--baseline" or arg.startswith("--baseline=") for arg in argv)
    try:
        if not argv or argv[0] in {"-h", "--help"}:
            print(help_for(None), end="")
            return 0
        if argv[0] == "--version":
            print(f"archkeel {_version()}")
            return 0
        if {"-h", "--help"} & set(argv):
            command = _command_or_none(argv) or command_of(argv)
            print(help_for(command), end="")
            return 0
        command_of(argv)
        options = parse(argv)
        if options.command is Command.SKILL:
            return _install_skill(options, mode)
        if options.command is Command.INIT:
            return _run_init(mode is OutputMode.JSON, options)
        if options.command is Command.EXPLORE:
            return _explore(options, mode)
        return _decide(options, mode)
    except (CoreError, OSError, ValueError) as error:
        output = any(arg == "--output" or arg.startswith("--output=") for arg in argv)
        message = _message(error, output=output)
        kind = _refusal_kind(error)
        return _refused(_command_or_none(argv), kind, message, mode, baseline=baseline)
    except Exception as error:
        traceback.print_exc()
        return _refused(
            _command_or_none(argv),
            RefusalKind.INTERNAL_ERROR,
            f"{type(error).__name__}: {error}",
            mode,
            baseline=baseline,
        )


def _command_or_none(argv: Sequence[str]) -> Command | None:
    """The command that the arguments name, if they name one that exists."""
    try:
        return Command(argv[0])
    except (ValueError, IndexError):
        return None


def _message(error: Exception, *, output: bool) -> str:
    """The message of a refusal; with `--output`, it says that no report file was written."""
    return f"{error}; no report file was written" if output else str(error)


def _refusal_kind(error: Exception) -> RefusalKind:
    if isinstance(error, CoreError) and error.gap is not None:
        if error.gap.kind is GapKind.PARSE_WORK_LIMIT:
            return RefusalKind.PARSE_WORK_LIMIT
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


def _install_skill(options: Options, mode: OutputMode) -> int:
    from .skill import InstallationAgent, install_skill

    path = install_skill((options.root or Path.cwd()).resolve(), options.agent)
    code = exit_for(Outcome.COMPLETED, None, baseline=False)
    if mode is OutputMode.JSON:
        result = envelope(Command.SKILL, Outcome.COMPLETED, None, code) | {"path": str(path)}
        print(json.dumps(result))
    else:
        name = "$archkeel" if options.agent == InstallationAgent.CODEX else "/archkeel"
        print(f"Installed Archkeel instructions: {path}")
        print(f"Use {name} in your agent session; start a new session if needed.")
    return code


def _request(options: Options, project: ProjectRoot) -> dict[str, object]:
    """The scan identity that the core answers, with the parts of the page and the baseline."""
    request: dict[str, object] = {
        "protocol": SCAN_PROTOCOL,
        "root": str(project.path),
        "config": options.config,
        "discover_root": project.discover,
    }
    if (claim := identity(project.path)) is not None:
        request["git_head"], request["dirty"] = claim
    # AD-496: the page draws the architecture, so the core also builds the topology for it. The
    # section is transport for the page: stdout shows it only when the user asked for it.
    page = options.output is not None and options.format == "html"
    if options.topology or page:
        request["topology"] = True
    if page:
        request["html"] = True
    if options.explorer:
        request["explorer"] = True
    if page and options.part_of is not None:
        link: dict[str, str] = {"document": options.part_of}
        if options.system_href is not None:
            link["href"] = options.system_href
        request["part_of"] = link
    if options.baseline is not None:
        request["baseline"] = options.baseline
    if options.write_baseline is not None:
        request["write_baseline"] = True
    if options.timings is not None:
        request["timings"] = True
    return request


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
    ending: tuple[int, Outcome, Gap | None, list[_Refusal], bool],
    where: tuple[Path, ProjectRoot],
) -> None:
    """Print one run as text: the problems first, then the summary, or one line for a report."""
    code, outcome, collected, failures, drafted = ending
    binary, project = where
    root, scanned = project.path, _scanned(project)
    typed = (options.root, root)
    problems = [
        f"Problem: {plain(message, *typed)}"
        for message in (
            *([collected.reason] if collected else []),
            *(message for _, message in failures),
        )
    ]
    test = document.get("self_test")
    collect = test.get("collect") if isinstance(test, dict) else None
    target = collect.get("target") if isinstance(collect, dict) else None
    if options.output is not None and not options.text and not problems:
        detail = f"; {target}" if isinstance(target, str) else ""
        line = header(options.command, frame, code, outcome, scanned)
        print(f"{line}; report written to {options.output}{detail}")
    elif collected is not None:
        message = plain(collected.reason, *typed)
        fix = fix_for(RefusalKind.COLLECTION_REFUSED, message)
        lines = refusal(options.command, code, message, fix, scanned)
        print("\n".join([*lines, *problems[1:]]))
    elif options.summary:
        files = _contract_files(document)
        ignored = _ignored_modules(frame, document, root)
        lines = summary(
            options.command, frame, code, files, problems, ignored, outcome=outcome, scanned=scanned
        )
        print("\n".join(lines))
    else:
        system = document.get("system")
        lines = render(
            options.command,
            frame,
            code,
            outcome=outcome,
            scanned=scanned,
            drafted=drafted,
            problems=problems,
            show_all=options.all,
            system=system if isinstance(system, dict) else None,
            contract_files=_contract_files(document),
            ignored=_ignored_modules(frame, document, root),
        )
        print("\n".join(lines))
        if isinstance(target, str):
            print(target)
        if options.output is not None and not failures:
            print(f"Report written to {options.output}")
        if options.verbose:
            print(f"Core: {binary}; engine: {frame.engine}; code digest: {frame.code_digest}")


def _decide(options: Options, mode: OutputMode) -> int:
    """Draft the files of a first run, then scan. A failure after a write still names the files."""
    # AD-735, AD-776: one root and one configuration for the draft, the scan and the files.
    project = ProjectRoot.of(options.root, options.config if options.config_given else None)
    options = copy.copy(options)
    options.config = project.config
    baseline = options.baseline is not None
    binary = locate_core()  # AD-735: the core is found and checked before the draft writes a file
    options, init = _prepare(options, project)  # AD-638, AD-660: a first run gets its files
    project = replace(project, config=options.config)
    if (stop := init.refusal()) is not None:
        kind, fix = stop
        return _refused(
            options.command,
            kind,
            init.message,
            mode,
            baseline=baseline,
            fix=fix,
            init=init,
            project=project,
        )
    try:
        return _scan(options, project, binary, init.created, mode)
    except (CoreError, OSError, ValueError) as error:
        if init.created is None:
            raise
        message = _message(error, output=options.output is not None)
        kind = _refusal_kind(error)
        return _refused(
            options.command, kind, message, mode, baseline=baseline, init=init, project=project
        )


def _explore(options: Options, mode: OutputMode) -> int:
    from .core_explorer import launch

    project = ProjectRoot.of(options.root, options.config if options.config_given else None)
    configured = (project.path / project.config).is_file()
    if not configured and not options.config_given and (project.path / SYSTEM).is_file():
        configured = True
        project = replace(project, config=SYSTEM)
    if not configured and options.config_given:
        raise ValueError("choose an existing Explorer configuration with --config")
    binary = locate_core()

    def scan(target: ProjectRoot, *, html: bool = False) -> tuple[bytes, CoreFrame]:
        report = Options(
            command=Command.REPORT,
            config=target.config,
            topology=True,
            explorer=not html,
            output=Path("report.html") if html else None,
        )
        return _exchange_scan(report, target, binary, [])

    render_report = (lambda: _explorer_report(*scan(project, html=True))) if configured else None
    return launch(options, mode, project, binary, scan, render_report)


def _exchange_scan(
    options: Options, project: ProjectRoot, binary: Path, sink: list[bytes]
) -> tuple[bytes, CoreFrame]:
    """Request and bind a core frame before delivery or publication."""
    request = _request(options, project)
    confirm(binary)  # a bundled core is checked again immediately before it starts (#1095)
    started_ns = time_ns()
    payload = json.dumps(request).encode()
    with scan_progress(project.path):
        if options.timings is None:  # #659: the phase seconds come on standard error only if asked
            stdout, status_code = exchange(str(binary), "scan", payload)
        else:
            stdout, status_code = exchange(str(binary), "scan", payload, stderr_sink=sink)
    frame = read_frame(
        stdout,
        status_code,
        scan=True,
        require_protocol=True,
        request=request,
        started_ns=started_ns,
    )
    return stdout, frame


def _scan(
    options: Options, project: ProjectRoot, binary: Path, created: Created | None, mode: OutputMode
) -> int:
    """Send the scan identity to the core and print the one frame that it gives."""
    baseline = options.baseline is not None
    root = project.path
    _refuse_timings_target(options, root)
    sink: list[bytes] = []
    stdout, frame = _exchange_scan(options, project, binary, sink)
    document = json.loads(stdout)
    document.pop("html", None)
    if isinstance(document.get("baseline"), dict):
        document["baseline"].pop("file", None)  # the bytes are written, not printed
    if not options.topology:
        document.pop("topology", None)
        frame = replace(frame, topology=None)
    require_baseline_part(frame, asked=baseline or options.write_baseline is not None)
    collected = next((gap for gap in frame.gaps if gap.kind is GapKind.COLLECT), None)
    if collected is not None and _NO_CONFIG in collected.reason:
        # The core names the cause; the way forward is the shell's to name (#1314).
        collected = replace(collected, reason=_config_reason(options, project, collected.reason))
    timings = None
    if options.timings is not None:
        refused = any(gap.kind is GapKind.COLLECT for gap in frame.gaps)
        timings = read_timings(sink[0], refused=refused)
    failures = _deliver(options, frame, stdout, root, document, timings)
    outcome = outcome_of(frame, delivered=not failures)
    code = exit_for(outcome, frame, baseline=baseline)
    result = (
        envelope(options.command, outcome, frame.status, code)
        | project.as_json()
        | {
            "frame": document,
            "core": {"path": str(binary), "engine": frame.engine, "code_digest": frame.code_digest},
            "gaps": [
                {"kind": gap.kind, "subject": gap.subject, "reason": gap.reason}
                for gap in frame.gaps
            ],
        }
    )
    if frame.baseline is not None:
        result["baseline"] = baseline_json(frame.baseline)
    refusals = [(RefusalKind.COLLECTION_REFUSED, collected.reason)] if collected else []
    result |= _refusal_fields([*refusals, *failures])
    if created is not None:
        result["init"] = created.as_json()
    if mode is OutputMode.JSON:
        print(json.dumps(result))
        return code
    if created is not None:
        print("\n".join(created.lines()), end="\n\n")
    ending = (code, outcome, collected, failures, created is not None)
    _print_text(options, frame, document, ending, (binary, project))
    return code


def _scanned(project: ProjectRoot) -> str:
    """The root and the configuration of a run for its header, from the current folder."""
    root, config = project.named(Path.cwd())
    return f" · root {root} · config {config}"


def _refusal_fields(refusals: Sequence[_Refusal]) -> dict[str, object]:
    """`refusal` is the first refusal, and `refusals` lists each one in order; none is lost."""
    if not refusals:
        return {}
    rows = [{"kind": kind, "message": message} for kind, message in refusals]
    return {"refusal": rows[0], "refusals": rows}


_IGNORE_CHECKS: Final = 50
_NO_CONFIG: Final = "config: cannot read"
_MISSING_FIX: Final = (
    "create it (`archkeel init` drafts one) or name another file with --config PATH."
)


def _config_reason(options: Options, project: ProjectRoot, reason: str) -> str:
    """Say whether the configuration file is missing, a folder or unreadable, and what to do.

    The file is where the core looked for it: below the project root.
    """
    path = project.path / options.config
    where = _where(options, project)
    if not path.exists():
        return (
            f"{reason}: the file does not exist in {where}. A new project: run `archkeel init` to "
            "draft it, or name another file with --config PATH. "
            f"Guide: {DOCUMENT}"
        )
    if path.is_dir():
        return f"{reason}: {options.config} is a folder, not a file; name the file with --config."
    return f"{reason}: the file exists but cannot be read; check its permissions and encoding."


def _where(options: Options, project: ProjectRoot) -> str:
    """The project root in the words of the user: the typed `--root`, or the folder found."""
    match project.mode:
        case RootMode.EXPLICIT:
            return str(options.root)
        case RootMode.CONFIG:
            return f"the root that the configuration names ({project.path})"
        case RootMode.WORK_TREE if project.path != resolve_root(Path.cwd()):
            return f"the top of the Git work tree ({project.path})"
        case RootMode.WORK_TREE | RootMode.CURRENT:
            return "the current folder"


def _refused(
    command: Command | None,
    kind: RefusalKind,
    message: str,
    mode: OutputMode,
    *,
    baseline: bool,
    fix: str | None = None,
    init: InitOutcome | None = None,
    project: ProjectRoot | None = None,
) -> int:
    """The refusal of a command that could not run: JSON, or the problem and the fix as text.

    `fix` replaces the fix of the kind. `init` is the draft step: the files that it wrote come
    first, so that a refusal after a write still names them (AD-735).
    """
    code = exit_for(Outcome.COMMAND_REFUSED, None, baseline=baseline)
    created = init.created if init is not None else None
    if mode is OutputMode.JSON:
        document = envelope(command, Outcome.COMMAND_REFUSED, Status.UNKNOWN, code)
        document |= project.as_json() if project is not None else {}
        document["refusal"] = {"kind": kind, "message": message}
        if init is not None:
            document["init"] = created.as_json() if created else {"state": init.state}
        print(json.dumps(document))
        return code
    if created is not None:
        print("\n".join(created.lines()), end="\n\n")
    words = plain(message)
    scanned = _scanned(project) if project is not None else ""
    print("\n".join(refusal(command, code, words, fix or fix_for(kind, words), scanned)))
    return code
