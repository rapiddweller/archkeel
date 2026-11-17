# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The `sites-*` shapes of the scaling tests and the joined shapes that time them (AD-323)."""

from __future__ import annotations

from scaling_shape_kit import Shape, as_bytes, join_lines

SITE_SHAPES: dict[str, Shape] = {
    # Sites (PR 4.3a-2): the scope, the shadowed names and the free names of a site were found by
    # a climb over the ancestors for each node, and a path or a receiver text by a copy of a chain.
    "sites-calls-at-depth": Shape(
        as_bytes(lambda n: "".join(f"function f{i}(){{ c{i}(g{i}); " for i in range(n)) + "}" * n),
        8000,
    ),
    "sites-calls-in-arrow-nest": Shape(
        as_bytes(
            lambda n: (
                "const f = "
                + "".join(f"(p{i}) => {{ var v{i}; c{i}(p{i}, v{i}); return " for i in range(n))
                + "0"
                + "; }" * n
                + ";"
            )
        ),
        5000,
    ),
    "sites-nested-calls": Shape(as_bytes(lambda n: "f(" * n + "x" + ")" * n + ";"), 60000),
    "sites-with-nest": Shape(as_bytes(lambda n: "with (o) { " * n + "f();" + "}" * n), 30000),
    "sites-member-chain-call": Shape(as_bytes(lambda n: "a" + ".b" * n + "();"), 100000),
    "sites-chained-calls": Shape(as_bytes(lambda n: "a" + ".b()" * n + ";"), 5000),
    "sites-calls-with-chains": Shape(
        as_bytes(lambda n: join_lines("a{i}.b.c.d(e{i}.f.g);", n)), 5000
    ),
    "sites-new-expressions": Shape(
        as_bytes(lambda n: join_lines("const v{i} = new A{i}.B(c{i});", n)), 6000
    ),
    "sites-publication-chain": Shape(
        as_bytes(lambda n: "".join(f"window.p{i} = " for i in range(n)) + "1;"), 20000, ".js"
    ),
    "sites-computed-access": Shape(as_bytes(lambda n: "a" + "[k]" * n + ";"), 60000),
    "sites-computed-calls": Shape(as_bytes(lambda n: "a" + "[0]()" * n + ";"), 20000),
    "sites-subscript-flat": Shape(
        as_bytes(lambda n: join_lines("a{i}[b{i}][c{i}](d{i});", n)), 6000
    ),
    "sites-many-free-names": Shape(
        as_bytes(lambda n: "f(" + join_lines("x{i}", n, ", ") + ");"), 40000
    ),
    "sites-many-bound-names": Shape(
        as_bytes(
            lambda n: (
                join_lines("var v{i};", n, " ")
                + "\n"
                + join_lines("function g{i}() { v{i}(); }", n)
            )
        ),
        4000,
    ),
    "sites-free-names-in-frames": Shape(
        as_bytes(lambda n: join_lines("function g{i}(a{i}) { var b{i}; a{i}(b{i}, c{i}); }", n)),
        4000,
    ),
    "sites-args-wide": Shape(
        as_bytes(lambda n: "f(" + join_lines("g{i}(h{i})", n, ", ") + ");"), 12000
    ),
    "sites-escapes": Shape(
        as_bytes(lambda n: join_lines("typeof w{i}; delete o{i}.p; x{i}++; f(g{i}, h{i});", n)),
        3000,
    ),
    "sites-many-shadowed-names": Shape(
        as_bytes(
            lambda n: (
                "function f() { "
                + join_lines("var v{i};", n, " ")
                + " "
                + join_lines("v{i}();", n, " ")
                + " }"
            )
        ),
        12000,
    ),
    # n nested arrow functions that each declare a name, with n sites at the bottom: the names that
    # a site shadows are the union over the chain, and a set for each site was n squared entries.
    "sites-shadow-nest-arrows": Shape(
        as_bytes(
            lambda n: (
                "const f = "
                + "".join(f"(p{i}) => {{ var v{i}; return " for i in range(n))
                + "["
                + join_lines("c{i}(v{i})", n, ", ")
                + "]"
                + "; }" * n
                + ";"
            )
        ),
        2500,
    ),
    "sites-comparisons-or-chain": Shape(
        as_bytes(lambda n: "const r = " + " || ".join(f"x === 'v{i}'" for i in range(n)) + ";"),
        9000,
    ),
    "sites-comparisons-flat": Shape(
        as_bytes(lambda n: join_lines("if (x{i} === 'a{i}') {}", n)), 8000
    ),
    "sites-comparison-wrappers": Shape(
        as_bytes(lambda n: "x === " + "(" * n + "'a'" + " as const)" * n + ";"), 9000
    ),
    "sites-switch-cases": Shape(
        as_bytes(lambda n: "switch (x) {\n" + join_lines("case 'c{i}': y{i}(); break;", n) + "\n}"),
        9000,
    ),
    "sites-templates-comparisons": Shape(
        as_bytes(lambda n: join_lines("x == `t{i}`; x != `u${y}{i}`; z === (`v{i}`);", n)), 6000
    ),
    "sites-in-decorator-run": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("@d(f{i}())", n, "\n") + "\nm() {}\n}"), 15000
    ),
    "sites-in-decorator-comment-mix": Shape(
        as_bytes(lambda n: "class C {\n" + join_lines("// c\n@d(f{i}())", n, "\n") + "\nm() {}\n}"),
        9000,
    ),
    "sites-after-comment-run": Shape(
        as_bytes(lambda n: "class C {\n" + "// c\n" * n + "m(a = f()) { g(); }\n}"), 100000
    ),
    "sites-script-wrappers": Shape(
        as_bytes(lambda n: join_lines("(function (window) { window.f{i}(w{i}); })(window);", n)),
        4000,
        ".js",
    ),
    "sites-script-wrapper-nest": Shape(
        as_bytes(lambda n: "(function (window) { " * n + "window.f();" + " })(window);" * n),
        8000,
        ".js",
    ),
    "sites-script-publications": Shape(
        as_bytes(lambda n: join_lines("window.a{i} = window.b{i} || g{i};", n)), 6000, ".js"
    ),
    "sites-iife-many-args": Shape(
        as_bytes(
            lambda n: (
                "(function ("
                + join_lines("w{i}", n, ", ")
                + ") { })("
                + join_lines("window", n, ", ")
                + ");"
            )
        ),
        30000,
        ".js",
    ),
    "sites-shorthand-properties": Shape(
        as_bytes(lambda n: "var o = { " + join_lines("a{i}", n, ", ") + " };"), 30000, ".js"
    ),
    "sites-type-positions": Shape(
        as_bytes(lambda n: "type T = " + "A<" * n + "B" + ">" * n + ";"), 50000, ".tsx"
    ),
    "sites-jsx-names": Shape(
        as_bytes(lambda n: join_lines("<a b={c{i}} d:e={f{i}} />;", n)), 5000, ".tsx"
    ),
}


# The sites run in a few shapes that join several of the shapes above. A joined shape holds every
# construct of its parts, each at a linear count, so a quadratic loop in one part shows in the
# ratio of the whole. The parts stay in `scaling_shapes.SHAPES` for the equality tests at small
# sizes, which is where a shape must not be too deep for the Python oracle. A part with `base` b
# has the count n * b / 1000 in a joined shape of n, so the parts take about the same time.
SITE_PARTS: dict[str, tuple[str, ...]] = {
    "sites-timed-calls": (
        "sites-calls-at-depth",
        "sites-nested-calls",
        "sites-with-nest",
        "sites-calls-in-arrow-nest",
    ),
    "sites-timed-chains": (
        "sites-member-chain-call",
        "sites-chained-calls",
        "sites-calls-with-chains",
        "sites-new-expressions",
    ),
    "sites-timed-computed": (
        "sites-computed-access",
        "sites-computed-calls",
        "sites-subscript-flat",
    ),
    "sites-timed-names": (
        "sites-many-free-names",
        "sites-many-bound-names",
        "sites-free-names-in-frames",
        "sites-args-wide",
        "sites-escapes",
        "sites-many-shadowed-names",
        "sites-shadow-nest-arrows",
    ),
    "sites-timed-comparisons": (
        "sites-comparisons-or-chain",
        "sites-comparisons-flat",
        "sites-comparison-wrappers",
        "sites-switch-cases",
        "sites-templates-comparisons",
    ),
    "sites-timed-runs": (
        "sites-in-decorator-run",
        "sites-in-decorator-comment-mix",
        "sites-after-comment-run",
    ),
    "sites-timed-scripts": (
        "sites-script-wrappers",
        "sites-script-wrapper-nest",
        "sites-iife-many-args",
        "sites-script-publications",
        "sites-publication-chain",
        "sites-shorthand-properties",
    ),
    "sites-timed-types-jsx": ("sites-type-positions", "sites-jsx-names"),
}


def _joined(parts: tuple[str, ...]) -> Shape:
    shapes = [SITE_SHAPES[name] for name in parts]
    assert len({shape.suffix for shape in shapes}) == 1, parts

    def make(n: int) -> bytes:
        return b"\n".join(shape.make(max(1, n * shape.base // 1000)) for shape in shapes)

    return Shape(make, 500, shapes[0].suffix)


SITE_TIMED: dict[str, Shape] = {name: _joined(parts) for name, parts in SITE_PARTS.items()}
