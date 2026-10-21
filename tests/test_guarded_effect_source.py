# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT

import pytest
from test_exact_module_ownership import _component, _observe_tree, _rule

from archkeel.ir.decisions import rule_assessments
from archkeel.ir.facts import guarded_effect


def test_native_collector_publishes_condition_bound_private_helper_actuals(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

def _helper(flag: bool):
    if flag:
        _effect()

def generate(seeded: bool):
    if seeded:
        _helper(seeded)
""",
        },
        contract,
    )

    assert result.observation is not None, result.coverage
    call = next(
        row
        for row in result.observation.records("calls") or ()
        if row.data.get("source_scope") == "sample.core.generate"
    )
    [proof] = [
        guarded_effect(item)
        for item in call.data.get("guarded_effect", ())
        if guarded_effect(item).condition.owner == "sample.core.generate"
    ]

    assert proof.condition_value is True
    [helper] = proof.helper_bindings
    assert helper.target == "sample.core._helper"
    assert helper.call_id == call.id
    [actual] = helper.arguments
    assert actual.argument_index == 0
    assert actual.token_kind == "condition"
    assert actual.condition is not None and actual.condition.name == "seeded"


def test_native_private_helper_uses_the_shared_binder_per_call_site(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

def _helper(flag: bool):
    if flag:
        _effect()

def generate(seeded: bool):
    if seeded:
        _helper(flag=seeded)
    if not seeded:
        _helper(flag=not seeded)
""",
        },
        contract,
    )
    assert result.observation is not None, result.coverage
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "FAIL"
    assert assessment.count == 1
    assert assessment.evaluation_proven


def test_native_secrets_effect_is_proven_directly_and_through_one_helper(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="secrets.token_hex",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    sources = (
        "import secrets\ndef generate(seeded: bool):\n"
        "    if seeded:\n        secrets.token_hex(8)\n",
        "import secrets\ndef _nonce(flag: bool):\n"
        "    if flag:\n        secrets.token_hex(8)\n\n"
        "def generate(seeded: bool):\n    if seeded:\n        _nonce(seeded)\n",
    )
    for index, source in enumerate(sources):
        result = _observe_tree(
            tmp_path / str(index),
            {"sample/__init__.py": "", "sample/core.py": source},
            contract,
        )
        assert result.observation is not None, result.coverage
        [assessment] = rule_assessments(result.observation, undecided_by_rule={})
        assert assessment.status == "FAIL"
        assert assessment.count == 1
        assert assessment.evaluation_proven
        [call] = [
            item
            for item in result.observation.records("calls") or ()
            if item.data.get("expression") == "secrets.token_hex"
        ]
        binding = call.data.get("call_binding")
        assert binding is not None and binding.get("target") == "secrets.token_hex"


def test_native_true_guarded_effect_fails_but_early_return_dominates(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    for body, expected in (
        ("if seeded:\n        _effect()", "FAIL"),
        ("if seeded:\n        return 'fixed'\n    _effect()", "PASS"),
        ("if seeded:\n        raise ValueError()\n    _effect()", "PASS"),
        ("if not seeded:\n        _effect()", "PASS"),
        ("if not seeded:\n        raise ValueError()\n    _effect()", "FAIL"),
        ("return _effect() if seeded else 'fixed'", "FAIL"),
    ):
        result = _observe_tree(
            tmp_path / expected,
            {
                "sample/__init__.py": "",
                "sample/core.py": (
                    f"def _effect():\n    return None\n\ndef generate(seeded: bool):\n    {body}\n"
                ),
            },
            contract,
        )

        assert result.observation is not None
        [assessment] = rule_assessments(result.observation, undecided_by_rule={})
        assert assessment.status == expected
        assert assessment.evaluation_proven


def test_terminal_control_inside_unmodeled_with_or_match_stays_unknown(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    sources = (
        "def _effect(): pass\n"
        "def generate(seeded: bool):\n"
        "    if seeded:\n"
        "        with gate:\n"
        "            return\n"
        "    _effect()\n",
        "def _effect(): pass\n"
        "def generate(seeded: bool):\n"
        "    if seeded:\n"
        "        match seeded:\n"
        "            case True:\n"
        "                return\n"
        "            case _:\n"
        "                pass\n"
        "    _effect()\n",
    )
    for index, source in enumerate(sources):
        result = _observe_tree(
            tmp_path / str(index),
            {"sample/__init__.py": "", "sample/core.py": source},
            contract,
        )

        assert result.observation is not None, result.diagnostics
        [call] = [
            row
            for row in result.observation.records("calls") or ()
            if row.data.get("expression") == "_effect"
        ]
        proofs = [guarded_effect(item) for item in call.data.get("guarded_effect", ())]
        assert any(
            not proof.complete and proof.unknown_reason == "unsupported_control_flow"
            for proof in proofs
        )
        [assessment] = rule_assessments(result.observation, undecided_by_rule={})
        assert assessment.status in {"UNKNOWN", "INCONCLUSIVE"}


def test_instance_member_guard_is_bound_to_its_annotated_declaration(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "member",
                    "owner": "sample.core.Generator",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

class Generator:
    def __init__(self):
        self.seeded: bool = False

    def generate(self):
        if self.seeded:
            _effect()
""",
        },
        contract,
    )

    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "FAIL"
    assert assessment.evaluation_proven


def test_reflective_member_mutation_cannot_preserve_the_guard(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "member",
                    "owner": "sample.core.Generator",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

class Generator:
    def __init__(self):
        self.seeded: bool = True

    def generate(self):
        if self.seeded:
            setattr(self, "seeded", False)
            _effect()
""",
        },
        contract,
    )
    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_opaque_method_call_invalidates_a_member_guard(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "member",
                    "owner": "sample.core.Generator",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

class Generator:
    def __init__(self):
        self.seeded: bool = False

    def reset(self):
        self.seeded = True

    def generate(self):
        if not self.seeded:
            self.reset()
            _effect()
""",
        },
        contract,
    )
    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_effect_deferred_to_a_nested_callable_remains_unknown(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

def generate(seeded: bool):
    if seeded:
        callback = lambda: _effect()
""",
        },
        contract,
    )

    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_raise_exception_identity_is_lexically_proven_or_remains_unknown(tmp_path):
    base_rule = _rule(
        "forbidden_effect_under_condition",
        source="sample.core",
        target="sample.core._effect",
        condition={
            "kind": "parameter",
            "owner": "sample.core.generate",
            "name": "seeded",
        },
    )
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [base_rule],
    }
    source = """def _effect():
    return None

def generate(seeded: bool):
    if seeded:
        raise ValueError()
    _effect()
"""
    result = _observe_tree(
        tmp_path / "builtin",
        {"sample/__init__.py": "", "sample/core.py": source},
        contract,
    )
    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "PASS"

    aliased = _observe_tree(
        tmp_path / "builtin-alias",
        {
            "sample/__init__.py": "",
            "sample/core.py": source.replace(
                "def _effect():",
                "from builtins import ValueError as BuiltinError\n\ndef _effect():",
            ).replace("raise ValueError()", "raise BuiltinError()"),
        },
        contract,
    )
    assert aliased.observation is not None
    [assessment] = rule_assessments(aliased.observation, undecided_by_rule={})
    assert assessment.status == "PASS"

    target_rule = dict(base_rule, target="builtins.ValueError")
    selected = _observe_tree(
        tmp_path / "selected",
        {"sample/__init__.py": "", "sample/core.py": source},
        dict(contract, rules=[target_rule]),
    )
    assert selected.observation is not None
    [assessment] = rule_assessments(selected.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"

    unresolved = _observe_tree(
        tmp_path / "unresolved",
        {
            "sample/__init__.py": "",
            "sample/core.py": source.replace("ValueError()", "unknown_factory()"),
        },
        contract,
    )
    assert unresolved.observation is not None
    [assessment] = rule_assessments(unresolved.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"


def test_shadowed_value_error_is_not_misreported_as_builtin_identity(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect():
    return None

def ValueError():
    return None

def generate(seeded: bool):
    if seeded:
        raise ValueError()
    _effect()
""",
        },
        contract,
    )
    assert result.observation is not None
    call = next(
        row
        for row in result.observation.records("calls") or ()
        if row.data.get("expression") == "ValueError"
    )
    [proof] = call.data.get("guarded_effect")
    assert proof.get("unknown_reason") != "raise_constructor_builtin:builtins.ValueError"


def test_missing_callee_identity_withholds_a_true_path_receipt(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={
                    "kind": "parameter",
                    "owner": "sample.core.generate",
                    "name": "seeded",
                },
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": "def generate(seeded: bool):\n    if seeded:\n        unknown()\n",
        },
        contract,
    )

    assert result.observation is not None
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_private_helper_unconditional_effect_is_reachable_with_false_actual(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect(): pass

def _helper(flag: bool):
    _effect()

def generate(seeded: bool):
    if seeded:
        _helper(False)
""",
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "FAIL"
    assert assessment.count == 1
    assert assessment.evaluation_proven


def test_nested_contradictory_guards_do_not_create_reachable_effect_paths(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    bodies = (
        "if not seeded:\n        if seeded:\n            _effect()",
        "return (_effect() if seeded else None) if not seeded else None",
    )
    for index, body in enumerate(bodies):
        result = _observe_tree(
            tmp_path / str(index),
            {
                "sample/__init__.py": "",
                "sample/core.py": (
                    f"def _effect(): pass\ndef generate(seeded: bool):\n    {body}\n"
                ),
            },
            contract,
        )
        assert result.observation is not None, result.diagnostics
        [assessment] = rule_assessments(result.observation, undecided_by_rule={})
        assert assessment.status == "UNKNOWN"
        assert assessment.count == 0
        assert not assessment.evaluation_proven


@pytest.mark.parametrize(
    "nested_declaration",
    ["    def local(): pass\n", "    class Local: pass\n"],
    ids=["function", "class"],
)
def test_nested_declaration_does_not_terminate_the_outer_effect_path(tmp_path, nested_declaration):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def _effect(): pass\ndef generate(seeded: bool):\n"
                f"{nested_declaration}    if seeded:\n        _effect()\n"
            ),
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "FAIL"
    assert assessment.count == 1
    assert assessment.evaluation_proven


@pytest.mark.parametrize(
    "declaration",
    [
        "def local(value=_effect()): pass",
        "@_effect()\ndef local(): pass",
        "class Local(_effect()): pass",
        "class Local:\n            _effect()",
    ],
    ids=["default", "decorator", "class-base", "class-body"],
)
def test_nested_declaration_eager_expressions_keep_the_active_guard(tmp_path, declaration):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def _effect(): pass\ndef generate(seeded: bool):\n"
                f"    if seeded:\n        {declaration.replace(chr(10), chr(10) + '        ')}\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    expected = (
        "UNKNOWN" if declaration.startswith("@") or "class Local:\n" in declaration else "FAIL"
    )
    assert assessment.status == expected, assessment.reason
    if expected == "FAIL":
        assert assessment.count == 1
        assert assessment.evaluation_proven
    elif declaration.startswith("@"):
        calls = result.observation.records("calls") or ()
        assert any(
            proof.get("condition_value") is True
            for row in calls
            for proof in row.data.get("guarded_effect", ())
        )
    else:
        unknowns = result.observation.records("unknowns") or ()
        assert any(item.kind == "guarded_effect_limit" for item in unknowns)


def test_future_annotation_is_not_treated_as_an_eager_effect(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "from __future__ import annotations\ndef _effect(): pass\n"
                "def generate(seeded: bool):\n    if seeded:\n"
                "        def local(value: _effect()): pass\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


@pytest.mark.parametrize(
    "helper", ["def public_helper(): _effect()", "@staticmethod\ndef _helper(): _effect()"]
)
def test_ineligible_resolved_local_helper_is_unknown_under_guard(tmp_path, helper):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    name = "public_helper" if helper.startswith("def public") else "_helper"
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                f"def _effect(): pass\n{helper}\ndef generate(seeded: bool):\n"
                f"    if seeded:\n        {name}()\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert not assessment.evaluation_proven


def test_ineligible_resolved_local_helper_on_false_path_is_ignored(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def _effect(): pass\ndef public_helper(): _effect()\n"
                "def generate(seeded: bool):\n    if not seeded:\n        public_helper()\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "PASS"
    assert assessment.evaluation_proven


def test_private_helper_with_complete_empty_call_inventory_passes(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def _effect(): pass\ndef _helper(): pass\n"
                "def generate(seeded: bool):\n    if seeded:\n        _helper()\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "PASS"
    assert assessment.evaluation_proven


def test_private_helper_with_multiple_boolean_parameters_remains_unknown(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "parameter", "owner": "sample.core.generate", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": (
                "def _effect(): pass\ndef _helper(run: bool, tag: bool):\n"
                "    if run:\n        _effect()\n"
                "def generate(seeded: bool):\n    if seeded:\n        _helper(False, seeded)\n"
            ),
        },
        contract,
    )
    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "UNKNOWN"
    assert assessment.count == 0
    assert not assessment.evaluation_proven


def test_private_helper_substitutes_non_self_member_receiver(tmp_path):
    contract = {
        "schema_version": "3.13.0",
        "components": [_component("all", ["sample"])],
        "rules": [
            _rule(
                "forbidden_effect_under_condition",
                source="sample.core",
                target="sample.core._effect",
                condition={"kind": "member", "owner": "sample.core.Generator", "name": "seeded"},
            )
        ],
    }
    result = _observe_tree(
        tmp_path,
        {
            "sample/__init__.py": "",
            "sample/core.py": """def _effect(): pass

def _helper(flag: bool):
    if flag:
        _effect()

class Generator:
    def __init__(instance):
        instance.seeded: bool = False

    def generate(instance):
        if instance.seeded:
            _helper(instance.seeded)
""",
        },
        contract,
    )

    assert result.observation is not None, result.diagnostics
    [assessment] = rule_assessments(result.observation, undecided_by_rule={})
    assert assessment.status == "FAIL"
    assert assessment.count == 1
    assert assessment.evaluation_proven
    [call] = [
        row
        for row in result.observation.records("calls") or ()
        if row.data.get("source_scope") == "sample.core.Generator.generate"
    ]
    [proof] = [guarded_effect(item) for item in call.data.get("guarded_effect", ())]
    [helper] = proof.helper_bindings
    [actual] = helper.arguments
    assert actual.token_kind == "condition"
    assert actual.condition is not None
    assert (actual.condition.kind.value, actual.condition.owner, actual.condition.name) == (
        "member",
        "sample.core.Generator",
        "seeded",
    )
