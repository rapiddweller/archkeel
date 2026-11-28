// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

fn proofs(causes: &[bool], erased: bool) -> (Option<ResolutionDimension>, bool) {
    let mut builder = Builder::default();
    builder.gap("unread caller", None, "src");
    let mut pending = PendingPool::new();
    for &execution in causes {
        pending.push(
            &mut builder,
            ("src", "dst"),
            ("src.rs", &Site::default()),
            &format!("candidate {execution}"),
            (erased && execution, execution, execution),
            None,
        );
    }
    let root = archkeel_snapshot::test_tree::Tree::new(&[]);
    let mut source = archkeel_snapshot::Snapshot::new(&root.path());
    let workspace = crate::crates::discover(&mut source, &[], "ns");
    let index = crate::modules::index(&workspace, &[]);
    let homes = LazyHomes {
        trait_homes: Vec::new(),
        drop_homes: Vec::new(),
        crate_deps: Vec::new(),
    };
    settle(&mut builder, pending, (&index, &[]), &homes);
    let gaps = builder.materialize_test_gaps();
    let pair = gaps
        .iter()
        .find(|gap| gap.data.data().source_module.is_some());
    let data = pair.expect("the pair is reachable").data.data();
    (data.resolution_dimension, data.no_name_route)
}

#[test]
fn a_named_cause_stays_open_before_or_after_an_execution_cause() {
    assert_eq!(
        proofs(&[true], false),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(
        proofs(&[true, true], false),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(proofs(&[true, false], false), (None, false));
    assert_eq!(proofs(&[false, true], false), (None, false));
    assert_eq!(proofs(&[true, false, true], false), (None, false));
}

#[test]
fn an_erased_destructor_is_execution_unless_the_pair_has_a_named_cause() {
    assert_eq!(
        proofs(&[true], true),
        (Some(ResolutionDimension::RuntimeEffects), true)
    );
    assert_eq!(proofs(&[true, false], true), (None, false));
    assert_eq!(proofs(&[false, true], true), (None, false));
}

#[test]
fn compact_named_sites_stream_in_unknown_id_order_and_merge_no_name_route() {
    let mut builder = Builder::default();
    let site_a = Site {
        line: 3,
        end_line: 3,
        column: 1,
        excerpt: "a.f()".to_owned(),
    };
    let site_b = Site {
        line: 7,
        end_line: 7,
        column: 1,
        excerpt: "b.g()".to_owned(),
    };
    builder.named_site(("src", "dst"), ("src.rs", &site_a), "reason a", true);
    builder.named_site(("src", "dst"), ("src.rs", &site_a), "reason a", false);
    builder.named_site(("src", "dst"), ("src.rs", &site_b), "reason b", true);
    let (_, holder) = builder.take_gaps_and_named_sites();
    let mut emitted = Vec::new();
    holder.stream_named_sites(&mut |record| emitted.push(record.clone()));
    assert_eq!(emitted.len(), 2);
    assert!(emitted[0].id < emitted[1].id);
    let merged = emitted
        .iter()
        .find(|record| record.title == "reason a")
        .expect("merged site");
    assert!(!merged.data.data().no_name_route);
}

#[path = "impl_flow_differential_tests.rs"]
mod differential;
