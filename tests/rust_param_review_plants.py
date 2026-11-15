# Archkeel
# Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
# SPDX-License-Identifier: MIT
"""Plants of the proof review of #1191 (AD-524): the sources of the plants that the review found.

Consumer: `test_collector_false_pass_rust_param_receiver.py`. A key that starts with `=` is a path
below the root of the repository; any other key is a file of `crates/app/src`. In each plant the
call `s.m(1)` has a typed parameter `s: &crate::c::S` that the code rebinds or removes, so the true
callee is not the member of `b`.
"""

from __future__ import annotations

REVIEW_PLANTS: dict[str, dict[str, str]] = {
    "macro-use-rename": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "macro_rules! rebind {\n"
        "    ($i:ident, $e:expr) => {\n"
        "        let $i = $e;\n"
        "    };\n"
        "}\n"
        "use rebind as assert;\n"
        "pub fn f(s: &crate::c::S) -> u8 {\n"
        "    assert!(s, &crate::c::U);\n"
        "    let r: u8 = s.m(1);\n"
        "    r\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u16 {\n"
        "        x as u16\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "impl crate::c::U {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
    },
    "macro-of-dep-outside-roots": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "use mac::assert;\n"
        "pub fn f(s: &crate::c::S) -> u8 {\n"
        "    assert!(s, &crate::c::U);\n"
        "    let r: u8 = s.m(1);\n"
        "    r\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u16 {\n"
        "        x as u16\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "impl crate::c::U {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "=vendor/mac/Cargo.toml": '[package]\nname = "mac"\nversion = "0.0.0"\nedition = "2021"\n',
        "=vendor/mac/src/lib.rs": "#[macro_export]\n"
        "macro_rules! assert {\n"
        "    ($i:ident, $e:expr) => {\n"
        "        let $i = $e;\n"
        "    };\n"
        "}\n",
        "=crates/app/Cargo.toml": "[package]\n"
        'name = "app"\n'
        'version = "0.0.0"\n'
        'edition = "2021"\n'
        "[dependencies]\n"
        'base-crate = { path = "../base" }\n'
        'mac = { path = "../../vendor/mac" '
        "}\n",
    },
    "proc-macro-rebinds": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub fn f(s: &crate::c::S) -> u8 {\n"
        "    pm::rebind!();\n"
        "    let r: u8 = s.m(1);\n"
        "    r\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u16 {\n"
        "        x as u16\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "impl crate::c::U {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "=crates/Cargo.toml": '[workspace]\nmembers = ["base", "app", "pm"]\n',
        "=crates/pm/Cargo.toml": "[package]\n"
        'name = "pm"\n'
        'version = "0.0.0"\n'
        'edition = "2021"\n'
        "[lib]\n"
        "proc-macro = true\n",
        "=crates/pm/src/lib.rs": "use proc_macro::TokenStream;\n"
        "#[proc_macro]\n"
        "pub fn rebind(_: TokenStream) -> TokenStream "
        "{\n"
        '    "let s = '
        '&crate::c::U;".parse().unwrap()\n'
        "}\n",
        "=crates/app/Cargo.toml": "[package]\n"
        'name = "app"\n'
        'version = "0.0.0"\n'
        'edition = "2021"\n'
        "[dependencies]\n"
        'base-crate = { path = "../base" }\n'
        'pm = { path = "../pm" }\n',
    },
    "cfg-on-enclosing-impl": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub struct W;\n"
        "#[cfg(any())]\n"
        "impl W {\n"
        "    pub fn f(&self, s: &crate::c::S) -> u8 {\n"
        "        let r: u8 = s.m(1);\n"
        "        r\n"
        "    }\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "pub fn keep() {}\n",
    },
    "cfg-on-enclosing-trait-impl": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub struct K;\n"
        "pub trait Q {\n"
        "    fn g(&self) -> u8 {\n"
        "        0\n"
        "    }\n"
        "    fn h(&self, _s: &crate::c::S) -> u8 {\n"
        "        0\n"
        "    }\n"
        "}\n"
        "#[cfg(any())]\n"
        "impl Q for K {\n"
        "    fn h(&self, s: &crate::c::S) -> u8 {\n"
        "        let r: u8 = s.m(1);\n"
        "        r\n"
        "    }\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "pub fn keep() {}\n",
    },
    "cfg-on-statement": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub fn f(s: &crate::c::S) -> u8 {\n"
        "    #[cfg(any())]\n"
        "    let _r: u8 = s.m(1);\n"
        "    let _ = s;\n"
        "    0\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "pub fn keep() {}\n",
    },
    "cfg-on-match-arm": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub fn f(s: &crate::c::S, k: u8) -> u8 {\n"
        "    let _ = s;\n"
        "    match k {\n"
        "        #[cfg(any())]\n"
        "        1 => s.m(1),\n"
        "        _ => 0,\n"
        "    }\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "pub fn keep() {}\n",
    },
    "cfg-on-block-expr": {
        "lib.rs": "mod a;\nmod b;\nmod c;\nmod d;\n",
        "a.rs": "pub fn f(s: &crate::c::S) -> u8 {\n"
        "    #[cfg(any())]\n"
        "    {\n"
        "        return s.m(1);\n"
        "    }\n"
        "    let _ = s;\n"
        "    0\n"
        "}\n",
        "b.rs": "impl crate::c::S {\n"
        "    pub fn m(&self, x: u8) -> u8 {\n"
        "        x as u8\n"
        "    }\n"
        "}\n",
        "c.rs": "pub struct S;\npub struct U;\n",
        "d.rs": "pub fn keep() {}\n",
    },
}
