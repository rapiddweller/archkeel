// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The sites of all modules of a scan: proven imports and hazards, with the names that the
//! modules re-export to each other (AD-450, AD-1094).

use std::collections::HashSet;

use super::binders::Binders;
use super::globals_read;
use super::hazards::{
    bindings, cleared, comprehension_trojans, proved, sites_with, table, Site, Split, BUILTINS,
    DYNAMIC, IMPORT_SYSTEM, LITERAL,
};
use super::hazards_names::{BUILTIN_TROJAN_HORSES, IMPORT_FUNCTIONS};
use super::lazy_cover::Lazy;
use super::literal;
use crate::module::Module;

/// The sites that the lazy import proof covers (`lazy.rs`) are no hazard when `lazy` is given.
pub(super) fn split(
    modules: &[Module],
    binders: &[Binders],
    (lazy, replaced): (Option<&[Lazy]>, bool),
    local_literals: bool,
) -> Split {
    let (mut literals, mut found) = (Vec::new(), Vec::new());
    let items: Vec<_> = modules
        .iter()
        .zip(binders)
        .map(|(m, b)| (&m.tree, b.unique(), bindings(&m.tree)))
        .collect();
    let reexports = table(items.iter().map(|(_, _, bound)| bound));
    let proved = proved(&items, &[&BUILTIN_TROJAN_HORSES, &IMPORT_FUNCTIONS]);
    let reads = globals_read::inert_reads(modules);
    for (index, (module, binders)) in modules.iter().zip(binders).enumerate() {
        let facts = binders.proof_facts(&BUILTINS);
        let cleared = cleared(&module.tree, &items[index].2, &facts);
        let mut proof = literal::Proof::of(&module.tree, binders).without_replaced_loader(replaced);
        proof.prove_local(&module.tree, local_literals);
        let covered = lazy.map(|all| &all[index]);
        for (range, target) in covered.iter().flat_map(|item| &item.targets) {
            literals.push((index, *range, target.clone()));
        }
        let named = comprehension_trojans((&module.tree, &module.name), &facts);
        let named = named
            .into_iter()
            .map(|(name, at)| Site::plain(DYNAMIC, name, at));
        for site in sites_with(&module.tree, proof, binders, &reads[index], &reexports)
            .into_iter()
            .chain(named)
        {
            let exempt = covered.iter().flat_map(|item| &item.exempt);
            let kind = (site.kind == DYNAMIC, site.kind == IMPORT_SYSTEM);
            if exempt
                .into_iter()
                .any(|range| range.contains_range(site.range))
                || HashSet::contains(&cleared, &site.range)
                || proved[index].covers(kind, &site.detail, site.range)
            {
                continue;
            }
            match site.kind {
                LITERAL => literals.push((index, site.range, site.detail)),
                _ => found.push((index, site)),
            }
        }
    }
    (literals, found)
}
