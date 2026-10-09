# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only validation for the independently authored Nest RealWorld Target."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.identity import module_identity
from archkeel.ir.model import component_owns_module, in_scope, requires_covers
from archkeel.ir.target_graph import declared_tree_graph

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "fixtures" / "L-nest-realworld"
CONTRACTS = (
    "architecture-contract.json",
    "contracts/runtime.json",
    "contracts/identity.json",
    "contracts/publishing.json",
    "contracts/persistence.json",
)
PROVENANCE = ("docs/target.md",)
NAMESPACE = "nestjs.realworld"


def _target():
    target_path = FIXTURE / CONTRACTS[0]
    assert target_path.is_file(), "author the Nest RealWorld Target before collecting it"
    payload = target_path.read_bytes()
    contract = parse_contract(json.loads(payload))

    def read(relative: str) -> tuple[bytes, str]:
        return (FIXTURE / relative).read_bytes(), relative

    tree = load_inside_contract_tree(
        CONTRACTS[0], contract, hashlib.sha256(payload).hexdigest(), CONTRACTS[0], read
    )
    graph = declared_tree_graph(tree, root_path=CONTRACTS[0])
    graph.validate()
    return tree, graph


def _module(path: str) -> str:
    return module_identity(NAMESPACE, path)


def _entity_index(graph):
    return {(entity.kind, entity.qualified_name): entity for entity in graph.entities}


def test_nest_target_assigns_all_41_selected_modules_once_at_each_level() -> None:
    tree, graph = _target()
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_bytes())
    selected_paths = {
        item["path"] for item in snapshot["original_src_files"] if item["build_input"]
    } | {item["path"] for item in snapshot["derived_files"]}
    modules = [entity for entity in graph.entities if entity.kind == "module"]

    assert len(selected_paths) == 41
    assert len(modules) == 41
    assert {entity.file_path for entity in modules} == selected_paths
    assert {entity.qualified_name for entity in modules} == {
        _module(path) for path in selected_paths
    }

    mounts = {mount.parent.id: mount.contract for mount in tree.mounts}
    for module in modules:
        root_owners = [
            component
            for component in tree.root.components
            if component_owns_module(component, module.qualified_name)
        ]
        assert len(root_owners) == 1, (module.qualified_name, root_owners)
        owner = root_owners[0]
        while owner.id in mounts:
            nested = mounts[owner.id]
            nested_owners = [
                component
                for component in nested.components
                if component_owns_module(component, module.qualified_name)
            ]
            assert len(nested_owners) == 1, (module.qualified_name, nested_owners)
            owner = nested_owners[0]
        assert module.parent_id == owner.id, (module.qualified_name, module.parent_id, owner.id)
        assert owner.namespace is None or in_scope(module.qualified_name, owner.namespace)

    assert {
        component.label: len(component.exact_modules) for component in tree.root.components
    } == {
        "API composition": 3,
        "Shared request infrastructure": 4,
        "Account and authentication": 10,
        "Article and comment publishing": 9,
        "Profile and follow": 4,
        "Tag catalogue": 5,
        "Persistence and schema lifecycle": 6,
    }
    for relative in CONTRACTS:
        payload = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        assert all(
            component["responsibilities"]
            and component["provenance"] == list(PROVENANCE)
            and component["decided_by"] == "agent"
            for component in payload["components"]
        )
        assert [rule["kind"] for rule in payload["rules"]] == ["complete_requires"]


def test_nest_target_records_source_owned_internal_dependencies() -> None:
    tree, _ = _target()
    root = {component.label: component for component in tree.root.components}
    mounted = {mount.parent.id: mount.contract for mount in tree.mounts}
    composition = root["API composition"]
    shared = root["Shared request infrastructure"]
    identity = root["Account and authentication"]
    articles = root["Article and comment publishing"]
    profile = root["Profile and follow"]
    tags = root["Tag catalogue"]
    persistence = root["Persistence and schema lifecycle"]

    for target, path in (
        (identity, "src/user/user.module.ts"),
        (articles, "src/article/article.module.ts"),
        (profile, "src/profile/profile.module.ts"),
        (tags, "src/tag/tag.module.ts"),
        (persistence, "src/mikro-orm.config.ts"),
    ):
        assert requires_covers(composition, target.label, _module(path))
    assert requires_covers(shared, identity.label, _module("src/user/user.entity.ts"))
    assert requires_covers(identity, shared.label, _module("src/user/auth.middleware.ts"))
    assert requires_covers(identity, articles.label, _module("src/article/article.entity.ts"))
    assert requires_covers(identity, persistence.label, _module("src/entities.generated.ts"))
    assert requires_covers(articles, identity.label, _module("src/user/user.module.ts"))
    assert requires_covers(articles, shared.label, _module("src/user/auth.middleware.ts"))
    assert requires_covers(profile, identity.label, _module("src/user/user.entity.ts"))
    assert requires_covers(profile, shared.label, _module("src/user/auth.middleware.ts"))
    assert requires_covers(tags, identity.label, _module("src/user/user.module.ts"))
    assert requires_covers(persistence, identity.label, _module("src/user/user.entity.ts"))
    assert requires_covers(persistence, articles.label, _module("src/article/article.entity.ts"))
    assert requires_covers(persistence, articles.label, _module("src/article/comment.entity.ts"))
    assert requires_covers(persistence, tags.label, _module("src/tag/tag.entity.ts"))

    runtime = mounted[composition.id]
    runtime_components = {component.label: component for component in runtime.components}
    assert requires_covers(
        runtime_components["Nest root module"],
        "Root response controller",
        _module("src/app.controller.ts"),
    )
    identity_children = {c.label: c for c in mounted[identity.id].components}
    assert requires_covers(
        identity_children["Account module wiring"],
        "Account HTTP contracts",
        _module("src/user/user.controller.ts"),
    )
    assert requires_covers(
        identity_children["Account module wiring"],
        "Account application service",
        _module("src/user/user.service.ts"),
    )
    assert requires_covers(
        identity_children["Account application service"],
        "Account HTTP contracts",
        _module("src/user/user.interface.ts"),
    )
    publishing_children = {c.label: c for c in mounted[articles.id].components}
    assert requires_covers(
        publishing_children["Article module wiring"],
        "Article application service",
        _module("src/article/article.service.ts"),
    )
    assert requires_covers(
        publishing_children["Article application service"],
        "Article and comment HTTP contracts",
        _module("src/article/dto/index.ts"),
    )
    assert requires_covers(
        publishing_children["Article and comment HTTP contracts"],
        "Article and comment models",
        _module("src/article/article.entity.ts"),
    )
    persistence_children = {c.label: c for c in mounted[persistence.id].components}
    assert (
        _module("src/entities.generated.ts")
        in persistence_children["ORM registry and configuration"].exact_modules
    )


def test_nest_target_closes_principal_api_and_required_user_creation() -> None:
    _, graph = _target()
    entities = _entity_index(graph)
    service_module = _module("src/user/user.service.ts")
    user_module = _module("src/user/user.entity.ts")
    create = entities[("method", f"{service_module}.UserService.create")]
    user = entities[("class", f"{user_module}.User")]
    create_parameters = [
        (parameter.name, parameter.kind, parameter.annotation)
        for parameter in create.signature.parameters
    ]
    assert create_parameters == [("dto", "positional", "CreateUserDto")]
    assert create.signature.returns == "Promise<IUserRO>"
    assert "async" in create.modifiers
    for name in (
        "findAll",
        "findOne",
        "findById",
        "findByEmail",
        "update",
        "delete",
        "generateJWT",
    ):
        assert ("method", f"{service_module}.UserService.{name}") in entities
    assert any(
        relationship.kind == "creates"
        and relationship.source_id == create.id
        and relationship.target_id == user.id
        for relationship in graph.relationships
    )

    article_service = _module("src/article/article.service.ts")
    feed = entities[("method", f"{article_service}.ArticleService.findFeed")]
    assert [(parameter.name, parameter.annotation) for parameter in feed.signature.parameters] == [
        ("user", "Viewer"),
        ("query", "any"),
    ]
    assert feed.signature.returns == "Promise<IArticlesRO>"
    for name in (
        "findAll",
        "findFeed",
        "findOne",
        "findComments",
        "create",
        "update",
        "delete",
        "favorite",
        "unFavorite",
        "addComment",
        "deleteComment",
    ):
        assert ("method", f"{article_service}.ArticleService.{name}") in entities
    user_controller = _module("src/user/user.controller.ts")
    assert {
        ("method", f"{user_controller}.UserController.{name}")
        for name in ("findMe", "update", "create", "delete", "login")
    } <= entities.keys()
    article_controller = _module("src/article/article.controller.ts")
    assert {
        ("method", f"{article_controller}.ArticleController.{name}")
        for name in (
            "findAll",
            "getFeed",
            "findOne",
            "findComments",
            "create",
            "update",
            "delete",
            "createComment",
            "deleteComment",
            "favorite",
            "unFavorite",
        )
    } <= entities.keys()

    profile_service = _module("src/profile/profile.service.ts")
    for name in ("follow", "unFollow", "findProfile"):
        assert ("method", f"{profile_service}.ProfileService.{name}") in entities
    profile_controller = _module("src/profile/profile.controller.ts")
    assert {
        ("method", f"{profile_controller}.ProfileController.{name}")
        for name in ("getProfile", "follow", "unFollow")
    } <= entities.keys()
    tag_service = _module("src/tag/tag.service.ts")
    assert (
        "method",
        f"{tag_service}.TagService.findAll",
    ) in entities
    tag_controller = _module("src/tag/tag.controller.ts")
    assert ("method", f"{tag_controller}.TagController.findAll") in entities
    middleware = _module("src/user/auth.middleware.ts")
    use = entities[("method", f"{middleware}.AuthMiddleware.use")]
    assert "async" in use.modifiers
    validation = _module("src/shared/pipes/validation.pipe.ts")
    transform = entities[("method", f"{validation}.ValidationPipe.transform")]
    assert "async" in transform.modifiers

    for qualified_name in (
        f"{user_module}.User",
        f"{_module('src/article/article.entity.ts')}.Article",
        f"{_module('src/article/comment.entity.ts')}.Comment",
        f"{_module('src/tag/tag.entity.ts')}.Tag",
    ):
        assert ("class", qualified_name) in entities
    for qname in (
        f"{_module('src/user/dto/create-user.dto.ts')}.CreateUserDto",
        f"{_module('src/user/dto/login-user.dto.ts')}.LoginUserDto",
        f"{_module('src/user/dto/update-user.dto.ts')}.UpdateUserDto",
        f"{_module('src/article/dto/create-article.dto.ts')}.CreateArticleDto",
        f"{_module('src/article/dto/create-comment.ts')}.CreateCommentDto",
        f"{_module('src/user/user.interface.ts')}.IUserData",
        f"{_module('src/article/article.interface.ts')}.IArticlesRO",
        f"{_module('src/profile/profile.interface.ts')}.IProfileRO",
        f"{_module('src/tag/tag.interface.ts')}.ITagsRO",
    ):
        assert ("class" if qname.endswith("Dto") else "interface", qname) in entities
    assert entities[("attribute", f"{user_module}.User.favorites")].annotation is None
    assert entities[("attribute", f"{user_module}.User.bio")].annotation == "string & Opt"
    assert entities[("method", f"{user_module}.User.toJSON")].signature is None
    assert (
        "class",
        f"{_module('src/user/user.repository.ts')}.UserRepository",
    ) in entities
    article_entity = _module("src/article/article.entity.ts")
    assert ("attribute", f"{article_entity}.Article.description") in entities
    assert entities[("attribute", f"{article_entity}.Article.description")].annotation is None
    for name in (
        "Migration20211219155639",
        "Migration20240114223020",
        "Migration20240114224028",
    ):
        migration_module = _module(f"src/migrations/{name}.ts")
        assert ("class", f"{migration_module}.{name}") in entities
        assert ("method", f"{migration_module}.{name}.up") in entities
    for qname in (
        f"{_module('src/user/user.interface.ts')}.IUserData.image",
        f"{_module('src/profile/profile.interface.ts')}.IProfileData.following",
    ):
        assert ("attribute", qname) in entities
    dto_module = _module("src/user/dto/create-user.dto.ts")
    for name in ("username", "email", "password"):
        assert ("attribute", f"{dto_module}.CreateUserDto.{name}") in entities
    article_dto = _module("src/article/dto/create-article.dto.ts")
    assert (
        entities[("attribute", f"{article_dto}.CreateArticleDto.tagList")].annotation == "string[]"
    )
    app_module = _module("src/app.module.ts")
    assert ("method", f"{app_module}.AppModule.onModuleInit") in entities
    bootstrap_module = _module("src/main.ts")
    bootstrap = entities[("function", f"{bootstrap_module}.bootstrap")]
    assert "async" in bootstrap.modifiers
    seeder = _module("src/seeders/test.seeder.ts")
    assert ("method", f"{seeder}.TestSeeder.run") in entities
    generated = _module("src/entities.generated.ts")
    assert ("constant", f"{generated}.entities") in entities
    assert ("type_alias", f"{generated}.Database") in entities
    assert ("type_alias", f"{generated}.EntityManager") in entities
    assert ("constant", f"{generated}.EntityManager") in entities


def test_nest_target_closes_only_source_authored_direct_member_scopes() -> None:
    _, graph = _target()
    entities = {entity.id: entity for entity in graph.entities}
    expected = {
        "AppController": ("method",),
        "AppModule": ("attribute", "method"),
        "Article": ("attribute", "method"),
        "ArticleController": ("attribute", "method"),
        "ArticleDTO": ("attribute",),
        "ArticleModule": ("attribute", "method"),
        "ArticleService": ("attribute", "method"),
        "AuthMiddleware": ("attribute", "method"),
        "Comment": ("attribute", "method"),
        "CreateArticleDto": ("attribute",),
        "CreateCommentDto": ("attribute",),
        "CreateUserDto": ("attribute",),
        "IArticleRO": ("attribute",),
        "IArticlesRO": ("attribute",),
        "IComment": ("attribute",),
        "ICommentsRO": ("attribute",),
        "IProfileData": ("attribute",),
        "IProfileRO": ("attribute",),
        "ITagsRO": ("attribute",),
        "IUserData": ("attribute",),
        "IUserRO": ("attribute",),
        "LoginUserDto": ("attribute",),
        "Migration20211219155639": ("method",),
        "Migration20240114223020": ("method",),
        "Migration20240114224028": ("method",),
        "ProfileController": ("attribute", "method"),
        "ProfileModule": ("attribute", "method"),
        "ProfileService": ("attribute", "method"),
        "Tag": ("attribute", "method"),
        "TagController": ("attribute", "method"),
        "TagModule": ("attribute", "method"),
        "TagService": ("attribute", "method"),
        "TestSeeder": ("method",),
        "UpdateUserDto": ("attribute",),
        "User": ("attribute", "method"),
        "UserController": ("attribute", "method"),
        "UserDTO": ("attribute",),
        "UserModule": ("attribute", "method"),
        "UserRepository": ("attribute", "method"),
        "UserService": ("attribute", "method"),
        "ValidationPipe": ("method",),
    }
    scopes = {
        entities[scope.scope_id].qualified_name.rsplit(".", 1)[-1]: scope
        for scope in graph.target_scopes
    }

    assert scopes.keys() == expected.keys()
    assert all(scope.mode == "closed" for scope in scopes.values())
    assert {name: scope.entity_kinds for name, scope in scopes.items()} == expected
    assert all(entities[scope.scope_id].kind in {"class", "interface"} for scope in scopes.values())

    comment_body = next(
        entity for entity in graph.entities if entity.qualified_name.endswith(".IComment.body")
    )
    assert comment_body.visibility.kind == "public"

    def direct_members(name: str) -> set[tuple[str, str]]:
        owner = next(
            entity
            for entity in graph.entities
            if entity.kind in {"class", "interface"}
            and entity.qualified_name.rsplit(".", 1)[-1] == name
        )
        return {
            (entity.kind, entity.qualified_name.rsplit(".", 1)[-1])
            for entity in graph.entities
            if entity.parent_id == owner.id
        }

    assert direct_members("User") == {
        ("attribute", name)
        for name in (
            "[EntityName]",
            "[EntityRepositoryType]",
            "id",
            "username",
            "email",
            "bio",
            "image",
            "password",
            "favorites",
            "followers",
            "followed",
            "articles",
        )
    } | {("method", "constructor"), ("method", "toJSON")}
    assert direct_members("UserService") == {
        ("attribute", "userRepository"),
        ("attribute", "em"),
        *{
            ("method", name)
            for name in (
                "constructor",
                "findAll",
                "findOne",
                "create",
                "update",
                "delete",
                "findById",
                "findByEmail",
                "generateJWT",
                "buildUserRO",
            )
        },
    }
    assert direct_members("ArticleService") == {
        ("attribute", name)
        for name in (
            "em",
            "articleRepository",
            "commentRepository",
            "userRepository",
        )
    } | {
        ("method", name)
        for name in (
            "constructor",
            "findAll",
            "findFeed",
            "findOne",
            "addComment",
            "deleteComment",
            "favorite",
            "unFavorite",
            "findComments",
            "create",
            "update",
            "delete",
        )
    }
    assert direct_members("ValidationPipe") == {
        ("method", name) for name in ("transform", "buildError", "toValidate")
    }
    assert direct_members("UserModule") == {("method", "configure")}
    assert direct_members("AppModule") == {
        ("attribute", "orm"),
        ("method", "constructor"),
        ("method", "onModuleInit"),
    }


def test_nest_target_bundle_hash_and_provenance_graph_are_current() -> None:
    _target()
    for relative in CONTRACTS:
        payload = json.loads((FIXTURE / relative).read_text(encoding="utf-8"))
        assert payload["components"]
        assert [rule["kind"] for rule in payload["rules"]] == ["complete_requires"]
    snapshot = json.loads((FIXTURE / "SNAPSHOT.json").read_text(encoding="utf-8"))
    assert snapshot["commit"] == "a6818d84b6a019cf2df4ef391dc87cea7d02c6a9"
    target_hash = hashlib.sha256(
        b"".join((FIXTURE / relative).read_bytes() for relative in CONTRACTS)
    ).hexdigest()
    receipt = (FIXTURE / "docs" / "target.md").read_text(encoding="utf-8")
    assert f"Target bundle SHA-256: `{target_hash}`" in receipt
    assert "<!-- archkeel-component-graph -->\n```mermaid\ngraph TD\n" in receipt
    assert "decorator details are not emitted" in receipt

    config = tomllib.loads((FIXTURE / "archkeel.toml").read_text(encoding="utf-8"))
    assert config["scan"] == {
        "language": "typescript",
        "roots": ["src"],
        "namespace": NAMESPACE,
        "contract": "architecture-contract.json",
        "tsconfig": "tsconfig.build.json",
    }
