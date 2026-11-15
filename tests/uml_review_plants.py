# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The proof-review plants of AD-526: trees whose joined UML target has a state that 4.0.1 judges.

Consumer: `test_cli_core_uml_review_nested.py`. Each plant states the truth of its UML row."""

from __future__ import annotations

import copy
import json
import os
import subprocess
from pathlib import Path

PROV = ["README.md"]
NOUML = object()  # a mounted contract without `declarations.uml`
PK = {
    "typescript": {
        "a": "app.src.a",
        "b": "app.src.b",
        "deep": "app.src.a.deep",
        "er": "app.src.a.deep.er",
        "c": "app.src.c",
    },
    "python": {
        "a": "app.a",
        "b": "app.b",
        "deep": "app.a.deep",
        "er": "app.a.deep.er",
        "c": "app.c",
    },
}
ONE, TWO, DEEP, T = (
    "app.src.a.one_x2e_ts",
    "app.src.a.two_x2e_ts",
    "app.src.a.deep.d_x2e_ts",
    "app.src.b.t_x2e_ts",
)
THREE, E = "app.src.a.three_x2e_ts", "app.src.a.deep.er.e_x2e_ts"
FILES = {
    "src/a/one.ts": (
        "import { two } from './two';\nimport { t } from '../b/t';\nexport const one = two + t;\n"
    ),
    "src/a/two.ts": "export const two = 2;\n",
    "src/a/deep/d.ts": "export const d = 4;\n",
    "src/b/t.ts": "export const t = 1;\n",
}
NOEDGE = {
    **FILES,
    "src/a/one.ts": "import { t } from '../b/t';\nexport const one = t;\n",
}  # no one -> two
DEEPER = {**FILES, "src/a/deep/er/e.ts": "import { d } from '../d';\nexport const e = d;\n"}
PONE, PTWO, PT, PDEEP = "app.a.one", "app.a.two", "app.b.t", "app.a.deep.d"
PY = {
    "app/__init__.py": "",
    "app/a/__init__.py": "",
    "app/b/__init__.py": "",
    "app/a/deep/__init__.py": "",
    "app/a/one.py": "import app.a.two\nimport app.b.t\n",
    "app/a/two.py": "VALUE = 2\n",
    "app/a/deep/d.py": "D = 4\n",
    "app/b/t.py": "T = 1\n",
}
PY_NOEDGE = {**PY, "app/a/one.py": "import app.b.t\n"}


def component(name, packages, requires=(), **extra):
    return {
        "id": name.upper(),
        "label": name,
        "role": "component",
        "packages": packages,
        "responsibilities": ["Own."],
        "forbidden_responsibilities": [],
        "provenance": PROV,
        "decided_by": "architect",
        "requires": [{"component": o, "rationale": "Use it."} for o in requires],
        **extra,
    }


def ent(identity, name, language="typescript", **more):
    return {
        "id": identity,
        "kind": "module",
        "qualified_name": name,
        "language": language,
        "presence": "planned",
        "provenance": PROV,
        "responsibilities": ["Hold it."],
        **more,
    }


def ref(identity, name, language="typescript"):
    item = ent(identity, name, language, presence="referenced")
    del item["responsibilities"]  # 4.0.1: "Target reference carries definition constraints"
    return item


def pent(identity, name, **more):
    return ent(identity, name, "python", **more)


def imp(source, target, identity=None):
    return {
        "id": identity or f"{source}-{target}",
        "kind": "imports",
        "source_id": source,
        "target_id": target,
        "provenance": PROV,
    }


def scope(entity, entity_kinds, relationship_kinds):
    return {
        "scope_id": entity,
        "mode": "closed",
        "rationale": "Keep it closed.",
        "provenance": PROV,
        "entity_kinds": entity_kinds,
        "relationship_kinds": relationship_kinds,
    }


def target(entities, relationships=None, scopes=None):
    return {
        "schema_version": "1.1.0",
        "entities": entities,
        "relationships": relationships or [],
        "scopes": scopes or [],
    }


def doc(components, uml):
    out = {"schema_version": "2.2.0", "components": components, "rules": []}
    if uml is not NOUML:
        out["declarations"] = {"uml": uml}
    return out


class Plant:
    def __init__(
        self,
        truth,
        note="",
        lang="typescript",
        files=None,
        root=None,
        inside=None,
        deeper=None,
        deepest=None,
        sib=None,
        edit=None,
        links=(),
        after=None,
    ):
        self.truth, self.note, self.lang = truth, note, lang
        self.files = dict(files if files is not None else (FILES if lang == "typescript" else PY))
        self.root, self.inside, self.deeper, self.deepest, self.sib = (
            root,
            inside,
            deeper,
            deepest,
            sib,
        )
        self.edit, self.links, self.after = edit, links, after

    def contracts(self):
        pk = PK[self.lang]
        a, b = component("a", [pk["a"]], ("b",)), component("b", [pk["b"]])
        out = {}
        if self.inside is not None:
            a["inside"] = "inside.json"
            ax = component("ax", [pk["a"]])
            if self.deeper is not None:
                ax["inside"] = "deeper.json"
                ay = component("ay", [pk["deep"]])
                if self.deepest is not None:
                    ay["inside"] = "deepest.json"
                    out["deepest.json"] = doc([component("az", [pk["er"]])], self.deepest)
                out["deeper.json"] = doc([ay], self.deeper)
            out["inside.json"] = doc([ax], self.inside)
        if self.sib is not None:
            b["inside"] = "sib.json"
            out["sib.json"] = doc([component("bx", [pk["b"]])], self.sib)
        rule = {
            "id": "REQUIRES",
            "kind": "complete_requires",
            "rationale": "Keep it.",
            "provenance": PROV,
            "decided_by": "architect",
        }
        rootc = {"schema_version": "2.2.0", "components": [a, b], "rules": [rule]}
        if self.root is not None:
            rootc["declarations"] = {"uml": self.root}
        out["architecture-contract.json"] = rootc
        out = copy.deepcopy(out)
        if self.edit:
            self.edit(out)
        return out


A_TARGET = target([ent("one", ONE), ent("two", TWO)], [imp("one", "two")])
PA_TARGET = target([pent("one", PONE), pent("two", PTWO)], [imp("one", "two")])
ROOT_T = target([ent("t", T)])


def _set(name, value):
    def edit(out):
        out[name] = value

    return edit


def _dotdot(out):
    out["architecture-contract.json"]["components"][0]["inside"] = "sub/../inside.json"


def _moved(out):
    out["real/inside.json"] = out.pop("inside.json")


def _twice(out):
    comps = out["architecture-contract.json"]["components"]
    comps.append(component("c", ["app.src.c"], inside="inside.json"))


def _narrow(out):
    out["inside.json"]["components"][0]["packages"] = ["app.src.a.deep"]
    out["deeper.json"]["components"][0]["packages"] = ["app.src.a.deep.er"]


def _narrow_ax(out):
    out["inside.json"]["components"][0]["packages"] = ["app.src.a.deep"]


def _claims_b(out):
    out["inside.json"]["components"][0]["packages"] = ["app.src.b"]


def _unreadable(root):
    os.chmod(root / "inside.json", 0)


PLANTS = {
    "c-nested-equal": Plant("PASS", "control", inside=A_TARGET),
    "link-ref-carries-constraints": Plant(
        "!PASS",
        "root defines one; nested REFERENCES one with responsibilities; every edge exists",
        root=target([ent("one", ONE), ent("t", T)], [imp("one", "t")]),
        inside=target(
            [ent("one", ONE, presence="referenced"), ent("two", TWO)], [imp("one", "two")]
        ),
    ),
    "link-ref-carries-constraints-3-levels": Plant(
        "!PASS",
        "level 2 defines d; level 3 references d with responsibilities",
        files=DEEPER,
        inside=A_TARGET,
        deeper=target([ent("d", DEEP)]),
        deepest=target([ent("e", E), ent("d", DEEP, presence="referenced")], [imp("e", "d")]),
    ),
    "py-link-ref-carries-constraints": Plant(
        "!PASS",
        "as the first in Python",
        lang="python",
        root=target([pent("one", PONE), pent("t", PT)], [imp("one", "t")]),
        inside=target(
            [pent("one", PONE, presence="referenced"), pent("two", PTWO)], [imp("one", "two")]
        ),
    ),
    "link-ref-owns-open-scope": Plant(
        "!PASS",
        "root defines one; nested references one and puts an OPEN scope on the reference",
        root=target([ent("one", ONE)]),
        inside=target(
            [ref("one", ONE), ent("two", TWO)],
            scopes=[{**scope("one", ["module"], []), "mode": "open"}],
        ),
    ),
    "link-ref-owner-differs": Plant(
        "!PASS",
        "root defines one without a parent; the nested reference of one has parent_id two",
        root=target([ent("one", ONE)]),
        inside=target(
            [{**ref("one", ONE), "parent_id": "two"}, ent("two", TWO)], [imp("one", "two")]
        ),
    ),
    "link-same-edge-in-two-contracts": Plant(
        "PASS?",
        "root draws one->t; nested draws one(ref)->t(ref) again; the edge exists",
        root=target([ent("one", ONE), ent("t", T)], [imp("one", "t")]),
        inside=target([ref("one", ONE), ref("t", T)], [imp("one", "t")]),
    ),
    "link-open-scope-on-definition": Plant(
        "PASS?",
        "control: an OPEN scope on a nested definition",
        inside=target([ent("one", ONE)], scopes=[{**scope("one", ["module"], []), "mode": "open"}]),
    ),
    "three-levels-narrow-equal": Plant(
        "PASS",
        "control: level 2 mounts on ax=a.deep, level 3 on ay=a.deep.er",
        files=DEEPER,
        edit=_narrow,
        inside=A_TARGET,
        deeper=target([ent("d", DEEP)]),
        deepest=target([ent("e", E)]),
    ),
    "three-levels-outside-at-2": Plant(
        "UNKNOWN",
        "level 2 (domain a.deep) defines a.two (AD-526 rule)",
        files=DEEPER,
        edit=_narrow,
        inside=target([ent("one", ONE)]),
        deeper=target([ent("d", DEEP), ent("two", TWO)]),
        deepest=target([ent("e", E)]),
    ),
    "three-levels-outside-at-3": Plant(
        "UNKNOWN",
        "level 3 (domain a.deep.er) defines a.deep.d (AD-526 rule)",
        files=DEEPER,
        edit=_narrow,
        inside=A_TARGET,
        deeper=NOUML,
        deepest=target([ent("e", E), ent("d", DEEP)]),
    ),
    "three-levels-outside-at-3-level-2-empty": Plant(
        "UNKNOWN",
        "as above with an empty target at level 2",
        files=DEEPER,
        edit=_narrow,
        inside=A_TARGET,
        deeper=target([]),
        deepest=target([ent("e", E), ent("d", DEEP)]),
    ),
    "three-levels-outside-at-3-in-sibling": Plant(
        "UNKNOWN",
        "level 3 (domain a.deep.er) defines b.t (AD-526 rule)",
        files=DEEPER,
        edit=_narrow,
        inside=A_TARGET,
        deeper=target([ent("d", DEEP)]),
        deepest=target([ent("e", E), ent("t", T)]),
    ),
    "sibling-outside": Plant(
        "UNKNOWN",
        "mount b defines a.deep.d (AD-526 rule)",
        inside=A_TARGET,
        sib=target([ent("d", DEEP)]),
    ),
    "sibling-outside-after-deep": Plant(
        "UNKNOWN",
        "mounts a, a:ax, b; mount b defines a.deep.er.e",
        files=DEEPER,
        inside=A_TARGET,
        deeper=target([ent("d", DEEP)]),
        sib=target([ent("e", E)]),
    ),
    "sibling-outside-first-mount-without-target": Plant(
        "UNKNOWN",
        "mount a has no target; mount b defines a.deep.d",
        inside=NOUML,
        sib=target([ent("d", DEEP)]),
    ),
}


def write(root: Path, plant: Plant) -> Path:
    graph = (
        "# Provenance\n\n<!-- archkeel-component-graph -->\n```mermaid\nflowchart LR\n"
        '    n_0["a"]\n    n_1["b"]\n    n_0 --> n_1\n```\n'
    )
    files = {"README.md": graph, **plant.files}
    if plant.lang == "typescript":
        files["tsconfig.json"] = '{"compilerOptions": {"strict": true}}\n'
        scan = (
            'language = "typescript"\nroots = ["src"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\ntsconfig = "tsconfig.json"\n'
        )
    else:
        files["pyproject.toml"] = (
            '[project]\nname = "app"\nversion = "0"\nrequires-python = ">=3.11"\n'
        )
        scan = (
            'language = "python"\nroots = ["app"]\nnamespace = "app"\n'
            'contract = "architecture-contract.json"\n'
        )
    files["archkeel.toml"] = "[scan]\n" + scan
    for name, value in plant.contracts().items():
        files[name] = value if isinstance(value, str) else json.dumps(value, indent=1)
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    for name, to in plant.links:
        os.symlink(to, root / name)
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    for step in (["init", "-q"], ["add", "-A"], ["commit", "-qm", "init"]):
        subprocess.run(["git", "-C", str(root), *step], check=True, env=env)
    if plant.after:
        plant.after(root)
    return root
