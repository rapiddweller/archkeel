# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Explore reads native Core ownership, sites and findings without deciding permissions."""

import json

from test_target_graph import _repository

from archkeel.check.report import run_report
from archkeel.cli.observe import observe
from archkeel.ir.codec import decode_canonical_model, parse_observation
from archkeel.ir.module_explore import module_exploration


def _sample(
    tmp_path,
    *,
    ambiguous=False,
    unowned_importer=False,
    own_importer=False,
    permitted=False,
    extra_files=None,
    core_exact=(),
    peer_exact=(),
    uml=False,
    other_component=False,
    other_requires_core=False,
    extra_rules=(),
    complete_requires=True,
    rule_include_type_checking=True,
    core_public=None,
):
    root, config = _repository(tmp_path)
    contract = json.loads((root / config.contract).read_bytes())
    contract.pop("declarations")
    contract["components"][0]["requires"] = []
    contract["components"][0]["exact_modules"] = list(core_exact)
    if core_public is not None:
        contract["components"][0]["public"] = list(core_public)
    peer = dict(contract["components"][0])
    peer.update(id="peer", label="peer", packages=["sample.peer"], namespace="sample.peer")
    peer["requires"] = [{"component": "core", "rationale": "Read the core interface."}]
    if not permitted:
        peer["requires"] = []
    peer["exact_modules"] = list(peer_exact)
    contract["components"].append(peer)
    if other_component:
        other = dict(contract["components"][0])
        other.update(
            id="other",
            label="other",
            packages=["sample.other"],
            namespace="sample.other",
            exact_modules=[],
            requires=(
                [{"component": "core", "rationale": "Read the core interface."}]
                if other_requires_core
                else []
            ),
        )
        contract["components"].append(other)
    if ambiguous:
        contract["components"][0].pop("namespace")
        contract["components"].append(
            dict(contract["components"][0], id="overlap", label="overlap")
        )
    rules = []
    if complete_requires:
        rule = {
            "id": "dependencies",
            "kind": "complete_requires",
            "rationale": "Each crossing must be explicitly granted.",
            "provenance": ["docs/target.md"],
            "decided_by": "architect",
        }
        if not rule_include_type_checking:
            rule["include_type_checking"] = False
        rules.append(rule)
    contract["rules"] = rules + list(extra_rules)
    if uml:
        contract["declarations"] = {
            "uml": {
                "schema_version": "1.0.0",
                "entities": [
                    {
                        "id": name + "-module",
                        "kind": "module",
                        "qualified_name": "sample." + name,
                        "parent_id": name,
                        "language": "python",
                        "presence": "planned",
                        "responsibilities": ["Own the module."],
                        "provenance": ["docs/target.md"],
                    }
                    for name in ("core", "peer")
                ],
                "scopes": [
                    {
                        "scope_id": "peer-module",
                        "mode": "closed",
                        "relationship_kinds": ["imports"],
                        "rationale": "Declare each module import.",
                        "provenance": ["docs/target.md"],
                    }
                ],
            }
        }
    (root / config.contract).write_text(json.dumps(contract))
    (root / "sample/peer.py").write_text("import sample.core\nimport sample.core\n")
    (root / "sample/unowned.py").write_text("import sample.core\n" if unowned_importer else "")
    if own_importer:
        (root / "sample/core.py").write_text("import sample.core\n")
    for path, text in (extra_files or {}).items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(text)
    _, encoded = run_report(root, config=config, analyzer=observe)
    assert encoded is not None
    return parse_observation(decode_canonical_model(json.loads(encoded)))


def _root(model):
    return next(level for level in module_exploration(model) if level.parent_id is None)
