# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Plants of the proof review of #1183 (AD-516): sources of one crate `app`, `a` is the caller.

Consumer: `test_collector_false_pass_rust_orphan_impl.py`. Each plant has `lib.rs`, `a.rs`, `b.rs`
and `c.rs`. The rule says `a` must not use `b`; Cargo fails in `a` when `mod b;` is deleted.
"""

from __future__ import annotations

SELF_TYPE_PLANTS: dict[str, dict[str, str]] = {
    "a trait argument (marker)": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Marker;\n"
        "impl crate::c::Tg<Marker> for crate::c::S { fn "
        "m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Tg<M> { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tg;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
    "a trait argument (AsRef)": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct L;\nimpl AsRef<L> for crate::c::S { fn as_ref(&self) -> &L { &L } }\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "pub fn f(s: &crate::c::S) { let _r = s.as_ref(); }\n",
    },
    "an array length that names a local type": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct L(pub u8, pub u8);\n"
        "impl crate::c::Tr for [u8; "
        "std::mem::size_of::<L>()] { fn m(&self) "
        "-> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { [0u8; 2].m() }\n",
    },
    "a qualified self type": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct L;\n"
        "impl crate::c::Pick for L { type Out = crate::c::S; }\n"
        "impl crate::c::Tr for <L as crate::c::Pick>::Out { fn "
        "m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub trait Pick { type Out; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
    "a const parameter named like a local type": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct N;\n"
        "impl<const N: usize> crate::c::Tr for "
        "[u8; N] { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { [0u8; 2].m() }\n",
    },
    "a block type shadowed by a use": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub fn g() {\n"
        "    #[allow(dead_code)]\n"
        "    struct S;\n"
        "    {\n"
        "        use crate::c::S;\n"
        "        impl crate::c::Tr for S { fn m(&self) -> "
        "u8 { 1 } }\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
    "a block type behind an inline mod": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub fn g() {\n"
        "    #[allow(dead_code)]\n"
        "    struct S;\n"
        "    mod m {\n"
        "        use crate::c::S;\n"
        "        impl crate::c::Tr for S { fn m(&self) "
        "-> u8 { 1 } }\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
    "a block trait shadowed by a use": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub fn g() {\n"
        "    #[allow(dead_code)]\n"
        "    trait Tr {}\n"
        "    {\n"
        "        use crate::c::{S, Tr};\n"
        "        impl Tr for S { fn m(&self) -> u8 { 1 } "
        "}\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\n",
        "a.rs": "use crate::c::Tr;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
}

OPEN_VALUE_FORMS: dict[str, dict[str, str]] = {
    "a method": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { crate::c::make().m() }\n",
    },
    "Display": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\n"
        "impl std::fmt::Display for Y { fn fmt(&self, _f: &mut "
        "std::fmt::Formatter) -> std::fmt::Result { Ok(()) } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "pub fn f() -> String { crate::c::make().to_string() }\n",
    },
    "Drop": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl Drop for Y { fn drop(&mut self) {} }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "pub fn f() { let _v = crate::c::make(); }\n",
    },
    "==": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\n"
        "impl PartialEq for Y { fn eq(&self, _o: &Self) -> bool { true } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "pub fn f() -> bool { crate::c::make() == crate::c::make() }\n",
    },
    "for": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\n"
        "impl Iterator for Y { type Item = u8; fn next(&mut self) -> Option<u8> { "
        "None } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "pub fn f() { for _ in crate::c::make() {} }\n",
    },
    "+": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\n"
        "impl std::ops::Add for Y { type Output = u8; fn add(self, _o: Y) -> u8 { 1 } "
        "}\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> crate::b::Y { crate::b::Y }\n",
        "a.rs": "pub fn f() -> u8 { crate::c::make() + crate::c::make() }\n",
    },
    "?": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\n"
        "pub struct E2;\n"
        "impl From<Y> for E2 { fn from(_: Y) -> E2 { E2 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub type R = Result<(), crate::b::E2>;\n"
        "pub fn h() -> Result<(), crate::b::Y> { Ok(()) }\n",
        "a.rs": "pub fn f() -> crate::c::R { crate::c::h()?; Ok(()) }\n",
    },
    "impl Trait": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> impl Tr { crate::b::Y }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { crate::c::make().m() }\n",
    },
    "dyn": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn make() -> Box<dyn Tr> { Box::new(crate::b::Y) }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { crate::c::make().m() }\n",
    },
    "a field": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub struct W { pub y: crate::b::Y }\n"
        "pub fn w() -> W { W { y: crate::b::Y } }\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { crate::c::w().y.m() }\n",
    },
    "an alias with Default": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "#[derive(Default)]\n"
        "pub struct Y;\n"
        "impl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Tr { fn m(&self) -> u8; }\npub type Al = crate::b::Y;\n",
        "a.rs": "use crate::c::Tr;\n"
        "pub fn f() -> u8 { let y: crate::c::Al = "
        "Default::default(); y.m() }\n",
    },
    "a closure": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct Y;\nimpl crate::c::Tr for Y { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn with(k: impl FnOnce(crate::b::Y) -> u8) -> u8 { k(crate::b::Y) "
        "}\n",
        "a.rs": "use crate::c::Tr;\npub fn f() -> u8 { crate::c::with(|y| y.m()) }\n",
    },
    "into() into a sink of c": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub struct L;\n"
        "impl From<crate::c::S> for L { fn from(_: crate::c::S) "
        "-> L { L } }\n",
        "c.rs": "pub struct S;\n"
        "pub trait Tr { fn m(&self) -> u8; }\n"
        "pub fn sink(_l: crate::b::L) {}\n",
        "a.rs": "pub fn f(s: crate::c::S) { crate::c::sink(s.into()) }\n",
    },
}

OPEN_TRAIT_FORMS: dict[str, dict[str, str]] = {
    "a generic bound on the trait": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub trait LT { fn m(&self) -> u8; }\n"
        "impl LT for crate::c::S { fn m(&self) -> u8 { 1 } "
        "}\n",
        "c.rs": "pub struct S;\npub fn run<T: crate::b::LT>(t: &T) -> u8 { t.m() }\n",
        "a.rs": "pub fn f(s: &crate::c::S) -> u8 { crate::c::run(s) }\n",
    },
    "a supertrait": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub trait LT { fn m(&self) -> u8; }\n"
        "impl LT for crate::c::S { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Sup: crate::b::LT {}\nimpl Sup for S {}\n",
        "a.rs": "fn g<T: crate::c::Sup>(t: &T) -> u8 { t.m() }\n"
        "pub fn f(s: &crate::c::S) -> u8 { g(s) }\n",
    },
    "a dyn supertrait": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub trait LT { fn m(&self) -> u8; }\n"
        "impl LT for crate::c::S { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub trait Sup: crate::b::LT {}\nimpl Sup for S {}\n",
        "a.rs": "pub fn f(s: &dyn crate::c::Sup) -> u8 { s.m() }\n",
    },
    "a re-export of the trait": {
        "lib.rs": "mod a;\nmod b;\nmod c;\n",
        "b.rs": "pub trait LT { fn m(&self) -> u8; }\n"
        "impl LT for crate::c::S { fn m(&self) -> u8 { 1 } }\n",
        "c.rs": "pub struct S;\npub use crate::b::LT;\n",
        "a.rs": "use crate::c::LT;\npub fn f(s: &crate::c::S) -> u8 { s.m() }\n",
    },
}
