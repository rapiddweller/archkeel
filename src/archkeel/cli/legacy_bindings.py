# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Imports of the existing shell engine, loaded only after command dispatch."""

from ..check.git import read_blob as read_blob
from ..check.onboarding import run_init as run_init
from ..check.report import (
    read_saved_snapshot as read_saved_snapshot,
)
from ..check.report import (
    render_result as render_result,
)
from ..check.report import (
    run_explore as run_explore,
)
from ..check.report import (
    run_report_with_observation as run_report_with_observation,
)
from ..check.report import (
    run_saved_report as run_saved_report,
)
from ..check.report import (
    unknown_result as unknown_result,
)
from ..check.run import run_check as run_check
from ..check.snapshot import resolve_commit as resolve_commit
from ..check.validation import invalid_result as invalid_result
from ..check.validation import run_validate as run_validate
from ..host.gitlab import load_gitlab_records as load_gitlab_records
from ..ir.codec import decode_json as decode_json
from ..ir.phases import (
    Phase as Phase,
)
from ..ir.phases import (
    PhaseClock as PhaseClock,
)
from ..ir.phases import (
    WorkCounter as WorkCounter,
)
from ..ir.phases import (
    measured as measured,
)
from ..ir.story import trace_flow as trace_flow
from ..ir.story import trace_json as trace_json
from ..ir.story import trace_summary as trace_summary
from ..ir.view_spec import (
    check_view as check_view,
)
from ..ir.view_spec import (
    parse_view_spec as parse_view_spec,
)
from ..ir.view_spec import (
    view_check_json as view_check_json,
)
from ..ir.view_spec import (
    view_summary as view_summary,
)
from ..render.html import (
    render_architecture_pages as render_architecture_pages,
)
from ..render.html import (
    render_check_html as render_check_html,
)
from ..render.summary import (
    check_summary as check_summary,
)
from ..render.summary import (
    init_summary as init_summary,
)
from ..render.summary import (
    report_summary as report_summary,
)
from ..render.terminal import print_result as print_result
from ..render.terminal import progress as progress
from . import build_parser as build_parser
from . import main as main
from .arguments import (
    Command as Command,
)
from .arguments import (
    ConfigurationSource as ConfigurationSource,
)
from .arguments import (
    ReportMode as ReportMode,
)
from .arguments import (
    cache_folder as cache_folder,
)
from .arguments import (
    configuration_source as configuration_source,
)
from .arguments import (
    root_digest as root_digest,
)
from .config import (
    ADOPTED_BASELINE_PATH as ADOPTED_BASELINE_PATH,
)
from .config import (
    CONFIG_PATH as CONFIG_PATH,
)
from .config import (
    ConfigFileMissingError as ConfigFileMissingError,
)
from .config import (
    load_check_config as load_check_config,
)
from .config import (
    load_config as load_config,
)
from .config import (
    parse_config as parse_config,
)
from .config import (
    project_name as project_name,
)
from .guide import GUIDE_PATH as GUIDE_PATH
from .guide import run_guide as run_guide
from .native_core import NativeCore as NativeCore
from .observe import (
    collect_cycles_less_often as collect_cycles_less_often,
)
from .observe import (
    configured_observer as configured_observer,
)
from .observe import (
    observer_for as observer_for,
)
from .skill import InstallationAgent as InstallationAgent
from .skill import install_skill as install_skill
