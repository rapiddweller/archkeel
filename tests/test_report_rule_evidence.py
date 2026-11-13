# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Issue #159/#160 report acceptance.

Rule status needs evaluation evidence: a violation beats undecided evidence, while a clean
fully evaluated rule can pass. `allowed_dependency` is a permission declaration, not a check
and not an UNKNOWN measurement. Browser acceptance must verify computed fail color and a
non-color status cue, plus the evidence attached to the correct rule row; HTML/CSS source
matching is not visual or accessibility proof.
"""

import json
from pathlib import Path

from test_baseline import GETATTR_RULE
from test_html_report import _start_tags
from test_report_filter import CONFIG, _tour_root

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.baseline import (
    KnownViolation,
    ViolationFingerprint,
    compare_violations,
)
from archkeel.ir.codec import (
    decode_canonical_model,
    parse_observation,
)
from archkeel.render.html import render_architecture_details, render_architecture_html


def _flow_data(page: str):
    start = page.index(">", page.index('id="flow-data"')) + 1
    return json.loads(page[start : page.index("</script>", start)])


def _linked_audit(page: str, directory: Path):
    atlas = _flow_data(page)["atlas"]
    href = atlas["architecture_href"]
    assert Path(href).name == href
    assert href in {link.get("href") for link in _start_tags(page, "a")}
    model = parse_observation(decode_canonical_model(json.loads((directory / href).read_bytes())))
    assert model.source.source_digest == atlas["source"]["source_digest"]
    assert model.source.git_head == atlas["source"]["git_head"]
    return model


def _report(
    tmp_path: Path,
    *,
    only_violations: bool = False,
    mixed_evidence: bool = False,
    opaque_provider: bool = False,
):
    root = _tour_root(tmp_path)
    if opaque_provider:
        provider = root / "shop/model/entities.py"
        provider.write_text(
            provider.read_text() + "\ndef opaque_probe():\n    return eval('Order')\n"
        )
    if mixed_evidence:
        (root / "shop/app/mixed.py").write_text(
            "def mixed(payload: dict, stamp: 'Missing') -> str:\n    return ''\n"
        )
        contract_path = root / CONFIG.contract
        contract = json.loads(contract_path.read_bytes())
        app = next(item for item in contract["components"] if item["id"] == "COMP-APP")
        app["public"].append("shop.app.mixed:mixed")
        contract_path.write_text(json.dumps(contract))
    result, architecture = run_report(
        root, config=CONFIG, analyzer=observe, only_violations=only_violations
    )
    assert architecture is not None
    (tmp_path / "architecture.json").write_bytes(architecture)
    for name, content in render_architecture_details(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).items():
        (tmp_path / name).write_bytes(content)
    observation = parse_observation(decode_canonical_model(json.loads(architecture)))
    page = render_architecture_html(
        result, architecture, repository="shop", architecture_href="architecture.json"
    ).decode()
    return result, observation, page


def test_same_fingerprint_growth_is_one_counted_finding_not_an_exact_line_claim() -> None:
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",))
    known = (KnownViolation(fingerprint, 1),)
    observed = (KnownViolation(fingerprint, 2),)

    assert compare_violations(known, observed, cycle_rules=frozenset()) == (
        f"new violation: {GETATTR_RULE} | shop.model.probe.read (2 observed, 1 in the baseline)",
    )


def test_one_fingerprint_shrink_reports_one_resolved_finding() -> None:
    fingerprint = ViolationFingerprint((GETATTR_RULE,), ("shop.model.probe.read",))

    assert compare_violations(
        (KnownViolation(fingerprint, 2),),
        (KnownViolation(fingerprint, 1),),
        cycle_rules=frozenset(),
    ) == (
        f"resolved violation: {GETATTR_RULE} | shop.model.probe.read "
        "(1 observed, 2 in the baseline); rewrite the baseline with --write-baseline",
    )
