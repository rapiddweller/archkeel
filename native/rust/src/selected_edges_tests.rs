// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-1136: a call of `PartialEq::eq` that the compiler resolved to a workspace impl is an edge with the
// compiler as evidence. The facts here are written by hand; `tests/test_cli_native_rust_selected_eq_edge.py` runs the
// real driver.

use crate::collect::tests::{APP, BASE, WORKSPACE};
use crate::reply::Collected;
use crate::type_reach::{Announced, Reached};
use crate::type_reach_facts::Facts;
use archkeel_facts::envelope::{Dirty, Profile, Provenance, Target};
use archkeel_facts::request::{RustRequest, RustSettings, Scope, Snapshot};
use archkeel_facts::ImportFact;
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::protocol::Version;

const A: &str = "pub fn same() -> bool { crate::c::make() == crate::c::make() }\n";
const B: &str = "pub struct Y;\nimpl PartialEq for Y { fn eq(&self, _o: &Y) -> bool { true } }\n";
const C: &str = "pub fn make() -> crate::b::Y { crate::b::Y }\n";

/// The string table of the hand-written facts.
const TABLE: &str = r#"["app::a","app::b","app::c","crates/app/src/a.rs","app::b::Y","PartialEq","app::b::{impl#0}::eq","other::m","crates/app/src/generated.rs","crates/app/src/b.rs","crates/app/src/c.rs"]"#;
const MODULES: [&str; 3] = [
    r#"{"k":"mod","m":0,"file":3,"mentions":[4],"dyn":[],"opaque":[],"dyn_in":[]}"#,
    r#"{"k":"mod","m":1,"file":3,"mentions":[4],"dyn":[],"opaque":[],"dyn_in":[]}"#,
    r#"{"k":"mod","m":2,"file":3,"mentions":[4],"dyn":[],"opaque":[],"dyn_in":[]}"#,
];
const IMPL: &str = r#"{"k":"impl","trait":5,"self":4,"self_adts":[4],"assoc":[],"assoc_dyn":[],"items":1,"m":1,"file":3,"line":2,"run":true}"#;
const SITE: &str =
    r#"{"k":"sel","from":0,"to":1,"impl":6,"file":3,"impl_file":9,"line":1,"col":28}"#;

fn facts_of(test: bool, records: &[&str]) -> Facts {
    let mut facts = Facts::empty();
    let mut lines = vec![
        format!("{{\"k\":\"build\",\"test\":{test}}}"),
        format!("{{\"k\":\"str\",\"v\":{TABLE}}}"),
    ];
    lines.extend(MODULES.iter().map(|m| (*m).to_owned()));
    lines.extend(records.iter().map(|r| (*r).to_owned()));
    facts.absorb(&lines.join("\n")).unwrap();
    facts
}

fn announced(test: bool, records: &[&str]) -> Announced {
    announced_in(vec![facts_of(test, records)])
}

/// One facts value for each configuration of the matrix.
fn announced_in(facts: Vec<Facts>) -> Announced {
    let reached = Reached {
        rustc: "rustc 1.97.0\n".to_owned(),
        target_triple: "aarch64-apple-darwin".to_owned(),
        driver_sha256: "d".repeat(64),
        cargo_lock_sha256: "c".repeat(64),
        members: vec!["crates/app/".to_owned()],
        configs: vec!["default".to_owned()],
    };
    Some(Ok((facts, reached)))
}

fn collect(announce: Announced) -> Collected {
    let tree = Tree::new(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", "pub fn f() {}"),
        ("crates/app/Cargo.toml", APP),
        (
            "crates/app/src/lib.rs",
            "pub mod a;\npub mod b;\npub mod c;\n",
        ),
        ("crates/app/src/a.rs", A),
        ("crates/app/src/b.rs", B),
        ("crates/app/src/c.rs", C),
    ]);
    let request = RustRequest {
        protocol_version: Version::V8,
        snapshot: Snapshot {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["crates".to_owned()],
            namespace: "ns".to_owned(),
            exclude_test_sources: Some(false),
        },
        resolver: RustSettings {},
    };
    let provenance = Provenance::native(Profile::Rust, ("1", "d"), ("1.88.0", "1.88"));
    crate::collect::collect_with(&request, provenance, |_, _| announce)
}

/// The selected-impl imports from `a` to `b`.
fn selected(found: &Collected) -> Vec<&archkeel_facts::Record<ImportFact>> {
    found
        .imports
        .iter()
        .filter(|r| matches!(r.data, ImportFact::SelectedImpl(_)))
        .collect()
}

fn gap_from_a_to_b(found: &Collected) -> bool {
    found.gaps.iter().any(|gap| {
        let data = gap.data.data();
        data.source_module.as_ref().map(|m| m.as_str()) == Some("ns.app.a")
            && gap.title.contains("trait impl in ns.app.b")
    })
}

#[test]
fn a_selected_eq_gives_an_edge_that_cites_the_call_and_keeps_the_pair_gap() {
    let found = collect(announced(false, &[IMPL, SITE]));
    let edges = selected(&found);
    assert_eq!(edges.len(), 1, "one selected_impl edge");
    let Some(edge) = edges.first() else {
        return;
    };
    let data = edge.data.data();
    assert_eq!(data.source_module.as_str(), "ns.app.a");
    assert_eq!(data.target_module.as_str(), "ns.app.b");
    assert_eq!(data.symbol, None, "the compiler fact names no symbol");
    let cited = found
        .evidence
        .iter()
        .find(|e| {
            edge.evidence_ids
                .iter()
                .any(|id| id.as_str() == e.id.as_str())
        })
        .expect("the evidence of the edge");
    assert_eq!(
        (cited.file.as_str(), cited.line),
        ("crates/app/src/a.rs", 1)
    );
    assert!(
        cited.excerpt.contains("app::b::{impl#0}::eq"),
        "{}",
        cited.excerpt
    );
    let target = found
        .head
        .imports
        .iter()
        .find(|t| t.import_id().as_str() == edge.id.as_str());
    assert!(matches!(target, Some(Target::Local { module, .. }) if module.as_str() == "ns.app.b"));
    // The compiler resolved one site. Another site of the pair (a drop, a format) stays open.
    assert!(gap_from_a_to_b(&found), "the pair gap a -> b stays");
}

#[test]
fn facts_without_the_site_give_no_edge() {
    let found = collect(announced(false, &[IMPL]));
    assert!(selected(&found).is_empty());
    assert!(gap_from_a_to_b(&found));
}

#[test]
fn a_site_of_a_test_unit_gives_no_edge() {
    let found = collect(announced(true, &[IMPL, SITE]));
    assert!(selected(&found).is_empty());
}

#[test]
fn a_site_that_names_a_module_of_no_scan_gives_no_edge() {
    let outside =
        r#"{"k":"sel","from":0,"to":2,"impl":6,"file":3,"impl_file":10,"line":1,"col":0}"#;
    let same = r#"{"k":"sel","from":1,"to":1,"impl":6,"file":3,"impl_file":9,"line":1,"col":0}"#;
    let other = r#"{"k":"sel","from":0,"to":7,"impl":6,"file":3,"impl_file":9,"line":1,"col":0}"#;
    let found = collect(announced(false, &[IMPL, same, other]));
    assert!(
        selected(&found).is_empty(),
        "same module and unknown module"
    );
    let found = collect(announced(false, &[IMPL, outside]));
    assert_eq!(selected(&found).len(), 1, "a -> c is a scan pair");
}

#[test]
fn a_site_in_another_file_than_its_module_gives_no_edge() {
    let elsewhere =
        r#"{"k":"sel","from":0,"to":1,"impl":6,"file":8,"impl_file":9,"line":1,"col":0}"#;
    let found = collect(announced(false, &[IMPL, elsewhere]));
    assert!(selected(&found).is_empty());
}

#[test]
fn a_site_that_one_configuration_lacks_gives_no_edge() {
    let both = announced_in(vec![
        facts_of(false, &[IMPL, SITE]),
        facts_of(false, &[IMPL, SITE]),
    ]);
    assert_eq!(
        selected(&collect(both)).len(),
        1,
        "every configuration has it"
    );
    let one = announced_in(vec![
        facts_of(false, &[IMPL, SITE]),
        facts_of(false, &[IMPL]),
    ]);
    let found = collect(one);
    assert!(
        selected(&found).is_empty(),
        "a feature alone cannot make an edge"
    );
    assert!(gap_from_a_to_b(&found), "the pair stays open");
}

#[test]
fn an_impl_in_a_module_of_another_file_than_its_scan_module_gives_no_edge() {
    // The module `app::b` maps to `ns.app.b`, but its impl module is a file that the scan does not hold.
    let loaded = r#"{"k":"sel","from":0,"to":1,"impl":6,"file":3,"impl_file":8,"line":1,"col":0}"#;
    let found = collect(announced(false, &[IMPL, loaded]));
    assert!(selected(&found).is_empty());
}

#[test]
fn configurations_that_select_the_impl_in_different_files_give_no_edge() {
    // `#[cfg_attr(.., path = ..)]` loads module `b` from another file in one configuration: the sites look alike.
    let cold = r#"{"k":"sel","from":0,"to":1,"impl":6,"file":3,"impl_file":9,"line":1,"col":28}"#;
    let hot = r#"{"k":"sel","from":0,"to":1,"impl":6,"file":3,"impl_file":8,"line":1,"col":28}"#;
    let found = collect(announced_in(vec![
        facts_of(false, &[IMPL, cold]),
        facts_of(false, &[IMPL, hot]),
    ]));
    assert!(selected(&found).is_empty());
}

const A_M: &str = "pub fn f() { crate::c::make().m(); }\n";
const B_M: &str = "pub struct S;\nimpl S { pub fn m(&self) {} }\n";
const C_M: &str = "pub fn make() -> crate::b::S { crate::b::S }\n";

fn collect_methods(announce: Announced) -> Collected {
    let tree = Tree::new(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", "pub fn f() {}"),
        ("crates/app/Cargo.toml", APP),
        (
            "crates/app/src/lib.rs",
            "pub mod a;\npub mod b;\npub mod c;\n",
        ),
        ("crates/app/src/a.rs", A_M),
        ("crates/app/src/b.rs", B_M),
        ("crates/app/src/c.rs", C_M),
    ]);
    let request = RustRequest {
        protocol_version: Version::V8,
        snapshot: Snapshot {
            root: tree.path(),
            git_head: "a".repeat(40),
            dirty: Dirty::Known(false),
        },
        scope: Scope {
            roots: vec!["crates".to_owned()],
            namespace: "ns".to_owned(),
            exclude_test_sources: Some(false),
        },
        resolver: RustSettings {},
    };
    let provenance = Provenance::native(Profile::Rust, ("1", "d"), ("1.88.0", "1.88"));
    crate::collect::collect_with(&request, provenance, |_, _| announce)
}

/// The record of a resolved method call at the method name of `A_M`, plus a column shift.
fn call(to: &str, callee_file: &str, shift: usize) -> String {
    let col = A_M.find("m()").unwrap() + shift;
    format!(
        "{{\"k\":\"call\",\"from\":0,\"to\":{to},\"callee\":6,\"file\":3,\"callee_file\":{callee_file},\"line\":1,\"col\":{col}}}"
    )
}

fn method_gap(found: &Collected) -> bool {
    found.gaps.iter().any(|gap| {
        gap.title
            .contains("method m of a type in its own file ns.app.b")
    })
}

fn edges_to(found: &Collected, target: &str) -> usize {
    let edges = selected(found);
    edges
        .iter()
        .filter(|r| r.data.data().target_module.as_str() == target)
        .count()
}

#[test]
fn an_unresolved_receiver_call_keeps_its_method_gap() {
    let found = collect_methods(announced(false, &[]));
    assert!(method_gap(&found), "the baseline holds the gap a -> b");
}

#[test]
fn a_call_that_the_compiler_resolved_outside_the_workspace_drops_the_gap() {
    let found = collect_methods(announced(false, &[&call("null", "null", 0)]));
    assert!(!method_gap(&found));
    assert!(selected(&found).is_empty(), "a foreign callee is no edge");
}

#[test]
fn a_call_resolved_to_another_module_drops_the_gap_and_is_an_edge() {
    let found = collect_methods(announced(false, &[&call("2", "10", 0)]));
    assert!(!method_gap(&found));
    assert_eq!(edges_to(&found, "ns.app.c"), 1);
}

#[test]
fn a_callee_in_the_file_of_the_candidate_keeps_the_gap_whatever_its_module_name() {
    // The module name of the callee maps to `c`, but the file is `b.rs`: only the file is verified.
    let found = collect_methods(announced(false, &[&call("2", "9", 0)]));
    assert!(method_gap(&found));
}

#[test]
fn a_call_resolved_to_the_candidate_keeps_the_gap_and_is_an_edge() {
    let found = collect_methods(announced(false, &[&call("1", "9", 0)]));
    assert!(method_gap(&found), "the named use of b stays held");
    assert_eq!(edges_to(&found, "ns.app.b"), 1);
}

#[test]
fn a_call_at_another_place_or_in_a_test_unit_keeps_the_gap() {
    let moved = collect_methods(announced(false, &[&call("null", "null", 1)]));
    assert!(method_gap(&moved), "another column is another call");
    let test = collect_methods(announced(true, &[&call("null", "null", 0)]));
    assert!(method_gap(&test), "test code decides nothing");
}

#[test]
fn every_configuration_must_resolve_the_call_to_the_same_callee() {
    let foreign = call("null", "null", 0);
    let both = announced_in(vec![
        facts_of(false, &[&foreign]),
        facts_of(false, &[&foreign]),
    ]);
    assert!(!method_gap(&collect_methods(both)));
    let lacking = announced_in(vec![facts_of(false, &[&foreign]), facts_of(false, &[])]);
    assert!(
        method_gap(&collect_methods(lacking)),
        "a feature can drop the call"
    );
    let other = announced_in(vec![
        facts_of(false, &[&foreign]),
        facts_of(false, &[&call("2", "10", 0)]),
    ]);
    assert!(
        method_gap(&collect_methods(other)),
        "a feature can change the callee"
    );
}
