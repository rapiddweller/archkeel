# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only checks for the independently authored Python RealWorld Target."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.model import component_owns_module, requires_covers
from archkeel.ir.target_graph import declared_tree_graph

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "K-python-realworld"
CONTRACTS = (
    "architecture-contract.json",
    "contracts/host-runtime.json",
    "contracts/http-interface.json",
    "contracts/product-policy.json",
    "contracts/product-contracts.json",
    "contracts/postgres-adapter.json",
)
PROVENANCE = ("docs/target.md",)


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


def test_python_realworld_target_owns_all_72_pinned_app_modules_once() -> None:
    tree, graph = _target()
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_bytes())
    selected = {item["path"] for item in snapshot["files"] if item["path"].startswith("app/")}
    python = {path for path in selected if path.endswith(".py")}
    modules = {
        entity.file_path
        for entity in graph.entities
        if entity.kind == "module" and entity.file_path
    }
    assert len(selected) == 79
    assert len(python) == 72
    assert modules == python
    assert len([item for item in tree.root.components]) == 5

    mounts = {mount.parent.id: mount.contract for mount in tree.mounts}
    for module in (entity for entity in graph.entities if entity.kind == "module"):
        root_owners = [
            component
            for component in tree.root.components
            if component_owns_module(component, module.qualified_name)
        ]
        assert len(root_owners) == 1, module.qualified_name
        root_owner = root_owners[0]
        assert (
            root_owner.namespace is None
            or module.qualified_name.startswith(root_owner.namespace + ".")
            or module.qualified_name == root_owner.namespace
        )
        nested = mounts[root_owner.id]
        nested_owners = [
            component
            for component in nested.components
            if component_owns_module(component, module.qualified_name)
        ]
        assert len(nested_owners) == 1, module.qualified_name
        assert module.parent_id == nested_owners[0].id
        assert (
            nested_owners[0].namespace is None
            or module.qualified_name.startswith(nested_owners[0].namespace + ".")
            or module.qualified_name == nested_owners[0].namespace
        )


def test_python_realworld_target_links_principal_module_flows_without_closing_imports() -> None:
    _, graph = _target()
    modules = {entity.id: entity.file_path for entity in graph.entities if entity.kind == "module"}
    module_ids = set(modules)
    imports = {
        (modules[relationship.source_id], modules[relationship.target_id])
        for relationship in graph.relationships
        if relationship.kind == "imports"
        and relationship.source_id in module_ids
        and relationship.target_id in module_ids
    }
    import_relationships = [
        relationship for relationship in graph.relationships if relationship.kind == "imports"
    ]
    assert all(
        relationship.reason.startswith("Selected source import at ")
        and relationship.provenance == PROVENANCE
        for relationship in import_relationships
    )
    assert {
        ("app/main.py", "app/api/routes/api.py"),
        ("app/main.py", "app/core/config.py"),
        ("app/core/config.py", "app/core/settings/development.py"),
        ("app/core/events.py", "app/db/events.py"),
        ("app/db/migrations/env.py", "app/core/config.py"),
        ("app/api/routes/api.py", "app/api/routes/authentication.py"),
        ("app/api/routes/authentication.py", "app/db/repositories/users.py"),
        ("app/services/authentication.py", "app/db/repositories/users.py"),
        ("app/db/repositories/users.py", "app/db/queries/queries.py"),
        ("app/models/domain/users.py", "app/services/security.py"),
        ("app/models/schemas/articles.py", "app/models/schemas/rwschema.py"),
        (
            "app/api/routes/articles/articles_resource.py",
            "app/db/repositories/articles.py",
        ),
        ("app/api/routes/comments.py", "app/db/repositories/comments.py"),
        ("app/api/routes/profiles.py", "app/db/repositories/profiles.py"),
        ("app/api/routes/tags.py", "app/db/repositories/tags.py"),
    } <= imports
    assert all(
        relationship.source_id in module_ids and relationship.target_id in module_ids
        for relationship in graph.relationships
        if relationship.kind == "imports"
    )
    assert all(
        scope.mode == "open"
        for scope in graph.target_scopes
        if scope.scope_id in module_ids and "imports" in scope.relationship_kinds
    )


def test_python_realworld_target_preserves_layered_import_boundaries() -> None:
    tree, _ = _target()
    roots = {component.id: component for component in tree.root.components}
    assert requires_covers(
        roots["http-interface"],
        "PostgreSQL persistence adapter",
        "app.db.repositories.articles",
    )
    assert requires_covers(
        roots["product-contracts"],
        "Product policy and identity services",
        "app.services.security",
    )
    assert not requires_covers(
        roots["http-interface"], "PostgreSQL persistence adapter", "app.db.queries.queries"
    )


def test_python_realworld_target_closes_principal_login_contract_and_call() -> None:
    _, graph = _target()
    entities = {(entity.kind, entity.qualified_name): entity for entity in graph.entities}
    login = entities[("function", "app.api.routes.authentication.login")]
    jwt = entities[("function", "app.services.jwt.create_access_token_for_user")]
    assert [
        (parameter.name, parameter.kind, parameter.annotation, parameter.default)
        for parameter in login.signature.parameters
    ] == [
        ("user_login", "positional", "UserInLogin", "Body(..., embed=True, alias='user')"),
        (
            "users_repo",
            "positional",
            "UsersRepository",
            "Depends(get_repository(UsersRepository))",
        ),
        ("settings", "positional", "AppSettings", "Depends(get_app_settings)"),
    ]
    assert login.signature.returns == "UserInResponse"
    assert jwt.signature.parameters[0].name == "user"
    assert jwt.signature.parameters[0].annotation == "User"
    assert jwt.signature.parameters[1].name == "secret_key"
    assert jwt.signature.parameters[1].annotation == "str"
    assert jwt.signature.returns == "str"
    assert any(
        relationship.kind == "calls"
        and relationship.source_id == login.id
        and relationship.target_id == jwt.id
        for relationship in graph.relationships
    )
    assert ("class", "app.models.domain.articles.Article") in entities
    assert ("class", "app.db.repositories.articles.ArticlesRepository") in entities
    assert ("symbol", "fastapi.security.APIKeyHeader") in entities
    article_tags = entities[("attribute", "app.models.domain.articles.Article.tags")]
    create_article = entities[
        ("method", "app.db.repositories.articles.ArticlesRepository.create_article")
    ]
    password_check = entities[("method", "app.models.domain.users.UserInDB.check_password")]
    assert article_tags.annotation == "List[str]"
    assert [
        (parameter.name, parameter.kind, parameter.annotation, parameter.default)
        for parameter in create_article.signature.parameters
    ] == [
        ("self", "positional", None, None),
        ("slug", "keyword_only", "str", None),
        ("title", "keyword_only", "str", None),
        ("description", "keyword_only", "str", None),
        ("body", "keyword_only", "str", None),
        ("author", "keyword_only", "User", None),
        ("tags", "keyword_only", "Optional[Sequence[str]]", "None"),
    ]
    assert "async" in create_article.modifiers
    assert password_check.signature.parameters[0].name == "self"
    assert password_check.signature.returns == "bool"
    assert ("class", "app.models.schemas.articles.ArticleForResponse") in entities
    assert ("class", "app.models.domain.rwmodel.RWModel.Config") in entities
    article = entities[("class", "app.models.domain.articles.Article")]
    article_scope = next(scope for scope in graph.target_scopes if scope.scope_id == article.id)
    assert article_scope.mode == "closed"
    assert article_scope.entity_kinds == ("attribute",)
    user_in_db = entities[("class", "app.models.domain.users.UserInDB")]
    user_scope = next(scope for scope in graph.target_scopes if scope.scope_id == user_in_db.id)
    assert {"attribute", "method"}.issubset(user_scope.entity_kinds)


def test_python_realworld_target_includes_every_realworld_route_family() -> None:
    _, graph = _target()
    functions = {entity.qualified_name for entity in graph.entities if entity.kind == "function"}
    assert {
        "app.api.routes.authentication.login",
        "app.api.routes.authentication.register",
        "app.api.routes.users.retrieve_current_user",
        "app.api.routes.users.update_current_user",
        "app.api.routes.profiles.retrieve_profile_by_username",
        "app.api.routes.profiles.follow_for_user",
        "app.api.routes.profiles.unsubscribe_from_user",
        "app.api.routes.articles.articles_resource.list_articles",
        "app.api.routes.articles.articles_common.get_articles_for_user_feed",
        "app.api.routes.articles.articles_resource.create_new_article",
        "app.api.routes.articles.articles_resource.retrieve_article_by_slug",
        "app.api.routes.articles.articles_resource.update_article_by_slug",
        "app.api.routes.articles.articles_resource.delete_article_by_slug",
        "app.api.routes.articles.articles_common.mark_article_as_favorite",
        "app.api.routes.articles.articles_common.remove_article_from_favorites",
        "app.api.routes.comments.list_comments_for_article",
        "app.api.routes.comments.create_comment_for_article",
        "app.api.routes.comments.delete_comment_from_article",
        "app.api.routes.tags.get_all_tags",
    } <= functions


def test_python_realworld_target_hash_and_scope_are_current() -> None:
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
    assert snapshot["commit"] == "029eb7781c60d5f563ee8990a0cbfb79b244538c"
    target_hash = hashlib.sha256(
        b"".join((FIXTURE / relative).read_bytes() for relative in CONTRACTS)
    ).hexdigest()
    receipt = (FIXTURE / "docs" / "target.md").read_text(encoding="utf-8")
    assert f"Target bundle SHA-256: `{target_hash}`" in receipt

    config = tomllib.loads((FIXTURE / "archkeel.toml").read_text(encoding="utf-8"))
    assert config["scan"] == {
        "language": "python",
        "roots": ["app"],
        "namespace": "app",
        "contract": "architecture-contract.json",
    }
