# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Reject Mermaid node labels GitHub's renderer parses differently than intended.

CI (see .github/workflows/ci.yml, job `mermaid`) additionally renders every block
extracted by tools/mermaid_blocks.py with the official mermaid-cli; that catches
anything this text-level check does not (unknown shapes, undeclared node ids, ...).
"""

from __future__ import annotations

import re

from tools.mermaid_blocks import blocks

# An edge label ("-->|text|") is not a node label, so it is removed before shapes are scanned.
_EDGE_LABEL = re.compile(r"[-=.]{1,3}>?\|[^|]*\|")
_NODE_LABELS = (
    re.compile(r"[A-Za-z0-9_-]+\[(.*?)\]"),
    re.compile(r"[A-Za-z0-9_-]+\((.*?)\)"),
    re.compile(r"[A-Za-z0-9_-]+\{(.*?)\}"),
)
_FORBIDDEN_CHARS = "|;"
_BRACKET_PAIRS = ("[]", "()", "{}")


def unsafe_node_labels(line: str) -> list[str]:
    """Return unquoted node label texts on `line` that break Mermaid's parser.

    A label quoted with `"..."` may contain anything; Mermaid treats it as a string.
    An unquoted label must not contain `|` or `;`, and its brackets/parens/braces must
    balance, since those characters otherwise close or reopen a node shape.
    """
    stripped = _EDGE_LABEL.sub("", line)
    unsafe = []
    for pattern in _NODE_LABELS:
        for match in pattern.finditer(stripped):
            text = match.group(1).strip()
            if text.startswith('"') and text.endswith('"') and len(text) >= 2:
                continue
            if any(char in text for char in _FORBIDDEN_CHARS) or any(
                text.count(open_char) != text.count(close_char)
                for open_char, close_char in _BRACKET_PAIRS
            ):
                unsafe.append(text)
    return unsafe


def test_unsafe_node_labels_examples() -> None:
    # The line that broke GitHub's renderer: an unquoted node label containing "|".
    broken = "A[Install skill: archkeel skill install claude|codex] --> B[archkeel init --json]"
    assert unsafe_node_labels(broken) == ["Install skill: archkeel skill install claude|codex"]

    # The fix: quoting the same text makes it a Mermaid string, "|" included.
    fixed = 'A["Install skill: archkeel skill install claude|codex"] --> B[archkeel init --json]'
    assert unsafe_node_labels(fixed) == []

    # "-->|text|" is a valid edge label, not a node label; it must not be flagged.
    edge_label = "C -->|diagnostics| D[Replace one TODO rationale]"
    assert unsafe_node_labels(edge_label) == []

    # Balanced brackets pass here; whether Mermaid accepts them is left to the CI render.
    assert unsafe_node_labels("A[foo(bar)] --> B[baz]") == []

    # Unmatched "[" inside an unquoted label.
    assert unsafe_node_labels("A[foo[bar] --> B[baz]") == ["foo[bar"]

    # ";" inside an unquoted label.
    assert unsafe_node_labels("A[foo;bar]") == ["foo;bar"]


def test_every_flowchart_and_graph_block_quotes_special_node_labels() -> None:
    failures = []
    seen_paths = set()
    for path, start_line, text in blocks():
        seen_paths.add(path)
        first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if not first_line.lower().startswith(("flowchart", "graph")):
            continue
        for offset, line in enumerate(text.splitlines(), start=1):
            for label in unsafe_node_labels(line):
                failures.append(f"{path}:{start_line + offset}: {label}")
    assert failures == []
    # Sanity check: the extraction actually found the file this check exists for.
    assert "docs/onboarding.md" in seen_paths
