// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: collection coverage. An expansion can add an edge with an unseen target.

use super::collect::tests::run;
use crate::scan::scan;
use std::collections::BTreeSet;

#[test]
fn an_attribute_on_every_syntax_position_names_its_unseen_expansion() {
    for item in [
        "#[mac::hide] fn f() {}",
        "#[mac::hide] struct S;",
        "#[mac::hide] enum E { V }",
        "#[mac::hide] impl S {}",
        "#[mac::hide] trait T {}",
        "impl S { #[mac::hide] fn f() {} }",
        "trait T { #[mac::hide] fn f(); }",
        "struct S { #[mac::hide] f: u8 }",
        "enum E { #[mac::hide] V }",
        "fn f() { #[mac::hide] let x = 1; }",
        "fn f() { let x = #[mac::hide] 1; }",
        "extern \"C\" { #[mac::hide] fn f(); }",
        "#[mac::hide] mod m {}",
        "#[mac::hide] use x::y;",
        "#[cfg_attr(unix, mac::hide)] fn f() {}",
    ] {
        let found = scan(item, &BTreeSet::new(), false).unwrap();
        assert!(
            found
                .concerns
                .iter()
                .any(|c| c.reason.contains("mac::hide")),
            "{item}: {:?}",
            found.concerns
        );
    }
}

#[test]
fn a_custom_derive_can_add_items_and_calls() {
    for item in [
        "#[derive(mac::Hide)] struct S;",
        "use mac::Clone; #[derive(Clone)] struct S;",
    ] {
        let found = scan(item, &BTreeSet::new(), false).unwrap();
        assert!(
            found
                .concerns
                .iter()
                .any(|c| c.reason.contains("derive macro")),
            "{item}"
        );
    }
}

#[test]
fn builtins_tools_and_helpers_do_not_add_attribute_gaps() {
    let text = r#"
        #[derive(Clone, Debug, Default)] #[repr(C)] #[must_use] struct Plain;
        #[rustfmt::skip] #[clippy::has_significant_drop] #[diagnostic::on_unimplemented(message = "x")]
        #[allow(dead_code)] fn f() {}
        #[derive(serde::Serialize, schemars::JsonSchema)] #[serde(rename = "S")]
        #[schemars(rename = "S")] struct S { #[serde(default)] f: u8 }
    "#;
    let found = scan(text, &BTreeSet::new(), false).unwrap();
    let other: Vec<_> = found
        .concerns
        .iter()
        .filter(|c| !c.reason.contains("derive macro"))
        .collect();
    assert!(other.is_empty(), "{other:?}");
    assert_eq!(found.concerns.len(), 2);
    assert!(
        !scan("#[serde(default)] struct S;", &BTreeSet::new(), false)
            .unwrap()
            .concerns
            .is_empty()
    );
}

#[test]
fn an_inline_attribute_gap_has_a_known_source_and_an_unseen_target() {
    let facts = run(
        &[
            (
                "crates/Cargo.toml",
                "[package]\nname = \"app\"\nedition = \"2021\"\n",
            ),
            ("crates/src/lib.rs", "mod b { #[mac::hide] fn f() {} }"),
        ],
        false,
    );
    let gap = facts
        .gaps
        .iter()
        .find(|g| g.title.contains("mac::hide"))
        .unwrap();
    let archkeel_facts::GapFact::CollectionGap(data) = &gap.data else {
        panic!("wrong kind")
    };
    assert_eq!(
        data.source_module.as_ref().map(|s| s.as_str()),
        Some("ns.app.b")
    );
    assert_eq!(data.module.as_ref().map(|s| s.as_str()), Some(""));
    assert!(
        !facts
            .typed(archkeel_wire::protocol::Version::V8)
            .unwrap()
            .facts
            .coverage
            .full_scope
    );
}
