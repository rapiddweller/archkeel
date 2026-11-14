// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::collections::{BTreeMap, BTreeSet};

use super::{finish, Bucket, Key};

fn bucket() -> Bucket {
    Bucket {
        count: 1,
        ..Bucket::default()
    }
}

#[test]
fn one_pair_in_each_resolution_state_has_its_own_stable_identity() {
    let mut buckets: BTreeMap<Key, Bucket> = BTreeMap::new();
    for state in ["resolved", "unresolved", "external"] {
        buckets.insert(("a".to_owned(), "b".to_owned(), state), bucket());
    }
    let first = finish(buckets, "module");
    let ids: BTreeSet<_> = first.iter().map(|edge| edge.id.clone()).collect();
    assert_eq!(ids.len(), 3);
    let mut again: BTreeMap<Key, Bucket> = BTreeMap::new();
    for state in ["external", "unresolved", "resolved"] {
        again.insert(("a".to_owned(), "b".to_owned(), state), bucket());
    }
    let second: BTreeSet<_> = finish(again, "module").into_iter().map(|e| e.id).collect();
    assert_eq!(ids, second);
}

#[test]
fn a_level_and_a_pair_order_change_the_identity() {
    let key = |s: &str, t: &str| -> BTreeMap<Key, Bucket> {
        BTreeMap::from([((s.to_owned(), t.to_owned(), "resolved"), bucket())])
    };
    let id = |level, s, t| finish(key(s, t), level).remove(0).id;
    assert_ne!(id("module", "a", "b"), id("component", "a", "b"));
    assert_ne!(id("module", "a", "b"), id("module", "b", "a"));
}
