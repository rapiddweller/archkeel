# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The shapes of the scaling matrix whose reply is quadratic by the data model (AD-340)."""

from __future__ import annotations

# The shapes whose reply is quadratic in the size of the file, by the data model of the Python
# collector and not by a loop of the native one: a nest of named definitions puts the qualified
# name of each definition (as long as the depth) into every record of everything inside it, and a
# chain of members puts the text of the receiver into each reference. The CPU time of the
# collector on such a shape is the size of its reply, so the matrix times the walk alone for them
# (`--dump-count`, test only), which counts what the walk found and writes none of these names.
WALK_ONLY = frozenset(
    {
        "member-chain",
        "nested-classes",
        "nested-functions",
        "sites-calls-at-depth",
        "sites-chained-calls",
        "sites-computed-calls",
        "sites-script-wrapper-nest",
        "sites-timed-calls",
        "sites-timed-chains",
        "sites-timed-computed",
        "sites-timed-scripts",
        "writes-at-depth",
        "writes-distinct-names",
        "writes-import-at-own-depth",
        "writes-imports-all-at-bottom",
        "writes-same-import-at-depth",
    }
)
