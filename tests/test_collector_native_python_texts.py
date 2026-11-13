# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The native CPython view and `ast.unparse` equal the running CPython (AD-377, slice 2a).

For each file the native dump writes the class name of each node of `ast.walk` of each statement
and `ast.unparse` of each expression in that order. The oracle is `ast` of the running interpreter
(run it on 3.11 to 3.14). The fields of an f-string (`FormattedValue`, its text `Constant` values
and its format spec) are no expression of their own for `annotation_text`, so neither side writes
their text. A native gap marker is allowed only where the oracle shows its named cause:
`<Deep>` for a node deeper than `unparse::MAX_DEPTH`, `<Unseen>` for a text with a lone
surrogate, `<Spec312>` on 3.12 for a named escape or a raw spec (AD-377 points 13 to 16).
"""

from __future__ import annotations

import ast
import json
import math
import os
import random
import re
import struct
import subprocess
import threading
from pathlib import Path

import pytest
from first_difference import same
from native_python import _minor

ROOT = Path(__file__).parents[1]
# `unparse::MAX_DEPTH` of the native writer.
MAX_DEPTH = 100


def _native(binary: Path, root: Path, rels: list[str]) -> dict[str, dict[str, list[str]]]:
    completed = subprocess.run(
        [str(binary), "--dump-texts", str(_minor()), str(root)],
        input="".join(f"{rel}\n" for rel in rels),
        capture_output=True,
        text=True,
        check=True,
    )
    rows = [json.loads(line) for line in completed.stdout.split("\n") if line]
    for row in rows:
        if "gap" in row:
            assert row["gap"]["message"] and "kinds" not in row and "texts" not in row
    return {row["file"]: row for row in rows if "gap" not in row}


def _fields_of_fstrings(tree: ast.AST) -> set[int]:
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if type(node).__name__ in {"JoinedStr", "TemplateStr"}:
            values: list[ast.AST] = getattr(node, "values", [])
            skipped.update(id(value) for value in values if isinstance(value, ast.Constant))
        if type(node).__name__ in {"FormattedValue", "Interpolation"}:
            skipped.add(id(node))
            spec = getattr(node, "format_spec", None)
            if spec is not None:
                skipped.add(id(spec))
    return skipped


def _text(node: ast.expr) -> str:
    try:
        return ast.unparse(node)
    except ValueError:
        return "<Invalid>"
    except RecursionError:
        return "<RecursionError>"


class _Oracle:
    """The CPython walk of one module: the class names, the texts, and the node of each text."""

    def __init__(self, tree: ast.Module, source: str) -> None:
        skipped = _fields_of_fstrings(tree)
        self.source = source
        self.kinds: list[str] = []
        self.texts: list[str] = []
        self.nodes: list[ast.expr] = []
        for statement in tree.body:
            for node in ast.walk(statement):
                self.kinds.append(type(node).__name__)
                if isinstance(node, ast.expr) and id(node) not in skipped:
                    self.texts.append(_text(node))
                    self.nodes.append(node)
        self.depths = _depths(tree, skipped)

    def allowed(self, found: str, index: int) -> bool:
        """A native gap marker is allowed only where the oracle shows its named cause."""
        node = self.nodes[index]
        if found == "<Deep>":
            return self.depths[id(node)] > MAX_DEPTH
        if found == "<Unseen>":
            text = self.texts[index]
            # The text spells the surrogate as an escape, or (in a 3.12+ spec) holds it raw.
            raw = any("\ud800" <= character <= "\udfff" for character in text)
            return raw or _SURROGATE.search(text) is not None
        if found == "<Spec312>":
            segment = ast.get_source_segment(self.source, node) or ""
            return _minor() == 12 and _spec_cause(segment)
        return False


_SURROGATE = re.compile(r"\\ud[89a-f][0-9a-f]{2}")
_RAW_FSTRING = re.compile(r"(?i)(?:rf|fr)['\"]")


def _spec_cause(segment: str) -> bool:
    """A named escape in a spec, or a backslash in a raw f-string: what 3.12 reads its own way."""
    return "\\N{" in segment or (_RAW_FSTRING.search(segment) is not None and "\\" in segment)


def _depths(tree: ast.Module, skipped: set[int]) -> dict[int, int]:
    """The expression levels of each node as the native writer counts them, without recursion."""
    depths: dict[int, int] = {}
    order: list[ast.AST] = []
    pending: list[ast.AST] = [tree]
    while pending:
        node = pending.pop()
        order.append(node)
        pending.extend(ast.iter_child_nodes(node))
    for node in reversed(order):
        below = max((depths[id(child)] for child in ast.iter_child_nodes(node)), default=0)
        counted = isinstance(node, ast.expr) and id(node) not in skipped
        depths[id(node)] = below + (1 if counted else 0)
    return depths


def _compare(found: dict[str, list[str]], oracle: _Oracle, label: object) -> int:
    shared = found["texts"][: len(oracle.texts)]
    texts = [
        oracle.texts[index] if oracle.allowed(text, index) else text
        for index, text in enumerate(shared)
    ]
    texts += found["texts"][len(texts) :]
    # A 3.12 spec gap names a node whose CPython kind differs (a `Constant` spec).
    spec_gap = any(
        text == "<Spec312>" and oracle.allowed(text, index) for index, text in enumerate(shared)
    )
    if not spec_gap:
        same("\n".join(found["kinds"]), "\n".join(oracle.kinds), (label, "kinds"))
    same("\n".join(texts), "\n".join(oracle.texts), (label, "texts"))
    return len(texts)


def _parsed(path: Path) -> _Oracle | None:
    try:
        source = path.read_bytes().decode("utf-8")
        return _Oracle(ast.parse(source), source)
    except (SyntaxError, UnicodeDecodeError, ValueError, MemoryError, RecursionError):
        return None


def _tree_equal(binary: Path, root: Path) -> int:
    rels = sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*.py")
        if path.is_file() and not path.is_symlink()
    )
    native = _native(binary, root, rels)
    count = 0
    for rel in rels:
        oracle = _parsed(root / rel)
        if oracle is None or rel not in native:
            # A file that one side refuses is the matter of the parse tests (AD-367).
            continue
        count += _compare(native[rel], oracle, rel)
    return count


@pytest.mark.parametrize("tree", ["src", "fixtures"])
def test_each_expression_of_the_tree_has_the_cpython_text(
    tree: str, python_dump_binary: Path
) -> None:
    assert _tree_equal(python_dump_binary, ROOT / tree) > 10_000


def _converted(root: Path, target: Path, newline: bytes) -> Path:
    for path in root.rglob("*.py"):
        if path.is_file() and not path.is_symlink():
            copy = target / path.relative_to(root)
            copy.parent.mkdir(parents=True, exist_ok=True)
            copy.write_bytes(path.read_bytes().replace(b"\n", newline))
    return target


@pytest.mark.parametrize("newline", [b"\r\n", b"\r"], ids=["crlf", "cr"])
def test_the_source_with_other_line_ends_has_the_cpython_text(
    newline: bytes, tmp_path: Path, python_dump_binary: Path
) -> None:
    """A Windows checkout: each line end, also inside a triple-quoted string, is a CR LF."""
    root = _converted(ROOT / "src", tmp_path / "src", newline)
    assert _tree_equal(python_dump_binary, root) > 10_000


@pytest.mark.skipif(
    not os.environ.get("ARCHKEEL_PYTHON_SCOPE_CORPORA"), reason="no corpus is named"
)
def test_each_expression_of_each_named_corpus_has_the_cpython_text(
    python_dump_binary: Path,
) -> None:
    for entry in os.environ["ARCHKEEL_PYTHON_SCOPE_CORPORA"].split(";"):
        _tree_equal(python_dump_binary, Path(entry.split("=")[0]))


# Each probe is one module. The oracle decides; a probe needs no expected text.
PROBES: dict[str, str] = {
    "precedence": "x = (a + b) * c ** -d ** e // (f @ g) % h << i >> j & k ^ l | m\n",
    "boolean": "x = a and (b or c) and not d and (not e) or f\n",
    "compare": "x = a < b <= c is not d not in e == (f > g)\n",
    "unary-power": "x = (-a) ** b, -(a ** b), (not a) == b, ~a.b\n",
    "conditional": "x = (a if b else c) if (d if e else f) else (lambda: g)\n",
    "lambda": "f = lambda a, /, b=1, *c, d, e=(1, 2), **g: (yield)\n",
    "lambda-empty": "f = (lambda: 0), lambda *, a: a, lambda *a: a\n",
    "walrus": "if (n := len(a)) > (m := 2): x = [y := f(z) for z in w]\n",
    "await-yield": "async def f():\n    x = await (yield a)\ndef g():\n    y = (yield from b)\n",
    "starred": "a, *b = c\nf(*a, *[1], **{'x': 1}, **b)\nx = [*a, *b], {*a}, (*a,)\n",
    "subscript": "x = a[1:2, ::3], a[()], a[(1, 2)], a[1:2], a[:], a[b,], a[*b]\n",
    "attribute-int": "x = 1 .real, 1.0.real, True.real, (1).bit_length, 1j.imag\n",
    "dict-set": "x = {}, {**a}, {a: b, **c}, set(), {*()}, {1}, {(1, 2): [3]}\n",
    "comprehensions": (
        "async def f():\n"
        "    x = [a async for a in b if c if d], {a: b for a, b in c}, (a for a in (b, c))\n"
    ),
    "call-generator": "f(a for a in b)\nf(x, (a for a in b))\n",
    "floats": "x = 1e16, 1e15, 0.00001, 0.0001, 1e400, 1.5e-310, 0.1 + 0.2, 1_000.000_1\n",
    "complex": "x = 2j, 1e400j, 0j, 1.5e16j, 3.14J\n",
    "float-ties": "x = 2.98023223876953125e-8, 161852602146008.125, -2.98023223876953125e-8\n",
    "ints": "x = 0x_ff, 0o777, 0b1010, 0xFFFFFFFFFFFFFFFFFFFFFFFF, 1_000, 00\n",
    "big-hex": f"x = 0x{'f' * 3570}\n",
    "big-hex-over": f"x = 0x{'f' * 3600}\n",
    "big-decimal": f"x = {'9' * 4300}\n",
    "strings": "x = 'a', \"b'\", 'c\"', '\\'\"', u'u', 'a' 'b', '\\n\\t\\r\\x00\\x7f'\n",
    "unicode": "x = 'é', '\\u00a0', '\\u200b', '\\U0001F600', '\\u0cf3', '\\U0001e4d0'\n",
    "bytes": "x = b'', b'\\x00\\xff', b\"'\", b'\"', b'\\'\"', rb'\\d'\n",
    "raw": "x = r'\\d+', R'\\n', r'a\\'b'\n",
    "triple": "x = '''a\nb''', \"\"\"c'''\"\"\"\n",
    "fstring-basic": "x = f'{a}', f'{a!r}', f'{a!s:>{w}}', f'{a:}', f'{a!r:}', f''\n",
    "fstring-debug": "x = f'{a=}', f'{ a = }', f'{a=!s}', f'{a=:>3}', f'x{a = !r:^4}y'\n",
    "fstring-join": "x = 'a' f'b{c}' 'd', f'a' 'b', '' f'', f'{a}' ''\n",
    "fstring-braces": "x = f'{{}}', f'{{{a}}}', f'{a:{{b}}}', f'{ {a: 1}[a] }'\n",
    "fstring-quotes": "x = f\"{a!r}'\", f'{a}\"', f'''{a}'\"''', f'\\n{a}\\t'\n",
    "fstring-spec-escapes": "x = f'{ab:\\n}', f'{ab:\\\\}', f\"{ab:'}\", f'{ab:\\\"}'\n",
    "fstring-nested-strings": "x = f'{\"a\"}', f\"{'b'}\", f'{a[\"k\"]}', f'{\"\\t\"}'\n",
    # A raw invisible character in a string of a field: 3.11 escapes it, so the text of the
    # field has a backslash and `ast.unparse` raises `ValueError`; 3.12 writes the escape.
    "fstring-raw-invisible": "x = f'{\"\u200b\"}', f'{\"\x01\"}', f'{\"\t\"}'\n",
    # A lone surrogate escape: ruff reads U+FFFD, so native names it (AD-377 point 14).
    "surrogate-fstring": "x = f'\\ud800{a}', f'{ab:\\ud800}', 'b' f'\\udfff', '\\ud800'\n",
    # A raw CR inside a string of each kind: CPython reads a newline (AD-377 point 3).
    "cr-inside-strings": (
        "x = '''a\r\nb'''\r\ny = r'''c\\\r\nd'''\r\nz = b'''e\rf'''\r\n"
        "w = f'''g\r\n{h:>\r\n}'''\r\nv = '''i\\\r\nj'''\r\nu = rb'''k\rl'''\r\n"
    ),
    "xor-and": "x = a ^ b & c, (a ^ b) & c, a & (b ^ c), (a | b) ^ c\n",
    # 3.12 keeps `\N{...}` in a spec as a `Constant` and decodes a raw spec: a gap on 3.12.
    "spec-named-escape": "x = f'{ab:\\N{BULLET}}'\n",
    "spec-raw": "x = rf'{ab:\\n}', rf'{ab:\\\\}', rf'{a:x\\ty}', Rf'{a:>3}'\n",
    "fstring-lambda": "x = f'{(lambda: 1)()}', f'{a if b else c}', f'{(a, b)}'\n",
    "ellipsis-none": "x = ..., None, True, False, [...]\n",
    "slices": "x = a[::], a[1:], a[:2:], a[::-1], a[b:c, d:e]\n",
    "chains": "x = a.b.c(d)(e)[f].g\n",
    "named-in-comprehension": "x = [b for a in c if (b := a)]\n",
    "match-values": (
        "match x:\n    case -1 | 1 + 2j | 'a' | None | Color.RED:\n        pass\n"
        "    case {1: a, **rest}:\n        pass\n    case P(a, b=1):\n        pass\n"
    ),
    "decorators": "@a.b(c)\n@d[e]\n@(lambda f: f)\ndef f(a: T = 1, *b: int) -> list[T]: ...\n",
    "class-header": "class C(B[int], metaclass=M, **kw):\n    x: 'C' = None\n",
    "deep-binop": "x = " + " + ".join(["a"] * (MAX_DEPTH + 5)) + "\n",
    "deep-at-bound": "x = " + "-" * (MAX_DEPTH - 1) + "a\n",
}


def _probe(binary: Path, root: Path, name: str, source: str) -> int:
    root.mkdir(parents=True, exist_ok=True)
    rel = f"{name}.py"
    (root / rel).write_text(source, encoding="utf-8")
    oracle = _parsed(root / rel)
    native = _native(binary, root, [rel])
    if oracle is None:
        assert rel not in native, f"{name}: CPython refuses the probe, native has a tree"
        return 0
    return _compare(native[rel], oracle, name)


@pytest.mark.parametrize(("name", "source"), sorted(PROBES.items()))
def test_each_probe_has_the_cpython_text(
    name: str, source: str, tmp_path: Path, python_dump_binary: Path
) -> None:
    _probe(python_dump_binary, tmp_path, name, source)


def test_a_newer_construct_has_the_cpython_text_of_its_version(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """3.12 type statements and generics, 3.13 type defaults, 3.14 t-strings: a probe of a newer
    version is a syntax error on an older one, and both sides refuse it there."""
    probes = {
        "type-alias": "type A[T] = list[T]\ntype B = int | str\n",
        "generic-class": "class C[T: (int, str), *Ts, **P]:\n    pass\n",
        "type-default": "def f[T = int, *Ts = *tuple[int], **P = [int]](): pass\n",
        "tstring": "x = t'{a}', t'{ a + 1 }', t'{a=}', t'a{b!r:>{w}}c', t'{ (a) }'\n",
        "pep701": "x = f'{'a'}', f'{f'{a}'}', f'{\"\\n\".join(a)}'\n",
        "pep758": "try:\n    pass\nexcept A, B:\n    pass\n",
        "tstring-surrogate": "x = t'\\ud800{a}'\n",
        "tstring-comment": "x = t'''{ a # c\n}'''\n",
        "tstring-line-join": "x = t'{a\\\n}', t'{ a \\\n }'\n",
    }
    for name, source in probes.items():
        _probe(python_dump_binary, tmp_path / name, name, source)


def test_a_deep_expression_is_deep_in_native_and_stops_cpython(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    """Native stops at `MAX_DEPTH` levels (stricter). Deeper, CPython raises `RecursionError`,
    which stops the Python collector without a verdict (AD-377)."""
    source = "x = " + " + ".join(["a"] * 400) + "\n"
    (tmp_path / "deep.py").write_text(source, encoding="utf-8")
    native = _native(python_dump_binary, tmp_path, ["deep.py"])["deep.py"]
    assert native["texts"][1] == "<Deep>"
    errors: list[BaseException] = []

    def work() -> None:
        tree = ast.parse(source)
        assert isinstance(tree.body[0], ast.Assign)
        try:
            ast.unparse(tree.body[0].value)
        except RecursionError as error:
            errors.append(error)

    thread = threading.Thread(target=work)
    thread.start()
    thread.join()
    assert errors, "CPython must stop with RecursionError at 400 levels"


def test_the_printable_table_equals_the_running_cpython(python_dump_binary: Path) -> None:
    """The native delta of `str.isprintable` from Unicode 14 is the one of this interpreter."""
    hidden = [point for point in range(0x110000) if not chr(point).isprintable()]
    ranges: list[str] = []
    start = previous = -2
    for point in [*hidden, -1]:
        if point != previous + 1:
            if start >= 0:
                ranges.append(f"{start:05X}-{previous:05X}")
            start = point
        previous = point
    completed = subprocess.run(
        [str(python_dump_binary), "--dump-printable", str(_minor())],
        capture_output=True,
        text=True,
        check=True,
    )
    same(completed.stdout.strip(), " ".join(ranges), "isprintable")


def test_float_rounding_ties_and_generated_values_have_the_cpython_text(
    tmp_path: Path, python_dump_binary: Path
) -> None:
    rng = random.Random(389)
    values = [2.0**exponent for exponent in range(-1074, 1024)]
    values += [struct.unpack("!d", rng.getrandbits(64).to_bytes(8, "big"))[0] for _ in range(2000)]
    source = "\n".join(f"x = {value!r}" for value in values if math.isfinite(value))
    (tmp_path / "floats.py").write_text(source)
    assert _tree_equal(python_dump_binary, tmp_path) > 8000
