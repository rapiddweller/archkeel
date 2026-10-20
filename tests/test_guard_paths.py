import ast

from archkeel.analyzer.python.guard_paths import guarded_call_paths


def _paths(source: str, function_name: str = "target"):
    module = ast.parse(source)
    function = next(
        item
        for item in module.body
        if isinstance(item, ast.FunctionDef) and item.name == function_name
    )
    return guarded_call_paths(function, "seeded")


def test_if_else_tracks_guard_polarity_for_calls():
    paths = _paths(
        """def target(seeded):
    if seeded:
        forbidden()
    else:
        allowed()
"""
    )

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("forbidden", True),
        ("allowed", False),
    ]
    assert all(isinstance(path.path_nodes[0], ast.Name) for path in paths)


def test_ternary_tracks_each_expression_path():
    paths = _paths("def target(seeded):\n    return forbidden() if seeded else allowed()\n")

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("forbidden", True),
        ("allowed", False),
    ]


def test_unconditional_call_is_reachable_with_condition_true():
    [path] = _paths("def target(seeded):\n    forbidden()\n")

    assert path.condition_value is None
    assert path.unknown_reason is None


def test_return_and_raise_remove_unreachable_paths():
    paths = _paths(
        """def target(seeded):
    if seeded:
        return fixed()
    raise ValueError()
    forbidden()
"""
    )

    assert [path.call_name for path in paths] == ["fixed", "ValueError"]


def test_effect_after_early_return_is_dominated_by_the_other_branch():
    paths = _paths(
        """def target(seeded):
    if seeded:
        return fixed()
    forbidden()
"""
    )

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("fixed", True),
        ("forbidden", False),
    ]


def test_reassignment_and_unsupported_control_flow_are_unknown():
    reassigned = _paths(
        """def target(seeded):
    if seeded:
        seeded = False
        forbidden()
"""
    )
    looped = _paths(
        """def target(seeded):
    while seeded:
        forbidden()
"""
    )

    assert len(reassigned) == len(looped) == 1
    assert reassigned[0].condition_value is None
    assert looped[0].condition_value is None


def test_unknown_branch_does_not_hide_a_proven_guarded_sibling():
    paths = _paths(
        """def target(seeded, other):
    if other:
        while True:
            uncertain()
    elif seeded:
        forbidden()
"""
    )

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("uncertain", None),
        ("forbidden", True),
    ]


def test_named_expression_in_condition_invalidates_guard_value():
    paths = _paths(
        """def target(seeded):
    if seeded:
        if (seeded := False):
            forbidden()
"""
    )

    assert paths[0].condition_value is None


def test_reflective_member_write_invalidates_a_stored_guard():
    module = ast.parse(
        """class Generator:
    def target(self):
        if self.seeded:
            setattr(self, "seeded", False)
            forbidden()
"""
    )
    function = module.body[0].body[0]
    paths = guarded_call_paths(function, "seeded", receiver_name="self")

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("setattr", None),
        ("forbidden", None),
    ]


def test_short_circuit_and_finally_paths_are_unknown():
    short_circuit = _paths(
        """def target(seeded, other):
    if seeded:
        if seeded and other:
            forbidden()
"""
    )
    finally_path = _paths(
        """def target(seeded):
    try:
        return fixed()
    finally:
        forbidden()
"""
    )

    assert short_circuit[0].condition_value is None
    assert [(path.call_name, path.condition_value) for path in finally_path] == [
        ("fixed", None),
        ("forbidden", None),
    ]


def test_declared_member_truth_and_negation_track_boolean_paths():
    module = ast.parse(
        """class Generator:
    def target(self):
        if not self.seeded:
            allowed()
        else:
            forbidden()
"""
    )
    function = module.body[0].body[0]
    paths = guarded_call_paths(function, "seeded", receiver_name="self")

    assert [(path.call_name, path.condition_value) for path in paths] == [
        ("allowed", False),
        ("forbidden", True),
    ]
