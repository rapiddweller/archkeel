// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::{chain_of, Names};
use crate::definitions::{ReceiverChain, Root, Step, Written};

/// A `fn` that binds `x` to a written type, has `Self = c::S`, and binds the name `shadow`.
struct Fixture;

impl Names for Fixture {
    fn named(&self, name: &str, _: (usize, usize)) -> Option<ReceiverChain> {
        (name == "x").then(|| ReceiverChain {
            name: "x".to_owned(),
            root: Root::Typed(Written::Unknown),
            steps: vec![Step::Field("a".to_owned())],
            macros: Vec::new(),
        })
    }
    fn hides(&self, first: &str) -> bool {
        first == "shadow"
    }
    fn self_type(&self) -> Option<Vec<String>> {
        Some(vec!["c".to_owned(), "S".to_owned()])
    }
    fn macros(&self) -> Vec<String> {
        Vec::new()
    }
}

fn chain(text: &str) -> Option<(Root, Vec<Step>)> {
    let expr: syn::Expr = syn::parse_str(text).unwrap();
    chain_of(&expr, &Fixture).map(|found| (found.root, found.steps))
}

fn path(names: &[&str]) -> Vec<String> {
    names.iter().map(|name| (*name).to_owned()).collect()
}

#[test]
fn a_chain_reads_fields_calls_and_try_after_its_root() {
    let (_, steps) = chain("&mut x.b").unwrap();
    let borrow = Step::Borrow(crate::definitions::SelfKind::Unique);
    assert_eq!(
        steps,
        vec![
            Step::Field("a".to_owned()),
            Step::Field("b".to_owned()),
            borrow
        ]
    );
    let (root, steps) = chain("x.b.m(1, 2)?.n()").unwrap();
    assert_eq!(root, Root::Typed(Written::Unknown));
    let expected = vec![
        Step::Field("a".to_owned()),
        Step::Field("b".to_owned()),
        Step::Call("m".to_owned(), 2),
        Step::Try,
        Step::Call("n".to_owned(), 0),
    ];
    assert_eq!(steps, expected);
}

#[test]
fn a_root_is_a_binding_a_literal_a_call_or_a_value_path() {
    assert_eq!(chain("\"s\"").unwrap().0, Root::Literal("str"));
    assert_eq!(
        chain("Self::new(1)").unwrap().0,
        Root::Call(path(&["c", "S", "new"]), 1)
    );
    assert_eq!(
        chain("m::T { a: 1 }").unwrap().0,
        Root::Value(path(&["m", "T"]))
    );
    assert_eq!(chain("E::V").unwrap().0, Root::Value(path(&["E", "V"])));
    // An unbound name, a hidden path, a generic call and an index give no chain.
    for text in [
        "y.m()",
        "shadow::f()",
        "Vec::<u8>::new()",
        "v[0].m()",
        "<T as Tr>::f()",
    ] {
        assert_eq!(chain(text), None, "{text}");
    }
}
