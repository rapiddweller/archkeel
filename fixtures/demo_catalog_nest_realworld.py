# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Source-only variants for the frozen Nest/Mikro RealWorld project Target."""

from __future__ import annotations

from pathlib import Path

from archkeel.ir.model import stable_id
from fixtures.demo_catalog_support import Variant

NEST_REALWORLD_FIXTURE_DIR = Path(__file__).resolve().parent / "L-nest-realworld"
_USER_SERVICE = "src/user/user.service.ts"
_ARTICLE_SERVICE = "src/article/article.service.ts"
_VALIDATION_PIPE = "src/shared/pipes/validation.pipe.ts"
_UML_RULE = stable_id("UML-TARGET", "architecture-contract.json")


def _replace(relative: str, old: str, new: str) -> str:
    source = (NEST_REALWORLD_FIXTURE_DIR / relative).read_text()
    if source.count(old) != 1:
        raise ValueError(f"{relative}: expected one mutation anchor {old!r}")
    return source.replace(old, new, 1)


VARIANTS: tuple[Variant, ...] = (
    Variant(
        id="nest-realworld-project",
        section="clean",
        item="nest-realworld:project",
        summary="Full pinned Nest RealWorld app against its frozen 41-input Target.",
        files={},
        expected_violations=(),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=NEST_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="nest-realworld-forbidden-edge",
        section="class_a",
        item="nest-realworld:forbidden_edge",
        summary="Make shared request validation import Article across a forbidden boundary.",
        files={
            _VALIDATION_PIPE: _replace(
                _VALIDATION_PIPE,
                "import { Dictionary } from '@mikro-orm/mysql';",
                "import { Dictionary } from '@mikro-orm/mysql';\n"
                "import { Article } from '../../article/article.entity';",
            )
        },
        expected_violations=("REQUIRES-COMPLETE",),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=NEST_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="nest-realworld-signature-fail",
        section="class_a",
        item="nest-realworld:feed-signature",
        summary="Change ArticleService.findFeed's declared result from IArticlesRO to IArticleRO.",
        files={
            _ARTICLE_SERVICE: _replace(
                _ARTICLE_SERVICE,
                "async findFeed(user: Viewer, query: any): Promise<IArticlesRO> {",
                "async findFeed(user: Viewer, query: any): Promise<IArticleRO> {",
            )
        },
        expected_violations=(_UML_RULE,),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=NEST_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
    Variant(
        id="nest-realworld-dynamic-unknown",
        section="class_a",
        item="nest-realworld:dynamic-user-construction",
        summary="Use a type-asserted constructor in UserService.create to make creates unknown.",
        files={
            _USER_SERVICE: _replace(
                _USER_SERVICE,
                "new User(username, email, password)",
                "new (User as any)(username, email, password)",
            )
        },
        expected_violations=(),
        expected_codes=(),
        expected_kinds=("parse_error",),
        fixture=NEST_REALWORLD_FIXTURE_DIR,
        expected_declared_rules="UNKNOWN",
    ),
)
