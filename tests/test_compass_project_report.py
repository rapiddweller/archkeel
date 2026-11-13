# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The full Compass proof replays source-only variants through the native report path."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import re
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import pytest

from archkeel.ir.graph_codec import parse_report
from fixtures.architecture_demo import REPORT_CASES, replay
from fixtures.demo_catalog_compass import COMPASS_FIXTURE_DIR, VARIANTS

SOURCE_DIGEST = "c6c1b8fe62fbc950af3b3dc4a033cac300bdeec2564e563909504a69df753e72"
TARGET_DIGEST = "4f6fb239818ff66ae963ce5a4ffe43d319b6d21cbeaf76d262d9cbf670a33a67"
EXPECTED_ASSESSMENTS = {
    "compass-project": Counter(PASS=1749, UNKNOWN=23),
    "compass-forbidden-edge": Counter(PASS=1749, UNKNOWN=23),
    "compass-signature-fail": Counter(PASS=1748, UNKNOWN=23, FAIL=1),
    "compass-dynamic-unknown": Counter(PASS=1747, UNKNOWN=24, FAIL=1),
}


def _payload(html: Path) -> dict:
    match = re.search(
        r'<script[^>]*id="flow-data"[^>]*>(.*?)</script>',
        html.read_text(encoding="utf-8"),
        re.DOTALL,
    )
    assert match
    return json.loads(match.group(1))


def _report(output: Path):
    main = output.with_suffix(".report.html")
    atlas = _payload(main)["atlas"]
    detail = main.with_name(atlas["detail_page"])
    data = _payload(detail)
    assert data["navigation"]["main_href"] == main.name
    return parse_report(
        {
            key: value
            for key, value in data.items()
            if key not in {"initial_scope", "initial_view", "navigation", "boundary_permissions"}
        }
    )


def _assert_named_factory_identities(report) -> None:
    factories = [
        entity
        for entity in report.target.entities
        if entity.kind == "method" and entity.qualified_name.endswith(".fromJson")
    ]
    assert len(factories) == 11
    for factory in factories:
        matches = [
            entity
            for entity in report.observed.entities
            if entity.kind == "method" and entity.qualified_name == factory.qualified_name
        ]
        assert len(matches) == 1
        for aspect in ("existence", "signature"):
            assessment = next(
                item
                for item in report.comparison.assessments
                if item.subject_id == factory.id and item.aspect == aspect
            )
            assert assessment.status == "PASS"


def test_compass_variants_are_source_only_and_keep_the_full_snapshot() -> None:
    assert {variant.id for variant in VARIANTS} == {
        "compass-project",
        "compass-forbidden-edge",
        "compass-signature-fail",
        "compass-dynamic-unknown",
    }
    selected = {
        path.relative_to(COMPASS_FIXTURE_DIR).as_posix()
        for path in COMPASS_FIXTURE_DIR.rglob("*.dart")
    }
    assert len(selected) == 111
    target_paths = (
        "architecture-contract.json",
        "contracts/application.json",
        "contracts/presentation.json",
        "contracts/domain.json",
        "contracts/data.json",
        "contracts/utilities.json",
    )
    target_digest = hashlib.sha256(
        b"".join((COMPASS_FIXTURE_DIR / path).read_bytes() for path in target_paths)
    ).hexdigest()
    assert target_digest == TARGET_DIGEST
    for variant in VARIANTS:
        assert variant.fixture == COMPASS_FIXTURE_DIR
        assert all(path in selected for path in variant.files)
        assert all(path.startswith("lib/") and path.endswith(".dart") for path in variant.files)


def test_compass_forbidden_edge_is_inside_the_data_component_contract() -> None:
    variant = next(row for row in VARIANTS if row.id == "compass-forbidden-edge")
    service_path = "lib/data/services/local/local_data_service.dart"
    assert set(variant.files) == {service_path}
    changed = variant.files[service_path]
    assert "import '../api/api_client.dart';" in changed
    assert "ApiClient().getDestinations();" in changed


@pytest.fixture(scope="module")
def replayed(tmp_path_factory: pytest.TempPathFactory) -> Callable[[str], tuple[Path, str]]:
    """Each replay takes over a minute: the tests of this file share one replay for a variant."""
    cache: dict[str, tuple[Path, str]] = {}

    def replay_once(variant_id: str) -> tuple[Path, str]:
        if variant_id not in cache:
            output = tmp_path_factory.mktemp(variant_id) / f"{variant_id}.json"
            summary = io.StringIO()
            with contextlib.redirect_stdout(summary):
                registered_case = REPORT_CASES[f"uml-{variant_id}"]
                assert registered_case == (variant_id, 2)
                assert replay(variant_id, output) == registered_case[1]
            cache[variant_id] = (output, summary.getvalue())
        return cache[variant_id]

    return replay_once


PACKAGE_CYCLE = "Package cycle with 23 members, roll-up only: no module cycle crosses them"
