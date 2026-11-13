# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Run repository observations and declaration checks."""

from __future__ import annotations

import io
import json
import os
import sys
from collections.abc import Sequence
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from .legacy_parser_base import _Parser as _Parser
from .output_path import html_path as html_path

if TYPE_CHECKING:
    from .arguments import Command


def cache_folder(command: Command, digest: str) -> Path:
    from .arguments import cache_folder as folder

    return folder(command, digest)


def root_digest(root: Path) -> str:
    from .arguments import root_digest as digest

    return digest(root)


def main(argv: Sequence[str] | None = None) -> int:
    from .core_only import requested, run

    arguments = list(sys.argv[1:] if argv is None else argv)
    if requested(arguments, os.environ):
        return run(arguments)
    return _legacy_main(arguments)


def build_parser() -> _Parser:
    from .legacy_parser import build_parser as parser

    return parser()


def _legacy_main(argv: Sequence[str] | None = None) -> int:
    from .legacy_bindings import (
        ADOPTED_BASELINE_PATH,
        CONFIG_PATH,
        GUIDE_PATH,
        Command,
        ConfigFileMissingError,
        ConfigurationSource,
        InstallationAgent,
        NativeCore,
        Phase,
        PhaseClock,
        ReportMode,
        WorkCounter,
        check_view,
        collect_cycles_less_often,
        configuration_source,
        configured_observer,
        decode_json,
        install_skill,
        invalid_result,
        load_check_config,
        load_config,
        load_gitlab_records,
        measured,
        observer_for,
        parse_config,
        parse_view_spec,
        progress,
        project_name,
        read_blob,
        read_saved_snapshot,
        render_architecture_pages,
        render_check_html,
        render_result,
        resolve_commit,
        run_check,
        run_explore,
        run_guide,
        run_init,
        run_report_with_observation,
        run_saved_report,
        run_validate,
        trace_flow,
        trace_json,
        trace_summary,
        unknown_result,
        view_check_json,
        view_summary,
    )
    from .legacy_output import (
        clear_report as _clear_report,
    )
    from .legacy_output import (
        html_path,
        show_result,
    )
    from .legacy_output import show_view as _show_view
    from .legacy_output import (
        write_files as _write_files,
    )
    from .legacy_output import (
        write_json as _write_json,
    )
    from .legacy_output import (
        write_pages as _write_pages,
    )
    from .legacy_output import (
        write_timings as _write_timings,
    )
    from .legacy_parser import _report_option_error
    from .legacy_parser_base import _ARCHITECTURE_JSON, _PER_RUN_LIMIT_REMEDY, _SNAPSHOT_PATH

    parser = build_parser()
    command = Command.ARGUMENTS
    subject = "command-line arguments"
    interactive = sys.stdout.isatty()
    artifacts: list[Path] = []
    files: tuple[tuple[str, bytes], ...] = ()
    try:
        args = parser.parse_cli_args(argv)
        if args.command is None:
            parser.print_help()
            return 0
        command = args.command
        interactive = interactive and not args.json
        if command is Command.SKILL:
            path = install_skill(args.root.resolve(), args.agent)
            print(
                f"Installed Archkeel instructions: {path}\n"
                f"Use {'$archkeel' if args.agent is InstallationAgent.CODEX else '/archkeel'} "
                "in your agent session; start a new session if needed."
                if interactive
                else json.dumps({"command": Command.SKILL, "exit_code": 0, "path": str(path)})
            )
            return 0
        if command is Command.STUDIO:
            subject = str(args.root)
            from .studio import serve_studio

            return serve_studio(args)
        collect_cycles_less_often()
        if args.config is None and (command is not Command.REPORT or args.input is None):
            args.config = CONFIG_PATH
        if command is Command.GUIDE:
            return run_guide(args.root.resolve(), args.config, args.output, args.check)
        if command is Command.STORY:
            subject = str(args.snapshot)
            trace_result = trace_flow(
                read_saved_snapshot(args.snapshot),
                args.source,
                args.target,
                max_paths=args.max_paths,
                max_hops=args.max_hops,
            )
            sys.stdout.write(
                trace_summary(trace_result) + "\n" if interactive else trace_json(trace_result)
            )
            return 0
        if command is Command.VIEW:
            subject = str(args.spec)
            spec_bytes = Path.read_bytes(args.spec)
            spec = parse_view_spec(decode_json(spec_bytes))
            subject = str(args.snapshot)
            view = check_view(spec, read_saved_snapshot(args.snapshot), strict=args.strict)
            text = view_check_json(view)
            # Exit 2: the check did not run, so there is no picture to write.
            drawn = args.show and view.exit_code != 2
            page = _show_view(view, text, spec_bytes, args.snapshot, args.output) if drawn else None
            sys.stdout.write(view_summary(view) + "\n" if interactive else text)
            if drawn and page is None:
                sys.stderr.write("archkeel view show: not drawn: the snapshot has no Explorer\n")
                return 2
            if page is not None:
                sys.stderr.write(f"archkeel view show: wrote {page}\n")
            return view.exit_code
        root = (args.root or Path.cwd()).resolve()
        subject = str(root / (args.config or CONFIG_PATH))
        activity = (
            f"reading recorded {args.input.name}"
            if command is Command.REPORT and args.input is not None
            else f"observing {root.name}"
        )
        if command is Command.REPORT and (error := _report_option_error(args)):
            subject = str(args.input if args.input is not None else root)
            parser.error(error)
        with progress(f"archkeel {command}: {activity}"):
            if command is Command.INIT:
                subject = str(root)
                init_analyzer = observer_for(
                    args.language,
                    collector_argv=tuple(args.collector_argv) if args.collector_argv else None,
                    tsconfig=args.tsconfig or "tsconfig.json",
                    output_limit_bytes=args.collector_output_limit_bytes,
                    output_limit_remedy=_PER_RUN_LIMIT_REMEDY,
                    timeout_seconds=args.collector_timeout_seconds,
                )
                result, requested_files = run_init(
                    root,
                    source=tuple(args.source) if args.source is not None else None,
                    namespace=args.namespace,
                    force=args.force,
                    full=args.full,
                    adopt_baseline=ADOPTED_BASELINE_PATH if args.adopt else None,
                    analyzer=init_analyzer,
                    language=args.language,
                    tsconfig=args.tsconfig,
                    collector_argv=tuple(args.collector_argv) if args.collector_argv else None,
                    collector_output_limit_bytes=args.collector_output_limit_bytes,
                    collector_timeout_seconds=args.collector_timeout_seconds,
                )
                files = requested_files.entries
            elif command is Command.EXPLORE:
                # AD-285: a result names the root by its basename, never by its path.
                subject = root.name
                digest = root_digest(root)
                folder: Path = Path(args.output or cache_folder(Command.EXPLORE, digest)).resolve()
                if folder.is_relative_to(root):
                    parser.error(
                        "--output is inside the analyzed repository; choose a folder outside it"
                    )
                artifact: Path = folder / _ARCHITECTURE_JSON
                result, architecture, observation = run_explore(
                    root,
                    observer=observer_for(
                        args.language,
                        tsconfig=args.tsconfig or "tsconfig.json",
                        output_limit_bytes=args.collector_output_limit_bytes,
                        output_limit_remedy=_PER_RUN_LIMIT_REMEDY,
                    ),
                    source=tuple(args.source) if args.source is not None else None,
                    namespace=args.namespace,
                    language=args.language,
                    tsconfig=args.tsconfig,
                )
                result = replace(result, root_name=root.name, root_digest=digest)
                # The scope and HEAD passed: no earlier snapshot of ours may look current now.
                _clear_report(artifact)
                if architecture is not None:
                    result = replace(result, artifact=str(artifact))
                    _write_json(artifact, architecture)
                    pages = render_architecture_pages(
                        result,
                        architecture,
                        repository=root.name,
                        architecture_href=artifact.name,
                        observation=observation,
                    )
                    _write_pages(artifact, pages, artifacts)
            elif command is Command.REPORT and args.input is not None:
                subject = str(args.input)
                conflicts = tuple(
                    option
                    for option, value in (
                        ("--root", args.root),
                        ("--config", args.config),
                        ("--baseline", args.baseline),
                        ("--output", args.output),
                        ("--timings", args.timings),
                    )
                    if value is not None
                )
                if conflicts:
                    parser.error(f"--input cannot be combined with {', '.join(conflicts)}")
                result = run_saved_report(
                    args.input,
                    only_violations=args.only is ReportMode.VIOLATIONS,
                    only_calls=args.only is ReportMode.CALLS,
                    only_architecture=args.only is ReportMode.ARCHITECTURE,
                    rule=args.rule,
                    component=args.component,
                    full_architecture=args.full,
                )
            elif command is Command.REPORT:
                config = load_config(root, args.config or CONFIG_PATH)
                subject = str(root)
                clock = PhaseClock() if args.timings is not None else None
                core = NativeCore.requested(args.native_core, os.environ)
                observer = configured_observer(config, core.observer(observer_for), clock)
                result, architecture, observation = run_report_with_observation(
                    root,
                    config=config,
                    analyzer=observer,
                    only_violations=args.only is ReportMode.VIOLATIONS,
                    only_calls=args.only is ReportMode.CALLS,
                    only_architecture=args.only is ReportMode.ARCHITECTURE,
                    rule=args.rule,
                    component=args.component,
                    full_architecture=args.full,
                    baseline=args.baseline,
                    clock=clock,
                )
                notes = config.scope_notes(observer.excluded_for())
                result = replace(result, scan_roots=config.roots, notes=(*result.notes, *notes))
                result = core.decide(result, root, config, args.config or CONFIG_PATH)
                if architecture is not None:
                    artifact = args.output or root / _SNAPSHOT_PATH
                    # The pages show the artifact path, so it is set before they render.
                    resolved = artifact.resolve()
                    result = replace(
                        result,
                        artifact=None
                        if args.only is ReportMode.ARCHITECTURE
                        else (
                            str(resolved.relative_to(root))
                            if resolved.is_relative_to(root)
                            else str(resolved)
                        ),
                    )
                    _write_json(artifact, architecture)
                    # A render failure must not publish a partial HTML set.
                    with measured(clock, Phase.RENDER):
                        pages = render_architecture_pages(
                            result,
                            architecture,
                            repository=project_name(root, config),
                            architecture_href=artifact.name,
                            observation=observation,
                        )
                    if clock is not None:
                        clock.count(
                            WorkCounter.REPORT_PAGE_BYTES, sum(len(payload) for _, payload in pages)
                        )
                    _write_pages(artifact, pages, artifacts)
                if clock is not None and args.timings is not None and result.exit_code == 0:
                    _write_timings(args.timings, clock)
                    artifacts.append(args.timings)
            elif command is Command.VALIDATE:
                config = load_config(root, args.config)
                if args.write_baseline and args.baseline is None:
                    parser.error("--write-baseline needs --baseline to name the file to write")
                if args.accept_new and not args.write_baseline:
                    parser.error("--accept-new needs --write-baseline")
                if args.amendment is not None and args.against is None:
                    parser.error("--amendment needs --against to name the compared revision")
                if args.write_amendment and args.against is None:
                    parser.error("--write-amendment needs --against to name the compared revision")
                if args.write_amendment and args.amendment is None:
                    parser.error("--write-amendment needs --amendment to name the file to write")
                if args.write_amendment and (not args.decided_by or not args.rationale):
                    parser.error("--write-amendment needs --decided-by and --rationale")
                against = args.against
                against_config = None
                if against is not None:
                    try:
                        against = resolve_commit(root, against)
                    except RuntimeError:
                        # Keep the existing `against.invalid` diagnostic for an unknown ref.
                        pass
                    else:
                        try:
                            against_config = parse_config(
                                read_blob(root, against, args.config), args.config
                            )
                        except ValueError:
                            # Missing or invalid historical config cannot authorize a rename.
                            against_config = None
                observer = configured_observer(config, observer_for)
                result, requested_files = run_validate(
                    root,
                    config,
                    observer,
                    write_graph=args.write_graph,
                    compact_open_decisions=args.compact_open_decisions,
                    # AD-103: run_validate reads both relative to --root, like the contract.
                    baseline=args.baseline,
                    write_baseline=args.write_baseline,
                    accept_new=args.accept_new,
                    against=against,
                    against_config=against_config,
                    amendment=args.amendment,
                    write_amendment=args.write_amendment,
                    decided_by=args.decided_by,
                    rationale=args.rationale,
                )
                files = requested_files.entries
                notes = config.scope_notes(observer.excluded_for(), against_config, against)
                result = replace(result, scan_roots=config.roots, notes=(*result.notes, *notes))
            else:
                config = load_check_config(root, args.baseline, args.head)
                subject = "check inputs"
                core = NativeCore.requested(args.native_core, os.environ)
                observer = configured_observer(config, core.observer(observer_for))
                result = run_check(
                    root,
                    config=config,
                    baseline=args.baseline,
                    expectation_commit=args.expectation_commit,
                    head=args.head,
                    expected_path=args.expected,
                    expected_digest=args.expected_digest,
                    branch=args.branch,
                    accepted_branch=args.accepted_branch,
                    host_records_path=args.host_records,
                    environ=os.environ,
                    host=load_gitlab_records,
                    analyzer=observer,
                    rule_rows=core.binary is not None,
                )
                result = core.decide_check(result, root, config, args.baseline)
                notes = config.scope_notes(observer.excluded_for(args.head))
                result = replace(result, scan_roots=config.roots, notes=(*result.notes, *notes))
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    args.output.write_bytes(render_result(result))
                    check_html = html_path(args.output, Command.CHECK)
                    check_html.write_bytes(
                        render_check_html(
                            result,
                            repository=project_name(root, config),
                            result_href=args.output.name,
                        )
                    )
                    artifacts.extend((args.output, check_html))
            _write_files(root, files, artifacts)
            if command is Command.INIT and args.adopt and result.exit_code == 0:
                # AD-266: the baseline must describe the adopted contract on disk, so validate
                # runs only after the init files are written; the first baseline accepts all.
                adopted, adopted_files = run_validate(
                    root,
                    load_config(root, CONFIG_PATH),
                    init_analyzer,
                    baseline=Path(ADOPTED_BASELINE_PATH),
                    write_baseline=True,
                    accept_new=True,
                )
                _write_files(root, adopted_files.entries, artifacts)
                if adopted.exit_code != 0:
                    result = replace(
                        result, exit_code=adopted.exit_code, diagnostics=adopted.diagnostics
                    )
            if command is Command.INIT and result.exit_code == 0:
                # The guide reads the contract from disk, so it runs after every init file.
                # Silence the "Wrote ..." line of run_guide, so --json stays one document.
                with redirect_stdout(io.StringIO()):
                    guide_code = run_guide(root, CONFIG_PATH, None, check=False)
                if guide_code != 0:
                    raise RuntimeError(f"archkeel guide failed with exit code {guide_code}")
                artifacts.append(root / GUIDE_PATH)
    except ConfigFileMissingError as error:
        result = (
            invalid_result(subject, error)
            if command is Command.VALIDATE
            else unknown_result(command, subject, error)
        )
        remedy = (
            "For a new repository, run archkeel init; otherwise restore archkeel.toml "
            "or select the existing configuration with --config PATH."
            if configuration_source(args.config, CONFIG_PATH) is ConfigurationSource.DEFAULT
            else "Restore the selected configuration or correct --config PATH and retry."
        )
        result = replace(
            result, diagnostics=tuple(replace(item, remedy=remedy) for item in result.diagnostics)
        )
    # The CLI contract is a JSON result with exit 2, never a bare traceback, for any failure.
    except Exception as error:
        result = (
            invalid_result(subject, error)
            if command is Command.VALIDATE
            # AD-285: explore writes a report result, so its failure is one too.
            else unknown_result(
                Command.REPORT if command is Command.EXPLORE else command, subject, error
            )
        )
    return show_result(result, command, interactive, artifacts)
