// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The class of a gap and the stable key of the cause (AD-564).

use archkeel_facts::data::{GapData, GapEffect};
use archkeel_facts::ids::ModuleName;

use super::{class, Class, Doubt, Scoped};
use crate::causes::Cause;
use crate::reason::Reason;
use crate::reason_key::stable;

fn names(names: &[&str]) -> Vec<ModuleName> {
    names.iter().map(|name| ModuleName::new(*name)).collect()
}

fn gap(source: Option<&str>, effect: Option<GapEffect>) -> GapData {
    let mut data = GapData::at("site", "shop.a");
    data.source_module = source.map(ModuleName::new);
    data.effect = effect;
    data
}

#[test]
fn each_doubt_of_a_gap_goes_to_the_wider_class() {
    let known = |name: &str| name == "shop.a" || name == "shop.b";
    let edges = |sources: &[&str]| {
        Some(GapEffect::Edges {
            sources: names(sources),
        })
    };
    let modules = |modules: &[&str]| {
        Some(GapEffect::Modules {
            modules: names(modules),
        })
    };
    let layout = |modules: &[&str]| {
        Some(GapEffect::Layout {
            modules: names(modules),
        })
    };
    let rows = [
        (gap(None, None), Class::Whole),
        (gap(Some("shop.b"), None), Class::Pair),
        // The two names of a pair form are one module: it is no pair (`coverage::droppable`).
        (gap(Some("shop.a"), None), Class::Whole),
        (gap(None, edges(&["shop.a"])), Class::Effect),
        (gap(None, modules(&["shop.a", "shop.b"])), Class::Effect),
        (gap(None, Some(GapEffect::EveryModule)), Class::Effect),
        (gap(None, edges(&[])), Class::Whole),
        (gap(None, modules(&[])), Class::Whole),
        (gap(None, edges(&["shop.a", "shop.c"])), Class::Whole),
        (gap(None, modules(&["shop.c"])), Class::Whole),
        (gap(None, layout(&["shop.a"])), Class::Effect),
        (gap(None, layout(&[])), Class::Whole),
        (gap(None, layout(&["shop.c"])), Class::Whole),
        (gap(Some("shop.b"), layout(&["shop.a"])), Class::Whole),
        (gap(Some("shop.b"), edges(&["shop.a"])), Class::Whole),
        (
            gap(Some("shop.b"), Some(GapEffect::EveryModule)),
            Class::Whole,
        ),
    ];
    for (data, expected) in rows {
        assert_eq!(class(&data, &known), expected, "{data:?}");
    }
}

fn scoped(ids: &[&str], doubts: Vec<Doubt>) -> Scoped {
    Scoped {
        ids: ids.iter().map(|id| (*id).to_owned()).collect(),
        doubts,
    }
}

#[test]
fn the_cause_names_the_doubts_and_its_key_holds_no_gap_id() {
    let doubts = vec![
        Doubt::Edges("shop.a".to_owned()),
        Doubt::Code("shop.b".to_owned()),
        Doubt::EveryModule,
    ];
    let first = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-1", "U-2"], doubts.clone())));
    assert_eq!(
        first.to_string(),
        "incomplete scope: 2 gaps leave unknown what the rule reads: the import edges \
         of shop.a, the code of shop.b, the code of every module"
    );
    let key = stable(&first);
    let words: Vec<(&str, &str)> = key
        .iter()
        .map(|entry| (entry.kind.as_str(), entry.reason.as_str()))
        .collect();
    assert_eq!(
        words,
        [
            ("gap_effect", "edges: shop.a"),
            ("gap_effect", "modules: shop.b"),
            ("gap_effect", "every_module"),
        ]
    );
    // The same doubts of other gaps are the same key; another doubt is another key.
    let moved = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-9"], doubts)));
    assert_eq!(stable(&moved), key);
    let other = vec![Doubt::Edges("shop.c".to_owned())];
    let other = Reason::NotComplete(Cause::ScopedGaps(scoped(&["U-1", "U-2"], other)));
    assert_ne!(stable(&other), key);
}
