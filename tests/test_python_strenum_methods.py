# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Inherited string methods need a proven StrEnum class and lexical annotation binding."""

import json
from pathlib import Path

import pytest

from archkeel.analyzer.python.collect import collect
from archkeel.ir.facts_codec import encode_response
from archkeel.ir.protocol import (
    CollectionRequest,
    CollectionResponse,
    PythonSettings,
    SnapshotInput,
    SourceScope,
)

ENUM = "from enum import StrEnum\nclass Level(StrEnum):\n    MODULE = 'module'\n"
USE = "def use(value: Level):\n    return value.capitalize()\n"


def _native_call(root: Path, files, *, namespace="sample", expression="value.capitalize"):
    for name, source in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    facts = collect(
        CollectionRequest(
            SnapshotInput(str(root), "a" * 40, False),
            SourceScope((".",), namespace),
            PythonSettings(),
        )
    )
    payload = json.loads(encode_response(CollectionResponse(facts)))
    calls = next(
        section["records"] for section in payload["facts"]["sections"] if section["name"] == "calls"
    )
    matching = [row["data"] for row in calls if row["data"]["expression"] == expression]
    assert len(matching) == 1, matching
    return matching[0]


def _files(model=ENUM, app="from sample.model import Level\n" + USE):
    return {"sample/__init__.py": "", "sample/model.py": model, "sample/app.py": app}


@pytest.mark.parametrize(
    "files,expression,target",
    [
        pytest.param(_files(), "value.capitalize", "builtins.str.capitalize", id="imported"),
        pytest.param(
            _files(
                app="from sample.model import Level as Chosen\n"
                "def use(value: Chosen):\n    return value.capitalize()\n"
            ),
            "value.capitalize",
            "builtins.str.capitalize",
            id="explicit-import-alias",
        ),
        pytest.param(
            _files(
                app="import sample.model as model\n"
                "def use(value: model.Level):\n    return value.capitalize()\n"
            ),
            "value.capitalize",
            "builtins.str.capitalize",
            id="qualified-import",
        ),
        pytest.param(
            {"sample/__init__.py": "", "sample/model.py": ENUM + USE},
            "value.capitalize",
            "builtins.str.capitalize",
            id="same-module",
        ),
        pytest.param(
            _files(
                model=ENUM + "    capitalize = 'member'\n",
                app="from sample.model import Level\n"
                "def use(value: Level):\n    return value.upper()\n",
            ),
            "value.upper",
            "builtins.str.upper",
            id="different-method-than-member",
        ),
    ],
)
def test_proven_populated_strenum_annotation_names_only_the_requested_builtin_method(
    tmp_path, files, expression, target
):
    data = _native_call(tmp_path, files, expression=expression)
    assert data["status"] == "partially_resolved", data
    assert data["targets"] == [target], data
    assert data["candidate_count"] == 1, data
    assert "unproven at runtime" in data["reason"], data


UNSAFE_CLASSES = [
    pytest.param(
        "from enum import Enum\nclass Level(Enum):\n    MODULE = 'module'\n", id="ordinary-enum"
    ),
    pytest.param(
        "from enum import IntEnum\nclass Level(IntEnum):\n    MODULE = 1\n", id="integer-enum"
    ),
    pytest.param(
        "class StrEnum: pass\nclass Level(StrEnum):\n    MODULE = 'module'\n",
        id="same-spelling-user-base",
    ),
    pytest.param(
        "from sample.provider import StrEnum\nclass Level(StrEnum):\n    MODULE = 'module'\n",
        id="foreign-provider",
    ),
    pytest.param(
        "from enum import StrEnum\nclass Level(StrEnum): pass\n", id="empty-subclassable-enum"
    ),
    pytest.param(
        "from enum import StrEnum\nclass Extra: pass\n"
        "class Level(Extra, StrEnum):\n    MODULE = 'module'\n",
        id="additional-base",
    ),
    pytest.param(
        "from enum import StrEnum\nclass Level(Missing, StrEnum):\n    MODULE = 'module'\n",
        id="unknown-additional-base",
    ),
    pytest.param(
        "if enabled:\n    from enum import StrEnum\nclass Level(StrEnum):\n    MODULE = 'module'\n",
        id="conditional-base-import",
    ),
    pytest.param(
        "from enum import StrEnum\n@decorate\nclass Level(StrEnum):\n    MODULE = 'module'\n",
        id="decorator",
    ),
    pytest.param(
        "from enum import StrEnum\n"
        "class Level(StrEnum, metaclass=Custom):\n    MODULE = 'module'\n",
        id="metaclass",
    ),
    pytest.param(ENUM + "    capitalize = 'member'\n", id="method-name-is-member"),
    pytest.param(ENUM + "    def capitalize(self): return 'different'\n", id="method-override"),
    pytest.param(
        ENUM + "    @property\n    def capitalize(self): return 'different'\n",
        id="property-override",
    ),
    pytest.param(
        ENUM + "    def __getattribute__(self, name): return replacement\n",
        id="getattribute-override",
    ),
    pytest.param(
        ENUM + "    def __getattr__(self, name): return replacement\n", id="getattr-override"
    ),
    pytest.param(ENUM + "    def __new__(cls, value): return replacement\n", id="new-override"),
    pytest.param(ENUM + "    touch()\n", id="class-body-call"),
    pytest.param(
        "from enum import StrEnum, auto\nclass Level(StrEnum):\n    MODULE = auto()\n",
        id="generated-member",
    ),
    pytest.param(
        ENUM + "    _ignore_ = 'temporary'\n    temporary = 'unused'\n", id="ignored-member-control"
    ),
    pytest.param(ENUM + "    MODULE = 'again'\n", id="duplicate-member"),
    pytest.param(ENUM + "    del MODULE\n", id="deleted-member"),
    pytest.param(ENUM + "    if enabled:\n        OTHER = 'other'\n", id="conditional-member"),
]


@pytest.mark.parametrize("model", UNSAFE_CLASSES)
def test_unsafe_class_never_claims_the_inherited_string_method(tmp_path, model):
    files = _files(model=model)
    files["sample/provider.py"] = "class StrEnum: pass\n"
    data = _native_call(tmp_path, files)
    assert data["status"] in {"unresolved", "partially_resolved"}, data
    assert "builtins.str.capitalize" not in data["targets"], data


UNSAFE_BINDINGS = [
    pytest.param(
        "from sample.model import Level\nAlias = Level\n"
        "def use(value: Alias):\n    return value.capitalize()\n",
        id="assigned-annotation-alias",
    ),
    pytest.param(
        "from sample.model import Level\ndef use(value: 'Level'):\n    return value.capitalize()\n",
        id="quoted-annotation",
    ),
    pytest.param(
        "from sample.model import Level\n"
        "def use(value: Level | None):\n    return value.capitalize()\n",
        id="union-annotation",
    ),
    pytest.param(
        "from sample.model import Level\n"
        "def use(value: list[Level]):\n    return value.capitalize()\n",
        id="generic-is-not-enum",
    ),
    pytest.param(
        "from sample.model import Level\n"
        "def outer(Level):\n"
        "    def use(value: Level):\n        return value.capitalize()\n",
        id="lexically-shadowed-annotation",
    ),
    pytest.param(
        "from sample.model import Level\nLevel = replacement\n" + USE,
        id="rebound-import",
    ),
    pytest.param(
        "if enabled:\n    from sample.model import Level\n" + USE,
        id="conditional-import",
    ),
    pytest.param(
        "from sample.model import Level\nfrom sample.provider import Level\n" + USE,
        id="competing-imports",
    ),
    pytest.param(
        "from sample.model import Level\n"
        "def use(value: Level):\n"
        "    value = unknown()\n    return value.capitalize()\n",
        id="conflicting-value-rebinding",
    ),
    pytest.param(
        "from sample.model import Level\n"
        "def use(value: Level):\n"
        "    for value in unknown():\n        pass\n"
        "    return value.capitalize()\n",
        id="loop-target-rebinding",
    ),
]


@pytest.mark.parametrize("app", UNSAFE_BINDINGS)
def test_unproven_annotation_or_value_binding_keeps_its_conservative_fallback(tmp_path, app):
    files = _files(app=app)
    files["sample/provider.py"] = "class Level: pass\n"
    data = _native_call(tmp_path, files)
    assert data["status"] in {"unresolved", "partially_resolved"}, data
    assert "builtins.str.capitalize" not in data["targets"], data


@pytest.mark.parametrize(
    "model_suffix,app_prefix,extra",
    [
        pytest.param("\nLevel.capitalize = replacement\n", "", {}, id="same-module-write"),
        pytest.param("", "Level.capitalize = replacement\n", {}, id="imported-write"),
        pytest.param("", "del Level.capitalize\n", {}, id="imported-delete"),
        pytest.param("", "setattr(Level, 'capitalize', replacement)\n", {}, id="setattr"),
        pytest.param("", "mutate(Level)\n", {}, id="class-escape"),
        pytest.param(
            "", "Alias = Level\nAlias.capitalize = replacement\n", {}, id="aliased-member-write"
        ),
        pytest.param("\nStrEnum.capitalize = replacement\n", "", {}, id="base-member-write"),
        pytest.param(
            "\nimport enum\nenum.StrEnum = replacement\n", "", {}, id="provider-attribute-write"
        ),
        pytest.param("\nmutate(StrEnum)\n", "", {}, id="provider-escape"),
        pytest.param(
            "",
            "",
            {"sample/patch.py": "import enum\nenum.StrEnum = replacement\n"},
            id="cross-module-provider-write",
        ),
        pytest.param(
            "",
            "",
            {"sample/patch.py": "from sample.model import Level\nLevel.capitalize = replacement\n"},
            id="cross-module-class-write",
        ),
    ],
)
def test_class_or_provider_mutation_cannot_authorize_a_builtin_target(
    tmp_path, model_suffix, app_prefix, extra
):
    files = _files(
        model=ENUM + model_suffix, app="from sample.model import Level\n" + app_prefix + USE
    )
    files.update(extra)
    data = _native_call(tmp_path, files)
    assert data["status"] in {"unresolved", "partially_resolved"}, data
    assert "builtins.str.capitalize" not in data["targets"], data


def test_scanned_provider_named_enum_strenum_is_not_the_stdlib_class(tmp_path):
    data = _native_call(
        tmp_path,
        {
            "enum/__init__.py": "class StrEnum: pass\n",
            "enum/app.py": ENUM + USE,
        },
        namespace="enum",
    )
    assert "builtins.str.capitalize" not in data["targets"], data
    assert data["status"] in {"unresolved", "partially_resolved"}, data


def test_existing_string_annotation_retains_partial_evidence(tmp_path):
    data = _native_call(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/app.py": "def use(value: str):\n    return value.capitalize()\n",
        },
    )
    assert data["status"] == "partially_resolved", data
    assert data["targets"] == ["builtins.str.capitalize"], data
