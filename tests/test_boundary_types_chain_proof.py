# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Every public re-export hop needs proof; private aliases cannot change that proof."""

from pathlib import Path

import pytest
from test_boundary_types_non_init_facades import _write_app

from archkeel.analyzer import observe

SAFE = "\ndef safe(value: str) -> str:\n    return value\n"
EXPORT = '__all__ = ["constraints", "safe"]\n'


@pytest.mark.parametrize(
    ("api", "middle", "package", "proven", "typed_origin"),
    [
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from .impl import element_constraints as constraints\n__all__ = ["constraints"]\n',
            False,
            True,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from ..impl import element_constraints as constraints\n__all__ = ["constraints"]\n',
            True,
            True,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from .impl import element_constraints as constraints\n'
            '__all__ = ["constraints"]\n__all__.append("other")\n',
            False,
            False,
            False,
        ),
        (
            "from .middle import constraints\n" + EXPORT + SAFE,
            'from ..impl import element_constraints as constraints\n__all__ = ["constraints"]\n'
            + SAFE
            + "constraints = safe\n",
            True,
            False,
            False,
        ),
        (
            "from .impl import element_constraints as constraints\n" + EXPORT + SAFE,
            'from .impl import element_constraints as constraints\n'
            '__all__ = ["constraints"]\nconstraints = object\n',
            False,
            True,
            False,
        ),
        (
            "from .impl import element_constraints as constraints\n"
            + EXPORT
            + SAFE
            + "constraints = safe\n",
            "",
            False,
            False,
            True,
        ),
    ],
    ids=(
        "ordinary-control",
        "init-control",
        "mutated-intermediate",
        "rebound-init",
        "private-alias-does-not-poison-public",
        "unknown-does-not-prove-facade-types",
    ),
)
def test_public_chain_proof_is_complete_and_entry_scoped(
    tmp_path: Path,
    api: str,
    middle: str,
    package: bool,
    proven: bool,
    typed_origin: bool,
) -> None:
    _write_app(tmp_path, public=["sample.app.api"], init="", api=api)
    path = tmp_path / "sample/app/middle.py"
    if package:
        path = tmp_path / "sample/app/middle/__init__.py"
        path.parent.mkdir()
    path.write_text(middle)
    if typed_origin:
        (tmp_path / "sample/app/impl.py").write_text(
            "class Payload:\n    pass\n"
            "def element_constraints(value: Payload) -> Payload:\n    return value\n"
        )
    result = observe(
        tmp_path,
        roots=("sample",),
        namespace="sample",
        contract="contract.json",
        git_head="a" * 40,
        dirty=False,
        contract_root=tmp_path,
    )
    assert result.observation is not None, result.diagnostics
    observation = result.observation
    violations = observation.records("violations") or ()
    unknowns = [
        record
        for record in observation.records("unknowns") or ()
        if record.kind.startswith("boundary")
    ]
    if proven:
        assert len(violations) == 3
        assert not unknowns
    else:
        assert not violations
        assert unknowns, "An unresolved export must remain UNKNOWN beside a typed local function"
    if typed_origin:
        assert not [
            record
            for record in observation.records("symbols") or ()
            if record.data.get("facade_types")
        ]
