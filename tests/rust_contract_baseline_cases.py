# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Baseline files, including hostile byte streams, for AD-386 parity."""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path
from typing import Any


def encode(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True).encode()


def entry(**changes: Any) -> dict[str, Any]:
    return {"rules": ["B", "A"], "subjects": ["z", "a", "z"], "count": 2, **changes}


def document(**changes: Any) -> dict[str, Any]:
    return {"schema_version": "1.3.0", "violations": [entry()], "budgets": {}, **changes}


def hostile_cases() -> list[tuple[str, bytes]]:
    cases = []
    wrong = (None, True, False, 0, -1, 1.0, "", [], {}, [1])
    for field in ("schema_version", "violations", "budgets"):
        for value in wrong:
            cases.append((f"root {field} {value!r}", encode(document(**{field: value}))))
        missing = document()
        del missing[field]
        cases.append((f"root missing {field}", encode(missing)))
    for field in ("rules", "subjects", "count", "roles"):
        for value in wrong:
            cases.append(
                (f"entry {field} {value!r}", encode(document(violations=[entry(**{field: value})])))
            )
        missing = entry()
        missing.pop(field, None)
        cases.append((f"entry missing {field}", encode(document(violations=[missing]))))
    for value in (None, True, [], "x", 2):
        cases.append((f"entry not object {value!r}", encode(document(violations=[value]))))
    for where in ("root", "entry", "role"):
        value = document()
        target = value if where == "root" else value["violations"][0]
        if where == "role":
            target["roles"] = [{"source": "a", "target": "b"}]
            target = target["roles"][0]
        target["extra"] = 1
        cases.append((f"unknown {where}", encode(value)))
    for roles in (
        [{"source": "a"}],
        [{"source": 1, "target": "a"}],
        [{"source": "a", "target": None}],
        [None],
        [{"source": "a", "target": "b"}] * 2,
        [{"source": "z", "target": "a"}, {"source": "a", "target": "z"}],
    ):
        cases.append((f"roles {roles!r}", encode(document(violations=[entry(roles=roles)]))))
    repeated = [entry(), entry(subjects=["z", "z", "a"], rules=["A", "B"], count=1)]
    cases.append(("duplicate fingerprint", encode(document(violations=repeated))))
    cases.append(("duplicate then invalid", encode(document(violations=[*repeated, None]))))
    cases.append(
        ("duplicate then bad budgets", encode(document(violations=repeated, budgets=None)))
    )
    for kind in (
        "cycle_edges",
        "calls_unresolved",
        "unknown",
        "violations",
        "facade_names",
        "coupling_names",
    ):
        for value in wrong:
            cases.append((f"budget {kind} {value!r}", encode(document(budgets={kind: value}))))
    for key in ("", " ", "\x1c", "\x1f", "\u3000", "\u200b", "é😀"):
        for names in ([], [""], ["b", "a"], ["a", "a"], ["a", "z"], [1], None):
            cases.append(
                (
                    f"names {key!r} {names!r}",
                    encode(document(budgets={"facade_names": {key: names}})),
                )
            )
    for number in (2**64 - 1, 2**64, 10**80, 10**400, -(10**80)):
        cases.append(
            (f"integer count {number}", encode(document(violations=[entry(count=number)])))
        )
        cases.append(
            (f"integer budget {number}", encode(document(budgets={"cycle_edges": number})))
        )
    for schema in ("1.3.1", "2.0.0", " 1.3.0", "1.3.0\x00", "é😀"):
        cases.append((f"unsupported schema {schema!r}", encode(document(schema_version=schema))))
    valid = encode(document())
    cases += [
        ("empty", b""),
        ("space", b" \n"),
        ("null", b"null"),
        ("list", b"[]"),
        ("BOM", b"\xef\xbb\xbf" + valid),
        ("non UTF-8", b"\xff"),
        ("UTF-16", valid.decode().encode("utf-16")),
        ("trailing data", valid + b"{}"),
        ("trailing text", valid + b"x"),
        ("deep root", b"[" * 10000 + b"]" * 10000),
        ("deep unknown", b'{"extra":' + b"[" * 150 + b"]" * 150 + b"}"),
        ("over size", b" " * (16 * 1024 * 1024 + 1) + valid),
        ("duplicate root key", valid[:-1] + b', "budgets": {}}'),
        ("duplicate escaped key", valid[:-1] + b', "budg\\u0065ts": {}}'),
        ("duplicate entry key", valid.replace(b'"count": 2', b'"count": 0, "count": 2')),
        (
            "duplicate budget key",
            encode(document(budgets={"cycle_edges": 1})).replace(
                b'"cycle_edges": 1', b'"cycle_edges": 2, "cycle_edges": 1'
            ),
        ),
        (
            "duplicate role key",
            encode(document(violations=[entry(roles=[{"source": "a", "target": "b"}])])).replace(
                b'"source": "a"', b'"source": "z", "source": "a"'
            ),
        ),
    ]
    for token in (b"NaN", b"Infinity", b"-Infinity", b"1e400", b"1.0", b"2e0"):
        cases.append(
            (f"number token {token!r}", valid.replace(b'"count": 2', b'"count": ' + token))
        )
    for text in (
        b'"\\ud800"',
        b'"\\udc00"',
        b'"\\ud83d\\ude00"',
        b'"a\x01b"',
        b'"\xc0\xaf"',
        b'"\xed\xa0\x80"',
    ):
        cases.append((f"text token {text!r}", valid.replace(b'"z"', text)))
    return cases


def integer_token_cases() -> list[tuple[str, bytes]]:
    cases = []
    for field in (
        "count",
        "cycle_edges",
        "private_crossings",
        "typing_positions",
        "calls_unresolved",
        "untyped_private_accesses",
        "unknown_positions",
    ):
        for token in (
            b"-0",
            b"-0.0",
            b"0.0",
            b"1.0",
            b"1e0",
            b"0e-0",
            b"1e-0",
            b"-0e0",
            b'"-0"',
            b"--0",
            b"-00",
            b"1-0",
            b"-0x",
            b"-0\x0b",
        ):
            value = (
                document(violations=[entry(count=17)])
                if field == "count"
                else document(budgets={field: 17})
            )
            data = encode(value).replace(
                b'"' + field.encode() + b'": 17', b'"' + field.encode() + b'": ' + token
            )
            cases.append((f"integer token {field} {token.decode()}", data))
    return cases


def schema_cases() -> list[tuple[str, bytes]]:
    return [
        (
            f"unlisted schema {major}.{minor}.{patch}",
            encode(document(schema_version=f"{major}.{minor}.{patch}")),
        )
        for major in range(4)
        for minor in range(6)
        for patch in range(4)
        if f"{major}.{minor}.{patch}" not in ("1.0.0", "1.1.0", "1.2.0", "1.3.0")
    ]


def valid_cases() -> list[tuple[str, bytes]]:
    cases = []
    for schema in ("1.0.0", "1.1.0", "1.2.0", "1.3.0"):
        for count in (1, 2, 2**64 - 1):
            value = document(schema_version=schema, violations=[entry(count=count)])
            if schema < "1.2.0":
                del value["budgets"]
            cases.append((f"version {schema} count {count}", encode(value)))
    for rules, subjects in (
        ([], []),
        ([""], [""]),
        (["A", "A"], ["z", "a", "z"]),
        (["é😀", "Z"], ['a\n\x7f\u2028\\"', "😀"]),
    ):
        cases.append(
            (
                f"permissive fingerprint {rules!r} {subjects!r}",
                encode(document(violations=[entry(rules=rules, subjects=subjects)])),
            )
        )
    scalars = (
        "cycle_edges",
        "private_crossings",
        "typing_positions",
        "calls_unresolved",
        "untyped_private_accesses",
        "unknown_positions",
    )
    cases.append(("all scalars", encode(document(budgets=dict.fromkeys(scalars, 17)))))
    cases.append(
        (
            "both keyed kinds",
            encode(
                document(
                    budgets={
                        "facade_names": {"A": ["", "a", "😀"], "B": []},
                        "coupling_names": {"A -> B": ["b"]},
                    }
                )
            ),
        )
    )
    cases.append(
        ("empty keyed kinds", encode(document(budgets={"facade_names": {}, "coupling_names": {}})))
    )
    cases.append(("empty roles", encode(document(violations=[entry(roles=[])]))))
    cases.append(
        (
            "empty role members",
            encode(document(violations=[entry(roles=[{"source": "", "target": ""}])])),
        )
    )
    many = [
        entry(rules=[str(index)], subjects=["gone"], count=index + 1)
        for index in reversed(range(100))
    ]
    cases.append(("100 stale entries retained", encode(document(violations=many))))
    return cases


def repository_cases() -> list[tuple[str, bytes]]:
    """Read tracked files by content, plus each in-memory demo baseline overlay."""
    from fixtures.architecture_demo import CATALOG

    root = Path(__file__).parents[1]
    paths = (
        subprocess.check_output(["git", "ls-files", "-z", "*.json"], cwd=root).decode().split("\0")
    )
    cases = []
    for path in filter(None, paths):
        data = (root / path).read_bytes()
        try:
            value = json.loads(data)
        except (ValueError, UnicodeError):
            if "baseline" in path:
                cases.append((f"file {path}", data))
            continue
        if (
            isinstance(value, dict)
            and "violations" in value
            and "schema_version" in value
            and str(value["schema_version"]).startswith("1.")
        ):
            cases.append((f"file {path}", data))
    for variant in CATALOG:
        for path, text in variant.files.items():
            if text is not None and ("baseline" in path or "known-violations" in path):
                cases.append((f"demo {variant.id}/{path}", text.encode()))
    cases.extend(_literal_test_cases(root))
    return cases


class _Constants(ast.NodeTransformer):
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def visit_Name(self, name: ast.Name) -> ast.AST:
        return ast.Constant(self.values[name.id]) if name.id in self.values else name


def _literal_test_cases(root: Path) -> list[tuple[str, bytes]]:
    """Read literal baseline inputs without running test functions or changing Python."""
    cases = []
    for path in sorted((root / "tests").glob("test_*.py")):
        tree = ast.parse(path.read_text())
        constants = {"BASELINE_SCHEMA_VERSION": "1.3.0", "GETATTR_RULE": "CONSTRUCT-NO-DYNAMIC"}
        constants.update(
            {
                node.targets[0].id: node.value.value
                for node in tree.body
                if isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
            }
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            keys = {key.value for key in node.keys if isinstance(key, ast.Constant)}
            if not {"schema_version", "violations"} <= keys:
                continue
            text = ast.unparse(node)

            # Replace known constant names through the AST, never through eval.
            try:
                value = ast.literal_eval(_Constants(constants).visit(ast.parse(text, mode="eval")))
            except (ValueError, TypeError):
                # A computed input is not a file; the generated parity sets cover that grammar.
                continue
            cases.append((f"test {path.name}:{node.lineno}", encode(value)))
    return cases
