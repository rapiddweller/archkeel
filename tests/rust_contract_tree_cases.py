# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""AD-366: the trees of the parity test of the Rust inside-contract tree.

A tree is the path of the root contract and a map from repository paths to bytes. The root
contract is in the map. The repository trees come from each root contract of the repository that
mounts an inside contract. The hostile trees change a small tree in one way.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from archkeel.ir.codec import load_inside_contract_tree, parse_contract
from archkeel.ir.codec_wire import decode_json
from archkeel.ir.model import contract_relative_path

Tree = tuple[str, str, dict[str, bytes]]
"""The name of the case, the root path and the bytes of each path."""

ROOT = Path(__file__).parents[1]


def identity(reference: str) -> str | None:
    """The repository path that a reference names, as `_contract_identity` makes it."""
    relative = contract_relative_path(reference)
    return relative.as_posix() if relative is not None and relative.parts else None


def _encode(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def _repository_tree(name: str, base: Path, root_path: str) -> Tree:
    files: dict[str, bytes] = {root_path: (base / root_path).read_bytes()}

    def read(reference: str) -> tuple[bytes, str]:
        key = identity(reference)
        if key is None or not (base / key).is_file():
            raise ValueError("missing")
        target = base / key
        files[key] = target.read_bytes()
        return files[key], reference

    root_bytes = files[root_path]
    load_inside_contract_tree(
        root_path, parse_contract(decode_json(root_bytes)), "", root_path, read
    )
    return name, root_path, files


def repository_trees() -> list[Tree]:
    """Each root contract of the repository that mounts an inside contract."""
    roots = [ROOT / "architecture-contract.json", *sorted(ROOT.glob("fixtures/*/*.json"))]
    trees = []
    for path in roots:
        try:
            document = json.loads(path.read_bytes())
        except ValueError:
            continue
        components = document.get("components") if isinstance(document, dict) else None
        if isinstance(components, list) and any(
            isinstance(item, dict) and "inside" in item for item in components
        ):
            name = path.relative_to(ROOT).as_posix()
            trees.append(_repository_tree(name, path.parent, path.name))
    return trees


def component(label: str, inside: str | None = None, **extra: Any) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": f"C-{label}",
        "label": label,
        "role": "component",
        "packages": [f"p.{label}"],
        "responsibilities": [f"Own {label}."],
        "forbidden_responsibilities": [],
        "provenance": [f"docs/{label}.md"],
    }
    if inside is not None:
        item["inside"] = inside
    item.update(extra)
    return item


def contract(*components: dict[str, Any], version: str = "3.14.0") -> dict[str, Any]:
    return {"schema_version": version, "components": list(components), "rules": []}


def _rule(identity: str) -> dict[str, Any]:
    return {
        "id": identity,
        "kind": "complete_requires",
        "rationale": "Every import is declared.",
        "provenance": ["docs/rule.md"],
        "decided_by": "architect",
    }


def _base() -> dict[str, dict[str, Any]]:
    """A root with two mounts; the first mount has one mount of its own."""
    root = contract(component("a", "a/inside.json"), component("b", "b/inside.json"))
    root["rules"] = [_rule("R-root")]
    first = contract(component("x", "a/x/inside.json"), component("y"))
    first["rules"] = [_rule("R-inner")]
    return {
        "architecture-contract.json": root,
        "a/inside.json": first,
        "a/x/inside.json": contract(component("deep")),
        "b/inside.json": contract(component("z"), version="3.0.0"),
    }


Edit = Callable[[dict[str, Any]], None]


def _inside(path: str, index: int, value: str | None) -> Edit:
    def edit(files: dict[str, Any]) -> None:
        item = files[path]["components"][index]
        if value is None:
            item.pop("inside", None)
        else:
            item["inside"] = value

    return edit


def _put(path: str, value: Any) -> Edit:
    def edit(files: dict[str, Any]) -> None:
        files[path] = value

    return edit


def _drop(path: str) -> Edit:
    return lambda files: files.pop(path)


def _set(path: str, keys: list[str | int], value: Any) -> Edit:
    def edit(files: dict[str, Any]) -> None:
        target = files[path]
        for key in keys[:-1]:
            target = target[key]
        target[keys[-1]] = value

    return edit


def _declarations(path: str, key: str, value: Any) -> Edit:
    def edit(files: dict[str, Any]) -> None:
        files[path].setdefault("declarations", {})[key] = value

    return edit


ROOT_PATH = "architecture-contract.json"
_MODULE = {"path": "src/a.py", "responsibility": "Own a."}
_CAPABILITY = {
    "id": "CAP-1",
    "name": "c",
    "label": "C",
    "review_order": 1,
    "provenance": ["docs/c.md"],
}
_DUPLICATE_KEY = (
    b'{"schema_version": "3.0.0", "schema_version": "3.0.0", "components": [], "rules": []}'
)
HOSTILE: dict[str, list[Edit]] = {
    "base": [],
    "empty tree": [_inside(ROOT_PATH, 0, None), _inside(ROOT_PATH, 1, None)],
    "missing mount": [_drop("b/inside.json")],
    "missing nested mount": [_drop("a/x/inside.json")],
    "mount with dot dot": [_inside(ROOT_PATH, 1, "a/../b/inside.json")],
    "mount with leading dot dot": [_inside(ROOT_PATH, 1, "../b/inside.json")],
    "mount with trailing slash": [_inside(ROOT_PATH, 1, "b/inside.json/")],
    "mount with dot segment": [_inside(ROOT_PATH, 1, "b/./inside.json")],
    "mount with double slash": [_inside(ROOT_PATH, 1, "b//inside.json")],
    "mount with backslash": [_inside(ROOT_PATH, 1, "b\\inside.json")],
    "mount with colon": [_inside(ROOT_PATH, 1, "b:inside.json")],
    "mount with nul": [_inside(ROOT_PATH, 1, "b/inside\x00.json")],
    "absolute mount": [_inside(ROOT_PATH, 1, "/b/inside.json")],
    "empty mount": [_inside(ROOT_PATH, 1, "")],
    "dot mount": [_inside(ROOT_PATH, 1, ".")],
    "dot slash mount": [_inside(ROOT_PATH, 1, "./")],
    "case variant mount": [_inside(ROOT_PATH, 1, "B/inside.json")],
    "unicode variant mount": [
        _inside(ROOT_PATH, 1, "b/insidé.json"),
        _put("b/insidé.json", contract(component("z"))),
    ],
    "unicode mount": [
        _inside(ROOT_PATH, 1, "b/insidé.json"),
        _put("b/insidé.json", contract(component("zé"))),
        _drop("b/inside.json"),
    ],
    "duplicate mount": [_inside(ROOT_PATH, 1, "a/inside.json")],
    "duplicate mount by alias": [_inside(ROOT_PATH, 1, "a/./inside.json")],
    "duplicate nested mount": [
        _set("b/inside.json", ["components", 0, "inside"], "a/x/inside.json")
    ],
    "cycle to root": [_inside(ROOT_PATH, 1, ROOT_PATH)],
    "cycle to parent": [_set("a/x/inside.json", ["components", 0, "inside"], "a/inside.json")],
    "self cycle": [_set("b/inside.json", ["components", 0, "inside"], "b/inside.json")],
    "invalid inside bytes": [_put("b/inside.json", b"{not json")],
    "inside of unknown version": [_set("b/inside.json", ["schema_version"], "9.9.9")],
    "inside of old version": [_set("b/inside.json", ["schema_version"], "2.2.0")],
    "inside with repeated label": [
        _set("b/inside.json", ["components"], [component("z"), component("z")])
    ],
    "inside not an object": [_put("b/inside.json", [])],
    "inside with duplicate key": [_put("b/inside.json", _DUPLICATE_KEY)],
    "inside with capabilities": [_declarations("b/inside.json", "capabilities", [_CAPABILITY])],
    "inside with context roots": [
        _declarations("b/inside.json", "context_roots", ["src"]),
        _declarations("b/inside.json", "context_roots_provenance", ["docs/c.md"]),
    ],
    "nested under unsupported": [
        _declarations("a/inside.json", "capabilities", [_CAPABILITY]),
    ],
    "declaration ID collision": [
        _set("a/inside.json", ["components", 1, "id"], "y"),
        _set(ROOT_PATH, ["components", 1, "id"], "a:y"),
    ],
    "rule ID collision": [_set(ROOT_PATH, ["rules", 0, "id"], "a:R-inner")],
    "parent ID collision with root label": [
        _set(
            ROOT_PATH,
            ["components"],
            [
                component("a", "a/inside.json"),
                component("b", "b/inside.json"),
                component("a:x", None),
            ],
        )
    ],
    "parent ID at two places": [
        _set("a/inside.json", ["components", 1], component("x:y", "c/inside.json")),
        _set("a/x/inside.json", ["components", 0], component("y", "d/inside.json")),
        _put("c/inside.json", contract(component("c"))),
        _put("d/inside.json", contract(component("d"))),
    ],
    "duplicate module target": [
        _declarations(ROOT_PATH, "modules", [_MODULE]),
        _declarations("b/inside.json", "modules", [_MODULE]),
    ],
    "duplicate module target in two insides": [
        _declarations("a/x/inside.json", "modules", [_MODULE]),
        _declarations("b/inside.json", "modules", [_MODULE]),
    ],
    "extra unmounted contract": [_put("c/inside.json", contract(component("c")))],
    "provenance paths": [
        _set("b/inside.json", ["components", 0, "provenance"], ["docs/z.md", "docs/a.md"])
    ],
}


def _uml_inside(files: dict[str, Any]) -> None:
    from rust_contract_graph_cases import base

    target = base()
    files["b/inside.json"] = target


HOSTILE["uml inside"] = [_uml_inside]

_PROVENANCE = ["docs/c.md"]
_INTERFACE = {
    "id": "R-IFACE",
    "kind": "interface_boundary",
    "include_type_checking": True,
    "rationale": "r",
    "provenance": _PROVENANCE,
    "decided_by": "architect",
}
# One value of each declaration that only a root may hold, with what its parser needs beside it.
ROOT_ONLY: dict[str, tuple[Any, dict[str, Any]]] = {
    "capabilities": ([_CAPABILITY], {}),
    "review_scopes": (
        [
            {
                "id": "RS-1",
                "label": "Review",
                "parent_id": "CAP-1",
                "subjects": ["p.z"],
                "provenance": _PROVENANCE,
            }
        ],
        {"capabilities": [_CAPABILITY]},
    ),
    "public_api": (["p.z:Thing"], {"public_api_provenance": _PROVENANCE}),
    "public_api_provenance": (_PROVENANCE, {"public_api": ["p.z:Thing"]}),
    "public_commands": (
        [{"id": "CMD-1", "command": "p.z:main", "description": "Run.", "provenance": _PROVENANCE}],
        {},
    ),
    "context_roots": (["p"], {"context_roots_provenance": _PROVENANCE}),
    "context_roots_provenance": (_PROVENANCE, {"context_roots": ["p"]}),
    "paths": (
        [
            {
                "id": "PATH-1",
                "label": "Run",
                "kind": "read",
                "steps": ["p.z"],
                "provenance": _PROVENANCE,
            }
        ],
        {},
    ),
    "spot_owners": (
        [
            {
                "id": "OWNER-1",
                "label": "Owner",
                "owner": "p.z",
                "responsibility": "Own z.",
                "provenance": _PROVENANCE,
            }
        ],
        {},
    ),
    "compat": ([{"module": "p.old", "target": "p.z", "lifetime": "migration"}], {}),
    "measurement_budgets": ([{"name": "cycle_edges", "provenance": _PROVENANCE}], {}),
    "facade_budgets": ([{"component": "z", "max_names": 3, "provenance": _PROVENANCE}], {}),
    "coupling_budgets": (
        [{"source": "z", "target": "y2", "max_names": 2, "provenance": _PROVENANCE}],
        {},
    ),
}


def _root_only(field: str) -> Edit:
    value, companions = ROOT_ONLY[field]

    def edit(files: dict[str, Any]) -> None:
        inside = contract(component("z", public=["p.z.api"]), component("y2", public=["p.y2.api"]))
        inside["rules"] = [_INTERFACE]
        inside["declarations"] = {field: value, **companions}
        files["b/inside.json"] = inside

    return edit


for _field in ROOT_ONLY:
    HOSTILE[f"inside with {_field}"] = [_root_only(_field)]
HOSTILE["review scope ID of the root"] = [
    _root_only("review_scopes"),
    _set(ROOT_PATH, ["components", 1, "id"], "RS-1"),
]
HOSTILE["chain at the depth bound"] = []
HOSTILE["chain one level deeper"] = []
HOSTILE["uml ID collision"] = [_uml_inside, _set(ROOT_PATH, ["components", 1, "id"], "b:E-K")]


def _bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else _encode(value)


def _chain(depth: int) -> dict[str, Any]:
    """The root mounts d/0.json, and each file mounts the next one."""
    names = [f"d/{level}.json" for level in range(depth)]
    files: dict[str, Any] = {ROOT_PATH: contract(component("c", names[0]))}
    for level, name in enumerate(names):
        following = names[level + 1] if level + 1 < depth else None
        files[name] = contract(component("c", following))
    return files


def hostile_trees() -> list[Tree]:
    trees = []
    for name, edits in HOSTILE.items():
        files: dict[str, Any] = copy.deepcopy(_base())
        if name == "chain at the depth bound":
            files = _chain(900)
        if name == "chain one level deeper":
            files = _chain(901)
        for edit in edits:
            edit(files)
        trees.append((name, ROOT_PATH, {path: _bytes(value) for path, value in files.items()}))
    for name, link, target in LINK_CASES:
        files = copy.deepcopy(_base())
        if name == "link to a mounted file":
            files[ROOT_PATH]["components"][1]["inside"] = link
        else:
            files["b/inside.json"]["components"][0]["inside"] = link
        encoded = {path: _bytes(value) for path, value in files.items()}
        if target in encoded:
            encoded[link] = encoded[target]
        else:
            encoded[link] = _bytes(contract(component("q")))
        trees.append((name, ROOT_PATH, encoded))
    return trees


# A symbolic link: the case, the link path and the path that the shell resolves it to.
LINK_CASES = [
    ("link to a mounted file", "a/x/alias.json", "a/x/inside.json"),
    ("link to an unmounted file", "b/alias.json", "b/other.json"),
    ("link out of the repository", "b/out.json", "../outside.json"),
]
LINKS = {link: target for _, link, target in LINK_CASES}


def generated_trees(seed: int = 880, count: int = 300) -> list[Tree]:
    """Random trees: each component may mount any path of a small set, safe or not."""
    import random

    generator = random.Random(seed)
    references = [
        "m/0.json",
        "m/1.json",
        "m/2.json",
        "m/3.json",
        "m/./1.json",
        "m/2.json/",
        "../m/0.json",
        "m/absent.json",
        ROOT_PATH,
    ]
    trees = []
    for number in range(count):
        files: dict[str, Any] = {}
        for path in [ROOT_PATH, "m/0.json", "m/1.json", "m/2.json", "m/3.json"]:
            labels = ["a", "b", "c"][: generator.randint(0, 3)]
            items = [
                component(
                    label,
                    generator.choice(references) if generator.random() < 0.5 else None,
                )
                for label in labels
            ]
            if generator.random() < 0.1 and items:
                items[0]["id"] = generator.choice(["a:C-a", "b:C-b", "C-a"])
            files[path] = contract(*items, version=generator.choice(["3.14.0", "3.0.0"]))
        if generator.random() < 0.1:
            files["m/3.json"] = b"[]"
        trees.append((f"generated {number}", ROOT_PATH, {k: _bytes(v) for k, v in files.items()}))
    return trees
