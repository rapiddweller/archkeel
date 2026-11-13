# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Compare provider headers and member protection before convergence (AD-410)."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any

from test_collector_native_python_parse import _minor
from test_collector_native_python_proofs import _same

from archkeel.analyzer.python import source as s
from archkeel.analyzer.python.imports import collect_imports


def _python(root: Path, rel: str) -> dict[str, Any] | None:
    namespace = Path(rel).parts[0].removesuffix(".py")
    parsed = s.parse_sources([root / rel], root=root, namespace=namespace)
    if not parsed.modules:
        return None
    m = parsed.modules[0]
    collect_imports([m], {m.module}, {}, namespace=namespace)

    def sites(nodes: Any) -> list[list[int]]:
        return sorted([*s.location(n)] for n in nodes)

    def pairs(values: Any) -> list[list[str]]:
        return sorted([*p] for p in values)

    unsafe = frozenset({m.module})
    classes = []
    for n in m.all_nodes:
        if isinstance(n, ast.ClassDef):
            classes.append(
                [n.lineno, {
                    "typed_header": s.typed_dict_header_static(m, n, unsafe),
                    "base_operands": s._class_base_operands_static(m, n),
                    "creation": [s.class_creation_static(m, n, owner_exposure_only=b,
                                                        unsafe_providers=unsafe)
                                 for b in (False, True)],
                    "dataclass": s.native_dataclass_header_static(m, n, unsafe),
                    "native": s.native_owner_creation_static(m, n, unsafe),
                    "generic": [s._native_generic_base_static(m, base, n, unsafe)
                                for base in n.bases],
                }]
            )
    modes = []
    for owner in (False, True):
        contained, namespace_owners = s._contained_member_roots(
            m, m.all_nodes, owner_exposure_only=owner, unsafe_providers=unsafe)
        modes.append({
            "contained": pairs(contained), "namespace_owners": sorted(namespace_owners),
            "unproven": sorted(s.unproven_member_bindings(
                m, owner_exposure_only=owner, unsafe_providers=unsafe)),
            "protected": sites(s._protected_member_references(
                m, m.all_nodes, member_surface=True, owner_exposure_only=owner,
                unsafe_providers=unsafe)),
            "escapes": sites(s.member_escape_references(
                m, m.all_nodes, member_surface=True, owner_exposure_only=owner,
                unsafe_providers=unsafe)),
        })
    constructors = s.proven_constructor_return_candidates(m)
    return {
        "overloads": sorted(s.static_overload_bindings(m)),
        "explicit": sorted(s.explicit_provider_escapes(m)), "classes": classes,
        "owners": [[name, *s.location(node)] for name, node in m._contained_owners],
        "static_containment": pairs(m._static_containment), "modes": modes,
        "types": sites(s._type_reference_nodes(m, s._protected_type_expressions(m.all_nodes))),
        "class_values": sites(s._class_value_expressions(m)),
        "constructors": sorted([[*s.location(n)], pairs(deps)]
                               for n, deps in constructors.items()),
        "typed_providers": sorted(name for name in m.bound_names
                                  if s.native_typed_dict_provider_static(m, name, unsafe)),
        "quoted": [[*s.location(n), s.annotation_text(s.quoted_type_expression(n))]
                   for n in m.all_nodes if isinstance(n, ast.Constant)
                   and isinstance(n.value, str)],
    }


def _native(binary: Path, root: Path, paths: list[str]) -> list[dict[str, Any]]:
    result = subprocess.run(
        [str(binary), "--dump-protection", str(_minor()), str(root)],
        input="".join(f"{p}\n" for p in paths), text=True, capture_output=True,
        timeout=30, check=True,
    )
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_protection_dump_exists(tmp_path: Path, python_dump_binary: Path) -> None:
    (tmp_path / "probe.py").write_text("from typing import TypedDict\nclass C(TypedDict):\n x: int\n")
    rows = _native(python_dump_binary, tmp_path, ["probe.py"])
    assert len(rows) == 1, rows
    assert rows[0]["full_scope"], rows
    _same(rows[0]["data"], _python(tmp_path, "probe.py"), "provider protection")
