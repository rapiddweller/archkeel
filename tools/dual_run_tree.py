# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shell side of the inside-contract tree in the dual run (AD-366, AD-379).

The core reads no file. A frame whose contract names `missing` paths asks the shell for those
inside contracts. The shell reads each one with the duties of AD-366: the path stays inside the
repository, and the identity is the resolved repository-relative path, so the core sees a link.
It sends the request again with every file read so far, until the frame names no path, a round
reads no new file, or a bound stops the loop by name. The rounds, the files and the bytes are
bounded, so a hostile tree cannot make the shell read without end. The file reader and the bounds
are the ones of the shell (`archkeel.cli.native_core`, AD-390).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from archkeel.cli.native_core import MAX_BYTES, MAX_FILES, MAX_ROUNDS, OverBudget, read_inside

__all__ = ["MAX_BYTES", "MAX_FILES", "MAX_ROUNDS", "OverBudget", "read_inside", "tree_frame"]

Frame = dict[str, Any]


def missing_paths(frame: Mapping[str, Any]) -> list[str] | None:
    """The paths that a frame asks the shell to read, or `None`."""
    contract = (frame.get("self_test") or {}).get("contract") or {}
    paths = contract.get("missing")
    return paths if isinstance(paths, list) and paths else None


def tree_frame(
    send: Callable[[Mapping[str, Any]], Frame], request: Mapping[str, Any], root: Path
) -> Frame:
    """The frame of the last round of `request`. `send` runs the core for one request."""
    sent: dict[str, dict[str, str]] = {}
    total = 0
    for _ in range(MAX_ROUNDS):
        frame = send(request)
        paths = missing_paths(frame)
        if paths is None or frame.get("error"):
            return frame
        added = False
        for path in paths:
            if path in sent:
                continue
            if len(sent) >= MAX_FILES:
                return {"error": f"the tree needs more than {MAX_FILES} inside contracts"}
            try:
                read = read_inside(root, path, MAX_BYTES - total)
            except OverBudget:
                return {"error": f"the inside contracts hold more than {MAX_BYTES} bytes"}
            if read is None:
                continue
            identity, data = read
            total += len(data)
            sent[path] = {"reference": path, "identity": identity, "hex": data.hex()}
            added = True
        if not added:
            # The frame names each path that the shell cannot read: a named gap, never a tree.
            return frame
        request = {**request, "insides": list(sent.values())}
    return {"error": f"the tree needs more than {MAX_ROUNDS} rounds"}
