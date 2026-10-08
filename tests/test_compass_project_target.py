# ArchKeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only checks for the independently authored Compass Target."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.target_graph import declared_tree_graph

FIXTURE = Path(__file__).parents[1] / "fixtures" / "J-compass"
PROVENANCE = ("docs/target.md",)
CONTRACTS = (
    "architecture-contract.json",
    "contracts/application.json",
    "contracts/presentation.json",
    "contracts/domain.json",
    "contracts/data.json",
    "contracts/utilities.json",
)


def _target():
    payload = (FIXTURE / CONTRACTS[0]).read_bytes()
    contract = parse_contract(json.loads(payload))

    def read(relative: str) -> tuple[bytes, str]:
        return (FIXTURE / relative).read_bytes(), relative

    tree = load_inside_contract_tree(
        CONTRACTS[0], contract, hashlib.sha256(payload).hexdigest(), CONTRACTS[0], read
    )
    graph = declared_tree_graph(tree, root_path=CONTRACTS[0])
    graph.validate()
    return tree, graph


def test_compass_target_covers_every_library_and_part_once() -> None:
    _, graph = _target()
    source = FIXTURE / "lib"
    dart_inputs = {path.relative_to(FIXTURE).as_posix() for path in source.rglob("*.dart")}
    modules = {entity.file_path for entity in graph.entities if entity.kind == "module"}
    assert len(dart_inputs) == 111
    assert len(modules) == 89
    assert len(dart_inputs - modules) == 22
    assert all(path in dart_inputs for path in modules)
    assert all(not path.endswith((".freezed.dart", ".g.dart")) for path in modules)
    assert modules == {
        path.relative_to(FIXTURE).as_posix()
        for path in source.rglob("*.dart")
        if not path.name.endswith((".freezed.dart", ".g.dart"))
    }
    declared = []
    for relative in CONTRACTS:
        payload = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        declared.extend(
            module
            for component in payload["components"]
            for module in component.get("exact_modules", [])
        )
    assert len(declared) == 89
    assert len(set(declared)) == 89
    assert set(declared) == {
        entity.qualified_name for entity in graph.entities if entity.kind == "module"
    }
    for part in dart_inputs - modules:
        if part.endswith((".freezed.dart", ".g.dart")):
            parent = part.removesuffix(".freezed.dart").removesuffix(".g.dart") + ".dart"
            assert parent in dart_inputs
            assert f"part '{Path(part).name}';" in (FIXTURE / parent).read_text(encoding="utf-8")


def test_compass_target_has_nested_responsibilities_and_principal_uml() -> None:
    _, graph = _target()
    assert sum(component.parent_id is not None for component in graph.component_intents) >= 20
    assert len(graph.entities) >= 400
    qualified = {entity.qualified_name for entity in graph.entities}
    assert "compass.ui.booking.view_models.booking_viewmodel.BookingViewModel" in qualified
    assert "compass.domain.models.activity.activity._$Activity.name::getter" in qualified
    assert "compass.data.services.api.api_client.ApiClient" in qualified
    assert "compass.config.dependencies.providersLocal::getter" in qualified
    assert "compass.routing.routes.Routes.bookingWithId" in qualified
    assert (
        "compass.data.repositories.auth.auth_repository.AuthRepository.isAuthenticated::getter"
        in qualified
    )
    assert (
        "compass.ui.search_form.view_models.search_form_viewmodel.SearchFormViewModel.selectedContinent::setter"
        in qualified
    )
    assert (
        "compass.domain.use_cases.booking.booking_create_use_case.BookingCreateUseCase.createFrom"
        in qualified
    )
    assert "compass.utils.command.Command._execute" in qualified
    assert len([edge for edge in graph.relationships if edge.kind == "mixes_in"]) == 11
    assert len([edge for edge in graph.relationships if edge.kind == "realizes"]) == 11
    assert len([edge for edge in graph.relationships if edge.kind == "inherits"]) == 6
    entity_by_id = {entity.id: entity for entity in graph.entities}
    booking_create_from = (
        "compass.domain.use_cases.booking.booking_create_use_case.BookingCreateUseCase.createFrom"
    )
    booking_call = [
        edge
        for edge in graph.relationships
        if edge.kind == "calls"
        and entity_by_id[edge.source_id].qualified_name
        == "compass.ui.booking.view_models.booking_viewmodel.BookingViewModel._createBooking"
        and entity_by_id[edge.target_id].qualified_name == booking_create_from
    ]
    assert len(booking_call) == 1
    assert any(
        entity.kind == "symbol"
        and entity.presence == "referenced"
        and entity.qualified_name == booking_create_from
        for entity in graph.entities
    )
    scopes = {scope.scope_id: scope.mode for scope in graph.target_scopes}
    mixins = [entity for entity in graph.entities if entity.kind == "mixin"]
    assert len(mixins) == 11
    assert all(scopes[mixin.id] == "closed" for mixin in mixins)
    closed = {scope_id for scope_id, mode in scopes.items() if mode == "closed"}
    assert all(
        entity.annotation is not None
        for entity in graph.entities
        if entity.kind == "attribute" and entity.parent_id in closed
    )
    assert all(
        entity.signature is not None
        for entity in graph.entities
        if entity.kind == "method" and entity.parent_id in closed
    )
    assert all(
        any(entity.qualified_name == mixin.qualified_name + ".toJson" for entity in graph.entities)
        and any(
            entity.qualified_name == mixin.qualified_name + ".copyWith::getter"
            for entity in graph.entities
        )
        for mixin in mixins
    )
    for name in (
        "ActivityRepository",
        "AuthRepository",
        "BookingRepository",
        "ContinentRepository",
        "DestinationRepository",
        "ItineraryConfigRepository",
        "UserRepository",
    ):
        assert any(entity.qualified_name.endswith("." + name) for entity in graph.entities)


def test_compass_application_target_separates_composition_and_navigation() -> None:
    root = json.loads((FIXTURE / CONTRACTS[0]).read_text(encoding="utf-8"))
    app = json.loads((FIXTURE / "contracts/application.json").read_text(encoding="utf-8"))
    application = next(
        component for component in root["components"] if component["id"] == "application"
    )
    assert application["inside"] == "contracts/application.json"
    app_modules = {
        component["id"]: set(component["exact_modules"]) for component in app["components"]
    }
    assert app_modules == {
        "application-composition": {
            "compass.config.assets",
            "compass.config.dependencies",
            "compass.main",
            "compass.main_development",
            "compass.main_staging",
        },
        "application-navigation": {
            "compass.routing.router",
            "compass.routing.routes",
        },
    }


def test_compass_target_is_source_authored_and_hash_receipt_is_current() -> None:
    for relative in CONTRACTS:
        payload = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        assert payload["components"]
        assert all(
            component["responsibilities"]
            and component["provenance"] == list(PROVENANCE)
            and component["decided_by"] == "agent"
            for component in payload["components"]
        )
        assert [rule["kind"] for rule in payload["rules"]] == ["complete_requires"]
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_text(encoding="utf-8"))
    assert snapshot["commit"] == "5541c59ab8e9d7e74c1a35ef22bd43a487fc596c"
    target_hash = hashlib.sha256(
        b"".join((FIXTURE / relative).read_bytes() for relative in CONTRACTS)
    ).hexdigest()
    receipt = (FIXTURE / "docs" / "target.md").read_text(encoding="utf-8")
    assert f"Target bundle SHA-256: `{target_hash}`" in receipt
