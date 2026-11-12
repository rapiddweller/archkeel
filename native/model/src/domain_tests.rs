// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The source domain of one mount (AD-385).

use std::collections::HashSet;

use super::Domain;
use crate::ids::{id_of, ModuleId};

fn domain() -> Domain {
    Domain::new(
        vec![id_of::<ModuleId>(1)],
        HashSet::from(["p.a.m".to_owned()]),
        vec!["p.a".to_owned()],
    )
}

#[test]
fn a_domain_holds_only_its_modules_and_reads_whole_segments_of_its_roots() {
    let domain = domain();
    assert!(!domain.holds(id_of::<ModuleId>(0)));
    assert!(domain.holds(id_of::<ModuleId>(1)));
    // A module beyond the table is outside the domain.
    assert!(!domain.holds(id_of::<ModuleId>(2)));
    // AD-385, N3 of the review of #1086: a domain holds its own modules only, so its size grows
    // with the mount and not with the reply.
    assert_eq!(domain.held(), [id_of::<ModuleId>(1)]);
    assert!(domain.selects("p.a.m"));
    assert!(!domain.selects("p.b.m"));
    assert!(domain.below_roots("p.a"));
    assert!(domain.below_roots("p.a.x"));
    assert!(!domain.below_roots("p.ab"));
}
