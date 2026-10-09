# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only variants for the pinned, whole-project Compass Target."""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.model import stable_id
from fixtures.demo_catalog_support import Variant

COMPASS_FIXTURE_DIR = Path(__file__).resolve().parent / "J-compass"
_USE_CASE = "lib/domain/use_cases/booking/booking_create_use_case.dart"
_BOOKING_VIEW_MODEL = "lib/ui/booking/view_models/booking_viewmodel.dart"


def _replace(relative: str, old: str, new: str) -> str:
    source = (COMPASS_FIXTURE_DIR / relative).read_text()
    if source.count(old) != 1:
        raise ValueError(f"{relative}: expected one mutation anchor {old!r}")
    return source.replace(old, new, 1)


_UML_RULE = stable_id("UML-TARGET", "architecture-contract.json")


def _local_data_service_with_api_call() -> str:
    relative = "lib/data/services/local/local_data_service.dart"
    source = (COMPASS_FIXTURE_DIR / relative).read_text()
    for old, new in (
        (
            "import 'package:flutter/services.dart';",
            "import 'package:flutter/services.dart';\n\nimport '../api/api_client.dart';",
        ),
        (
            "  Future<List<Destination>> getDestinations() async {\n"
            "    final json = await _loadStringAsset(Assets.destinations);",
            "  Future<List<Destination>> getDestinations() async {\n"
            "    ApiClient().getDestinations();\n"
            "    final json = await _loadStringAsset(Assets.destinations);",
        ),
    ):
        if source.count(old) != 1:
            raise ValueError(f"{relative}: expected one mutation anchor {old!r}")
        source = source.replace(old, new, 1)
    return source


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="compass-project",
        section="clean",
        item="compass:project",
        summary="The complete pinned Compass application: routing, session/auth, repositories, "
        "booking, persistence, API services and generated model APIs are compared with an "
        "independently authored whole-project Target.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=COMPASS_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="compass-forbidden-edge",
        section="class_a",
        item="compass:forbidden_edge",
        summary="Make the local asset service call the HTTP API client. That cross-component "
        "dependency is not permitted by the nested data Target.",
        files={
            "lib/data/services/local/local_data_service.dart": _local_data_service_with_api_call()
        },
        expected_violations=("REQUIRES-COMPLETE",),
        expected_codes=("graph.drift", "rule.violated"),
        fixture=COMPASS_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="compass-signature-fail",
        section="class_a",
        item="compass:signature",
        summary="Widen BookingCreateUseCase.createFrom's result from Booking to Object. The "
        "source declaration remains analyzable, while the closed API contract no longer matches.",
        files={
            _USE_CASE: _replace(
                _USE_CASE,
                "Future<Result<Booking>> createFrom(ItineraryConfig itineraryConfig)",
                "Future<Result<Object>> createFrom(ItineraryConfig itineraryConfig)",
            )
        },
        expected_violations=(_UML_RULE,),
        expected_codes=("rule.violated",),
        fixture=COMPASS_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="compass-dynamic-unknown",
        section="class_a",
        item="compass:dynamic_receiver",
        summary="Keep BookingViewModel._createBooking and its createFrom call, but make the "
        "receiver's declared type dynamic. The same Target call can no longer be proven.",
        files={
            _BOOKING_VIEW_MODEL: _replace(
                _BOOKING_VIEW_MODEL,
                "final BookingCreateUseCase _createUseCase;",
                "final dynamic _createUseCase;",
            )
        },
        expected_violations=(),
        expected_codes=(),
        fixture=COMPASS_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
)
