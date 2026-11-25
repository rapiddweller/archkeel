// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: `type_reach_model.rs`. The closes of the reviews: each test moves one fact of one dispatch.

use super::tests::{facts, imp, known, module, target, verdict};
use super::{Cause, Mode, Verdict};
use crate::type_reach_fold::Reach;
use serde_json::json;
use std::collections::{BTreeMap, BTreeSet};

#[test]
fn a_dyn_type_argument_of_an_instance_brings_the_implementers_of_that_trait() {
    // `show::<Box<dyn Tr>>` from another module: the generic code of `a` can call a method of `b::X`.
    let generic = json!({"k": "fn", "f": "k::a::show", "m": "k::a", "implements": null});
    let seed = json!({"k": "seed", "to": "k::a::show", "args": ["k::Box"], "dyn": ["k::Tr"]});
    let implementer = imp("k::b", Some("k::Tr"), &["k::b::X"], &[]);
    let with = facts(&[
        module("k::a", &[], &[], &[]),
        generic.clone(),
        seed,
        implementer.clone(),
    ]);
    assert_eq!(verdict(&with, &Mode::Cha), "kept");
    let plain = json!({"k": "seed", "to": "k::a::show", "args": ["k::Box"], "dyn": []});
    let without = facts(&[module("k::a", &[], &[], &[]), generic, plain, implementer]);
    assert_eq!(verdict(&without, &Mode::Cha), "excluded");
}

#[test]
fn a_type_that_flows_into_foreign_code_reaches_an_open_dyn_and_no_other() {
    // `erase::<X>` is a call out of the workspace: the foreign code can coerce `X` to `dyn Any`.
    let held = module("k::a", &[], &["k::Any"], &[]);
    let seed = json!({"k": "seed", "to": "<foreign>", "args": ["k::b::X"], "dyn": []});
    let drop_impl = imp("k::b", Some("k::Drop"), &["k::b::X"], &[]);
    let open = json!({"k": "open", "tr": "k::Any"});
    let reached = facts(&[held.clone(), seed.clone(), drop_impl.clone(), open]);
    assert_eq!(verdict(&reached, &Mode::Cha), "kept");
    let closed = facts(&[held, seed, drop_impl]);
    assert_eq!(verdict(&closed, &Mode::Cha), "excluded");
}

#[test]
fn a_foreign_adt_holds_the_dyn_of_its_fields_and_only_what_is_coerced_to_it() {
    // `a` mentions `std::io::Error`, which holds a `dyn Error`. `Error::other(X)` coerces `X` inside `std`.
    let foreign = json!({"k": "adt", "d": "std::io::Error", "fields": [], "dyn": ["k::Error"]});
    let implementer = imp("k::b", Some("k::Error"), &["k::b::X"], &[]);
    let seed = json!({"k": "seed", "to": "<foreign>", "args": ["k::b::X"], "dyn": []});
    let held = module("k::a", &["std::io::Error"], &[], &[]);
    let with = facts(&[held.clone(), foreign.clone(), implementer.clone(), seed]);
    assert_eq!(verdict(&with, &Mode::Cha), "kept");
    // An implementer that nothing coerces is not in a foreign `dyn`: the program has no such value.
    let without = facts(&[held, foreign, implementer]);
    assert_eq!(verdict(&without, &Mode::Cha), "excluded");
}

#[test]
fn the_namespace_comes_from_the_scan_and_a_foreign_namespace_matches_no_module() {
    let all = facts(&[module("k::a", &[], &[], &[]), target()]);
    let other: BTreeSet<String> = ["rs.k.a", "rs.k.b"].map(String::from).into();
    let reach = Reach::new(&all, &other);
    let pair = ("rs.k.a", "rs.k.b");
    assert!(matches!(
        reach.decide(pair, &Mode::Cha, &mut BTreeMap::new()),
        Verdict::Excluded
    ));
    assert_eq!(reach.matched(&other), 2);
    let none: BTreeSet<String> = ["x.y.a"].map(String::from).into();
    assert_eq!(Reach::new(&all, &none).matched(&none), 0);
}

#[test]
fn an_edge_passes_the_instances_of_its_caller_only_when_its_arguments_hold_a_type_parameter() {
    // `a::outer` is called with `b::X`, and calls `c::inner::<i32>` or `c::inner::<T>`.
    let outer = json!({"k": "fn", "f": "k::a::outer", "m": "k::a", "implements": null});
    let inner = json!({"k": "fn", "f": "k::c::inner", "m": "k::c", "implements": null});
    let seed = json!({"k": "seed", "to": "k::a::outer", "args": ["k::b::X"], "dyn": []});
    let edge = |param: bool| json!({"k": "edge", "from": "k::a::outer", "to": "k::c::inner", "args": [], "dyn": [], "param": param});
    let pair = ("native.k.c", "native.k.b");
    let held = |param: bool| {
        let all = facts(&[
            module("k::c", &[], &[], &[]),
            outer.clone(),
            inner.clone(),
            seed.clone(),
            edge(param),
            target(),
        ]);
        let reach = Reach::new(&all, &known());
        matches!(
            reach.decide(pair, &Mode::Cha, &mut BTreeMap::new()),
            Verdict::Kept(Cause::Reached)
        )
    };
    assert!(held(true));
    assert!(!held(false));
}

#[test]
fn an_open_dyn_with_a_need_takes_only_the_escaped_types_that_meet_it() {
    // `dyn ToString` has the blanket impl `impl<T: Display> ToString for T`: `X` needs `Display`.
    let held = module("k::a", &[], &["k::ToString"], &[]);
    let seed = json!({"k": "seed", "to": "<foreign>", "args": ["k::b::X"], "dyn": []});
    let drop_impl = imp("k::b", Some("k::Drop"), &["k::b::X"], &[]);
    let open = json!({"k": "open", "tr": "k::ToString", "needs": ["k::Display"]});
    let display = imp("k::b", Some("k::Display"), &["k::b::X"], &[]);
    let meets = facts(&[
        held.clone(),
        seed.clone(),
        drop_impl.clone(),
        open.clone(),
        display,
    ]);
    assert_eq!(verdict(&meets, &Mode::Cha), "kept");
    let lacks = facts(&[held, seed, drop_impl, open]);
    assert_eq!(verdict(&lacks, &Mode::Cha), "excluded");
}
