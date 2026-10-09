# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only variants for the pinned Python RealWorld project Target."""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.model import stable_id
from fixtures.demo_catalog_support import Variant

PYTHON_REALWORLD_FIXTURE_DIR = Path(__file__).resolve().parent / "K-python-realworld"
_ARTICLES_ROUTE = "app/api/routes/articles/articles_resource.py"
_ARTICLE_MODEL = "app/models/domain/articles.py"
_AUTH_ROUTE = "app/api/routes/authentication.py"
_UML_RULE = stable_id("UML-TARGET", "architecture-contract.json")


def _replace(relative: str, old: str, new: str, *, occurrences: int = 1) -> str:
    source = (PYTHON_REALWORLD_FIXTURE_DIR / relative).read_text()
    if source.count(old) != occurrences:
        raise ValueError(f"{relative}: expected {occurrences} mutation anchors {old!r}")
    return source.replace(old, new, 1)


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="python-realworld-project",
        section="clean",
        item="python-realworld:project",
        summary="The full pinned RealWorld app: account, profile, article/feed/favorite, comment, "
        "tag, repository and PostgreSQL query modules compared with the frozen project Target.",
        files={},
        expected_violations=(),
        expected_codes=(),
        fixture=PYTHON_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="python-realworld-forbidden-edge",
        section="class_a",
        item="python-realworld:forbidden_edge",
        summary="Add a direct SQL-query import to an HTTP route, bypassing its repository.",
        files={
            _ARTICLES_ROUTE: _replace(
                _ARTICLES_ROUTE,
                "from app.db.repositories.articles import ArticlesRepository",
                "from app.db.queries.queries import queries\n"
                "from app.db.repositories.articles import ArticlesRepository",
            )
        },
        expected_violations=("REQUIRES-COMPLETE",),
        expected_codes=("rule.violated",),
        fixture=PYTHON_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="python-realworld-signature-fail",
        section="class_a",
        item="python-realworld:article_tags_signature",
        summary="Change Article.tags from List[str] to List[int] in the closed UML scope.",
        files={_ARTICLE_MODEL: _replace(_ARTICLE_MODEL, "tags: List[str]", "tags: List[int]")},
        expected_violations=(_UML_RULE,),
        expected_codes=("rule.violated",),
        fixture=PYTHON_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="FAIL",
    ),
    Variant(
        id="python-realworld-dynamic-unknown",
        section="class_a",
        item="python-realworld:login_dynamic_call",
        summary="Dispatch login JWT creation with getattr; the required call becomes UNKNOWN.",
        files={
            _AUTH_ROUTE: _replace(
                _AUTH_ROUTE,
                "token = jwt.create_access_token_for_user(",
                'token = getattr(jwt, "create_access_token_for_user")(',
                occurrences=2,
            )
        },
        expected_violations=(),
        expected_codes=(),
        fixture=PYTHON_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
)
