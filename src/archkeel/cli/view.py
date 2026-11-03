# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Check a view spec (AD-284) and draw the checked result in the Explorer (AD-287)."""

import os
import sys
from pathlib import Path
from typing import Final

from ..check.report import read_saved_snapshot, run_saved_report
from ..ir.codec import decode_json
from ..ir.view_spec import check_view, parse_view_spec, view_check_json, view_summary
from ..render.html import render_architecture_pages

_SNAPSHOT_NAME: Final = "architecture.json"
_NOT_CHECKED: Final = 2


def _cache_directory(source_digest: str) -> Path:
    # ponytail: repeats the AD-285 explore cache rule; merge both into one helper with strand A.
    cache = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(cache) / "archkeel/view" / source_digest[:16]


def run_view(
    spec_path: Path,
    snapshot_path: Path,
    output: Path | None,
    *,
    show: bool,
    strict: bool,
    interactive: bool,
) -> int:
    """Print the check; with `show`, also write the Explorer pages of the checked snapshot."""
    spec = parse_view_spec(decode_json(spec_path.read_bytes()))
    observation = read_saved_snapshot(snapshot_path)
    result = check_view(spec, observation, strict=strict)
    text = view_check_json(result)
    page: Path | None = None
    if show and result.exit_code != _NOT_CHECKED:
        snapshot = snapshot_path.read_bytes()
        report = run_saved_report(snapshot_path)
        if report.exit_code != 0:
            reasons = "; ".join(item.unknown_claim for item in report.diagnostics)
            raise ValueError(f"the snapshot report cannot be drawn: {reasons}")
        pages = render_architecture_pages(
            report,
            snapshot,
            repository=", ".join(observation.source.scope),
            architecture_href=_SNAPSHOT_NAME,
            view_check=text,
        )
        directory = output or _cache_directory(observation.source.source_digest)
        directory.mkdir(parents=True, exist_ok=True)
        written = {name for name, _ in pages}
        # A detail page of an earlier snapshot must not stay linked beside the new report.
        for previous in directory.glob("architecture.detail*.html"):
            if previous.name not in written:
                previous.unlink()
        for name, payload in pages:
            (directory / name).write_bytes(payload)
        if (directory / _SNAPSHOT_NAME).resolve() != snapshot_path.resolve():
            (directory / _SNAPSHOT_NAME).write_bytes(snapshot)
        page = directory / f"{Path(_SNAPSHOT_NAME).stem}.report.html"
    sys.stdout.write(view_summary(result) + "\n" if interactive else text)
    if page is not None:
        sys.stderr.write(f"archkeel view show: wrote {page}\n")
    return result.exit_code
