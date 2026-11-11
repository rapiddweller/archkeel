// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the invariant of the extraction. The count of the tree must equal what the scan read,
// for each shape of node, with and without the test items that the scan leaves out.

use std::collections::BTreeSet;

use super::super::scan;

/// The count of the tree, and what the scan read as nodes: references and calls of the tree.
fn counted(text: &str, exclude_tests: bool) -> (usize, usize) {
    let found = scan(text, &BTreeSet::new(), exclude_tests).unwrap();
    let tally = found.tally;
    let read = found.references.len() - tally.unseen + found.macro_calls.len() - tally.hidden;
    (tally.expected, read)
}

#[test]
fn the_count_equals_the_scan_for_each_shape_of_node() {
    let text = "use a::{b, c as d, e::*, f::{self}};\nextern crate g;\nextern crate self as h;\n\
        #[i::j(k::l)]\nstruct S;\nmacro_rules! m { () => { n::o() } }\n\
        fn f() { p::q(); println!(\"{}\", r::s); m!(); t::u!(v::w!()); let _: x::Y; }\n\
        impl z::T for S { fn g(&self) { y::h(); } }\nmod inner { pub use super::a::b; }\n";
    let (expected, read) = counted(text, false);
    assert_eq!(expected, read);
    assert!(expected >= 14, "{expected}");
}

#[test]
fn the_count_leaves_out_what_the_scan_leaves_out_of_a_test_build() {
    let text = "use a::b;\n#[cfg(test)]\nmod tests { use c::d; fn t() { e::f(); g!(); } }\n\
        fn f() {\n#[cfg(test)]\nh::i();\nj::k();\n}\n";
    let (expected, read) = counted(text, true);
    assert_eq!(expected, read);
    assert_eq!(expected, 3);
    let (all, read) = counted(text, false);
    assert_eq!(all, read);
    assert!(all > expected);
}

#[test]
fn a_doc_attribute_that_calls_a_macro_is_counted_like_code() {
    let text = "#![doc = include_str!(\"../README.md\")]\n#[doc = concat!(\"a\", \"b\")]\n\
        #[doc = a::b!()]\nmacro_rules! m { () => {} }\n#[doc = include_str!(\"x\")]\nmod x;\n\
        #[doc = include_str!(\"y\")]\nuse a::b;\n#[allow(unused = c::d!())]\nfn f() {}\n";
    let (expected, read) = counted(text, false);
    assert_eq!(expected, read);
    assert!(expected >= 7, "{expected}");
}

#[test]
fn a_use_leaf_without_a_segment_names_no_path() {
    let (expected, read) = counted(
        "use ::*;\nuse {self};\nuse self as x;\nuse a::{self as y};\n",
        false,
    );
    assert_eq!(expected, read);
    assert_eq!(expected, 1);
}

#[test]
fn the_count_includes_method_calls_and_qualified_self_paths() {
    let text = "fn f(x: u8) { x.m(); x.a().b::<u8>(); <u8>::c(); println!(\"{}\", x.hidden()); }\n";
    let found = scan(text, &BTreeSet::new(), false).unwrap();
    let tally = found.tally;
    let read = found.references.len() - tally.unseen + found.macro_calls.len() - tally.hidden
        + found.method_calls.len()
        - tally.hidden_methods;
    assert_eq!(tally.expected, read);
    assert!(tally.expected >= 5, "{}", tally.expected);
}
