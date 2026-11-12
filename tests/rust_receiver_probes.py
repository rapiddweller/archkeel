# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""The compiled probe crates of a method call on `self` (AD-383).

Each case is a crate `app` with the modules `a` to `e`. `a::run()` makes the call under test, and
each method returns the name of its module, so the program output names the real target.
`tests/test_collector_native_rust_receivers_compiled.py` compiles and runs each case.
"""

from __future__ import annotations

LIB = "mod a;\nmod b;\nmod c;\nmod d;\nmod e;\npub fn run() -> &'static str {\n    a::run()\n}\n"
TYPES = "pub struct S;\npub struct T;\n"
DEREF = (
    "pub struct S(pub T);\npub struct T;\nimpl std::ops::Deref for S {\n    type Target = T;\n"
    "    fn deref(&self) -> &T {\n        &self.0\n    }\n}\n"
)
STR = "&'static str"
RUN = "crate::c::S.f()"


def method(module: str, form: str = "&self", ty: str = "crate::c::S", attrs: str = "") -> str:
    """An `impl` of `ty` with a member `m` that returns `module`."""
    return (
        f'impl {ty} {{\n    {attrs}pub fn m({form}) -> {STR} {{\n        "{module}"\n    }}\n}}\n'
    )


def caller(form: str = "&self", body: str = "self.m()", run: str = RUN, head: str = "") -> str:
    """`a`: an `impl S` whose method `f` makes the call, and `run()`."""
    return (
        f"{head}impl crate::c::S {{\n    pub fn f({form}) -> {STR} {{\n        {body}\n    }}\n}}\n"
        f"pub fn run() -> {STR} {{\n    {run}\n}}\n"
    )


def tr(form: str, target: str, module: str = "d", name: str = "m") -> str:
    """A trait `Tm` with a member `name` and its impl for `target`, which returns `module`."""
    return (
        f"pub trait Tm {{\n    fn {name}({form}) -> {STR};\n}}\n"
        f"impl Tm for {target} {{\n"
        f'    fn {name}({form}) -> {STR} {{\n        "{module}"\n    }}\n}}\n'
    )


USE_TM = "use crate::d::Tm;\n"
GATE = '#[cfg(feature = "optional")]\n'


def _std_case(name: str, c: str, inherent: str, body: str, form: str = "&self") -> dict[str, str]:
    """An inherent member named as a std trait method, beside the impl of that trait."""
    member = f'impl crate::c::S {{\n    pub fn {inherent} -> {STR} {{\n        "b"\n    }}\n}}\n'
    run = "let mut s = crate::c::S;\n    s.f()" if form == "&mut self" else RUN
    if form == "self":
        run = "crate::c::S.f()"
    return {"c.rs": c, "b.rs": member, "a.rs": caller(form, body, run)}


CASES: dict[str, dict[str, str]] = {
    "inherent shared": {"b.rs": method("b")},
    "inherent beside trait m(self) for S": {
        "b.rs": method("b"),
        "d.rs": tr("self", "crate::c::S"),
        "a.rs": caller(head=USE_TM),
    },
    "inherent beside trait m(self) for &S": {
        "b.rs": method("b"),
        "d.rs": tr("self", "&crate::c::S"),
        "a.rs": caller(head=USE_TM),
    },
    "inherent beside trait m(self) for &mut S": {
        "b.rs": method("b"),
        "d.rs": tr("self", "&mut crate::c::S"),
        "a.rs": caller(head=USE_TM),
    },
    "inherent m(&mut self) beside trait m(&self)": {
        "b.rs": method("b", "&mut self"),
        "d.rs": tr("&self", "crate::c::S"),
        "a.rs": caller("&mut self", run="let mut s = crate::c::S;\n    s.f()", head=USE_TM),
    },
    "inherent m(&self) from &mut self beside trait m(&mut self)": {
        "b.rs": method("b"),
        "d.rs": tr("&mut self", "crate::c::S"),
        "a.rs": caller("&mut self", run="let mut s = crate::c::S;\n    s.f()", head=USE_TM),
    },
    "call inside impl Trait for S": {
        "b.rs": method("b"),
        "a.rs": (
            f"pub trait F {{\n    fn f(&self) -> {STR};\n}}\nimpl F for crate::c::S {{\n"
            f"    fn f(&self) -> {STR} {{\n        self.m()\n    }}\n}}\n"
            f"pub fn run() -> {STR} {{\n    crate::c::S.f()\n}}\n"
        ),
    },
    "receiver Box<Self>": {
        "b.rs": method("b"),
        "a.rs": caller("self: Box<Self>", run="Box::new(crate::c::S).f()"),
    },
    "receiver Rc<Self>": {
        "b.rs": method("b"),
        "a.rs": caller("self: std::rc::Rc<Self>", run="std::rc::Rc::new(crate::c::S).f()"),
    },
    "receiver Pin<&mut Self>": {
        "b.rs": method("b"),
        "a.rs": caller(
            "self: std::pin::Pin<&mut Self>",
            run="let mut s = crate::c::S;\n    std::pin::Pin::new(&mut s).f()",
        ),
    },
    "receiver self: &Self": {"b.rs": method("b"), "a.rs": caller("self: &Self")},
    "receiver mut self": {"b.rs": method("b", "self"), "a.rs": caller("mut self")},
    "receiver self: Self": {"b.rs": method("b", "self"), "a.rs": caller("self: Self")},
    "by-value self calls a &self inherent": {
        "c.rs": "#[derive(Clone, Copy)]\npub struct S;\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": caller("self"),
    },
    "deref target with an inherent member too": {
        "c.rs": DEREF,
        "b.rs": method("b"),
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(run="crate::c::S(crate::c::T).f()"),
    },
    "deref target without an inherent member": {
        "c.rs": DEREF,
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(run="crate::c::S(crate::c::T).f()"),
    },
    "gated inherent member, deref target (review of #1081)": {
        "c.rs": DEREF,
        "b.rs": method("b", attrs=GATE + "    "),
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(run="crate::c::S(crate::c::T).f()"),
    },
    "gated module of the member, deref target": {
        "c.rs": DEREF,
        "b.rs": f"{GATE}mod inner {{\n{method('b')}}}\n",
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(run="crate::c::S(crate::c::T).f()"),
    },
    "two blocks in two modules under opposite cfg": {
        "b.rs": GATE + method("b"),
        "d.rs": '#[cfg(not(feature = "optional"))]\n' + method("d"),
    },
    "member in a cfg(test) block, trait method otherwise": {
        "b.rs": "#[cfg(test)]\n" + method("b"),
        "d.rs": tr("&self", "crate::c::S"),
        "a.rs": caller(head=USE_TM),
    },
    "member made by a macro_rules impl": {
        "b.rs": "macro_rules! make {\n    () => {\n" + method("b") + "    };\n}\nmake!();\n",
    },
    "impl inside a function body": {
        "b.rs": "pub fn hidden() {\n" + method("b") + "}\n",
    },
    "impl in a nested module": {"b.rs": "pub mod inner {\n" + method("b") + "}\n"},
    "S shadowed by a local type": {
        "b.rs": method("b"),
        "a.rs": (
            f'struct S;\nimpl S {{\n    fn m(&self) -> {STR} {{\n        "a"\n    }}\n'
            f"    fn f(&self) -> {STR} {{\n        self.m()\n    }}\n}}\n"
            f"pub fn run() -> {STR} {{\n    S.f()\n}}\n"
        ),
    },
    "S bound by use as S": {
        "b.rs": method("b"),
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": (
            f"use crate::c::T as S;\nimpl S {{\n    pub fn f(&self) -> {STR} {{\n        self.m()\n"
            f"    }}\n}}\npub fn run() -> {STR} {{\n    crate::c::T.f()\n}}\n"
        ),
    },
    "S as a type parameter": {
        "b.rs": method("b"),
        "d.rs": tr("&self", "crate::c::T"),
        "a.rs": (
            "#[allow(unused_imports)]\nuse crate::c::S;\n"
            f"pub trait F {{\n    fn f(&self) -> {STR};\n}}\n"
            f"impl<S: crate::d::Tm> F for S {{\n    fn f(&self) -> {STR} {{\n        self.m()\n"
            f"    }}\n}}\npub fn run() -> {STR} {{\n    crate::c::T.f()\n}}\n"
        ),
    },
    "enum Self": {
        "c.rs": "pub enum S {\n    A,\n}\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": caller(run="crate::c::S::A.f()"),
    },
    "union Self": {
        "c.rs": "pub union S {\n    pub x: u8,\n}\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": caller(run="crate::c::S { x: 0 }.f()"),
    },
    "impl S<u8> and impl S<u16>": {
        "c.rs": "pub struct S<X>(pub X);\npub struct T;\n",
        "b.rs": method("b", ty="crate::c::S<u8>"),
        "d.rs": method("d", ty="crate::c::S<u16>"),
        "a.rs": caller(run="crate::c::S(0u16).f()").replace(
            "impl crate::c::S {", "impl crate::c::S<u16> {"
        ),
    },
    "const generics": {
        "c.rs": "pub struct S<const N: usize>;\npub struct T;\n",
        "b.rs": method("b", ty="crate::c::S<1>"),
        "d.rs": method("d", ty="crate::c::S<2>"),
        "a.rs": caller(run="crate::c::S::<2>.f()").replace(
            "impl crate::c::S {", "impl crate::c::S<2> {"
        ),
    },
    "lifetime-only generics": {
        "c.rs": "pub struct S<'x>(pub &'x u8);\npub struct T;\n",
        "b.rs": method("b", ty="crate::c::S<'_>"),
        "a.rs": caller(run="crate::c::S(&0).f()").replace(
            "impl crate::c::S {", "impl<'a> crate::c::S<'a> {"
        ),
    },
    "impl dyn Trait": {
        "c.rs": "pub struct S;\npub struct T;\npub trait Tr {}\nimpl Tr for u8 {}\n",
        "b.rs": method("b", ty="dyn crate::c::Tr"),
        "a.rs": (
            "impl dyn crate::c::Tr {\n"
            f"    pub fn f(&self) -> {STR} {{\n        self.m()\n    }}\n}}\n"
            f"pub fn run() -> {STR} {{\n    let x: &dyn crate::c::Tr = &0u8;\n    x.f()\n}}\n"
        ),
    },
    "raw identifier r#m": {
        "b.rs": method("b").replace("fn m(", "fn r#m("),
        "a.rs": caller(body="self.r#m()"),
    },
    "field call (self.m)()": {
        "c.rs": f"pub struct S {{\n    pub m: fn() -> {STR},\n}}\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": f'fn local() -> {STR} {{\n    "a"\n}}\n'
        + caller(body="(self.m)()", run="crate::c::S { m: local }.f()"),
    },
    "method beside a field of the same name": {
        "c.rs": f"pub struct S {{\n    pub m: fn() -> {STR},\n}}\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": f'fn local() -> {STR} {{\n    "a"\n}}\n'
        + caller(run="crate::c::S { m: local }.f()"),
    },
    "turbofish self.m::<u8>()": {
        "b.rs": method("b").replace("fn m(", "fn m<X>("),
        "a.rs": caller(body="self.m::<u8>()"),
    },
    "path Self::m(self)": {"b.rs": method("b"), "a.rs": caller(body="Self::m(self)")},
    "path S::m(self)": {"b.rs": method("b"), "a.rs": caller(body="crate::c::S::m(self)")},
    "(*self).m()": {"b.rs": method("b"), "a.rs": caller(body="(*self).m()")},
    "(&*self).m()": {"b.rs": method("b"), "a.rs": caller(body="(&*self).m()")},
    "self.clone().m()": {
        "c.rs": "#[derive(Clone)]\npub struct S;\npub struct T;\n",
        "b.rs": method("b"),
        "a.rs": caller(body="self.clone().m()"),
    },
    "self.0.m()": {
        "c.rs": "pub struct S(pub T);\npub struct T;\n",
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(body="self.0.m()", run="crate::c::S(crate::c::T).f()"),
    },
    "self.0.m() beside an inherent m of S": {
        "c.rs": "pub struct S(pub T);\npub struct T;\n",
        "b.rs": method("b"),
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(body="self.0.m()", run="crate::c::S(crate::c::T).f()"),
    },
    "trait impl in the caller, trait not in scope, deref target": {
        "c.rs": DEREF,
        "d.rs": f"pub trait Tm {{\n    fn m(&self) -> {STR};\n}}\n",
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": "impl crate::d::Tm for crate::c::S {\n"
        f'    fn m(&self) -> {STR} {{\n        "a"\n    }}\n}}\n'
        + caller(run="crate::c::S(crate::c::T).f()"),
    },
    "closure in the method body": {
        "b.rs": method("b"),
        "a.rs": caller(body="let g = || self.m();\n        g()"),
    },
    "nested impl with its own self": {
        "b.rs": method("b"),
        "e.rs": method("e", ty="crate::c::T"),
        "a.rs": caller(
            body="impl crate::c::T {\n"
            f"            fn g(&self) -> {STR} {{\n                self.m()\n"
            "            }\n        }\n        crate::c::T.g()"
        ),
    },
    "call in a macro call": {
        "b.rs": method("b"),
        "a.rs": "macro_rules! id {\n    ($e:expr) => {\n        $e\n    };\n}\n"
        + caller(body="id!(self.m())"),
    },
    "two blocks of S, the member in the second": {
        "b.rs": f'impl crate::c::S {{\n    pub fn n(&self) -> {STR} {{\n        "b"\n    }}\n}}\n',
        "d.rs": method("d"),
    },
    "std name clone": _std_case(
        "clone", "#[derive(Clone)]\npub struct S;\npub struct T;\n", "clone(&self)", "self.clone()"
    ),
    "std name eq": _std_case(
        "eq",
        "#[derive(PartialEq)]\npub struct S;\npub struct T;\n",
        "eq(&self, _: &Self)",
        "self.eq(self)",
    ),
    "std name fmt": _std_case(
        "fmt",
        "#[derive(Debug)]\npub struct S;\npub struct T;\n",
        "fmt(&self, _: u8)",
        "self.fmt(0)",
    ),
    "std name into": _std_case(
        "into",
        "#[derive(Clone, Copy)]\npub struct S;\npub struct T;\n",
        "into(self)",
        "self.into()",
        "self",
    ),
    "std name as_ref": _std_case(
        "as_ref",
        "pub struct S;\npub struct T;\nimpl AsRef<S> for S {\n    fn as_ref(&self) -> &S {\n"
        "        self\n    }\n}\n",
        "as_ref(&self)",
        "self.as_ref()",
    ),
    "std name borrow": {
        **_std_case("borrow", TYPES, "borrow(&self)", "self.borrow()"),
        "a.rs": caller(body="self.borrow()", head="use std::borrow::Borrow;\n"),
    },
    "std name to_string": _std_case(
        "to_string",
        "pub struct S;\npub struct T;\nimpl std::fmt::Display for S {\n"
        "    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {\n"
        '        write!(f, "s")\n    }\n}\n',
        "to_string(&self)",
        "self.to_string()",
    ),
    "std name next": _std_case(
        "next",
        "pub struct S;\npub struct T;\nimpl Iterator for S {\n    type Item = u8;\n"
        "    fn next(&mut self) -> Option<u8> {\n        None\n    }\n}\n",
        "next(&mut self)",
        "self.next()",
        "&mut self",
    ),
}

# The cases where the collector, before AD-383 or after it, gave neither the exact edge nor a gap.
KNOWN_MISSES: dict[str, str] = {
    "member made by a macro_rules impl": "#1020: a member that a macro expands is no gap yet",
}
