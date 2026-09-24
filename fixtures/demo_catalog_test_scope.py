# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-101 test scope demos: `archkeel-tests.toml` governs the shop sample's `tests/` on its own.

Every row runs with `--config archkeel-tests.toml`; the product's `archkeel.toml` and contract
are the clean sample's, untouched, and its own rows keep passing beside this tree.
"""

from __future__ import annotations

from fixtures.demo_catalog_support import FIXTURE_DIR, HEADER, Variant

TEST_CONFIG = "archkeel-tests.toml"
_BUILDER = (FIXTURE_DIR / "tests/support/orders.py").read_text()
_UNIT_TEST = (FIXTURE_DIR / "tests/unit/test_entities.py").read_text()
_INTEGRATION_TEST = (FIXTURE_DIR / "tests/integration/test_place_order.py").read_text()


def _builder_moved_to(module: str, path: str) -> dict[str, str | None]:
    """The shared order builder moved out of `tests.support`, with both of its importers."""
    return {
        "tests/support/orders.py": None,
        path: _BUILDER,
        "tests/unit/test_entities.py": _UNIT_TEST.replace("tests.support.orders", module),
        "tests/integration/test_place_order.py": _INTEGRATION_TEST.replace(
            "tests.support.orders", module
        ),
    }


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="test-scope-clean",
        section="clean",
        item="test_scope:clean",
        summary="A second configuration scans tests/ against its own contract, and it passes.",
        files={},
        expected_violations=(),
        expected_codes=(),
        config=TEST_CONFIG,
    ),
    Variant(
        id="test-scope-helper-in-unit",
        section="class_a",
        item="symbol_placement:test-helper-outside-support",
        summary=(
            "The shared order builder moved into tests/unit: it is defined outside support, "
            "and the integration test that follows it now imports the unit suite."
        ),
        files=_builder_moved_to("tests.unit.orders", "tests/unit/orders.py"),
        expected_violations=("TESTS-HELPERS-IN-SUPPORT", "TESTS-REQUIRES-COMPLETE"),
        expected_codes=("graph.drift", "rule.violated", "rule.violated"),
        config=TEST_CONFIG,
    ),
    Variant(
        id="test-scope-helper-at-root",
        section="class_a",
        item="root_layout:test-helper-at-root",
        summary=(
            "The shared order builder moved directly below tests: no suite owns it, and it "
            "is outside both the allowed layout and support."
        ),
        files=_builder_moved_to("tests.orders", "tests/orders.py"),
        expected_violations=(
            "TESTS-ASSIGNMENT-COMPLETE",
            "TESTS-HELPERS-IN-SUPPORT",
            "TESTS-ROOT-LAYOUT",
        ),
        expected_codes=("graph.drift", "rule.violated", "rule.violated", "rule.violated"),
        config=TEST_CONFIG,
    ),
    Variant(
        id="test-scope-suite-crossing",
        section="class_a",
        item="complete_requires:test-suite-crossing",
        summary="A unit test imports an integration test, a suite pair no requires entry allows.",
        files={
            "tests/unit/test_entities.py": HEADER
            + '"""Order arithmetic without persistence."""\n\n'
            "from __future__ import annotations\n\n"
            "from tests.integration.test_place_order import test_placed_order_round_trips\n"
            "from tests.support.orders import OrderBuilder\n\n"
            '__all__ = ["test_placed_order_round_trips"]\n\n\n'
            "def test_order_total_multiplies_quantity() -> None:\n"
            '    order = OrderBuilder().with_line("pen", 3, 150)\n'
            "    assert order.total().cents == 450\n"
        },
        expected_violations=("TESTS-REQUIRES-COMPLETE",),
        expected_codes=("graph.drift", "rule.violated"),
        config=TEST_CONFIG,
    ),
)
