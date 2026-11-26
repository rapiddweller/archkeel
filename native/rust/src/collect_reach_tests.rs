// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// AD-1120: the reply carries the provenance of the type-reach facts only when the scan used them.

use crate::collect::tests::{APP, BASE, WORKSPACE};
use archkeel_facts::envelope::{Dirty, Profile, Provenance};
use archkeel_facts::request::{RustRequest, RustSettings, Scope, Snapshot};
use archkeel_snapshot::test_tree::Tree;
use archkeel_wire::protocol::Version;

fn reached() -> crate::type_reach::Reached {
    crate::type_reach::Reached {
        rustc: "rustc 1.97.0\n".to_owned(),
        target_triple: "aarch64-apple-darwin".to_owned(),
        driver_sha256: "d".repeat(64),
        cargo_lock_sha256: "c".repeat(64),
        members: vec!["crates/app/".to_owned()],
        configs: ["default", "no-default-features", "all-features"]
            .map(str::to_owned)
            .to_vec(),
    }
}

/// One facts file that names one module as the driver does: `<crate>::<module>`, without the namespace.
fn reach(module: &str) -> crate::type_reach::Announced {
    let mut facts = crate::type_reach_facts::Facts::empty();
    let text = format!(
        "{{\"k\":\"build\"}}\n{{\"k\":\"str\",\"v\":[\"{module}\",\"f\"]}}\n{}",
        "{\"k\":\"mod\",\"m\":0,\"file\":1,\"mentions\":[],\"dyn\":[],\"opaque\":[],\"dyn_in\":[]}"
    );
    facts.absorb(&text).unwrap();
    Some(Ok((vec![facts], reached())))
}

fn typed(announce: crate::type_reach::Announced) -> archkeel_facts::envelope::Reply {
    let tree = Tree::new(&[
        ("crates/Cargo.toml", WORKSPACE),
        ("crates/base/Cargo.toml", BASE),
        ("crates/base/src/lib.rs", "pub fn f() {}"),
        ("crates/app/Cargo.toml", APP),
        ("crates/app/src/lib.rs", "pub fn g() {}"),
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
        .typed(Version::V8)
        .unwrap()
}

#[test]
fn a_reply_with_used_facts_carries_the_typed_fact() {
    let reply = typed(reach("app"));
    let fact = reply.facts.type_reach.expect("a fact");
    assert_eq!(fact.configs, reached().configs);
    assert_eq!(fact.members, reached().members);
    assert_eq!(fact.driver_sha256, reached().driver_sha256);
}

#[test]
fn a_reply_without_facts_carries_none() {
    assert_eq!(typed(None).facts.type_reach, None);
}

#[test]
fn unavailable_facts_and_facts_of_another_scan_carry_none() {
    let failed = typed(Some(Err("cargo check failed".to_owned())));
    assert_eq!(failed.facts.type_reach, None);
    assert_eq!(typed(reach("other")).facts.type_reach, None);
}
