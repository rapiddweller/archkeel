// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The row order of each table, as the schema states it. A string id orders as its string,
//! because the string table is sorted by UTF-8 bytes. A table whose order key is unique must be
//! strictly ascending, so a repeated row is refused too. The violation rows follow their record
//! ids, which the payload does not hold: their order is not checked.

use std::cmp::Reverse;

use crate::codes::Level;
use crate::payload::Payload;
use crate::problem::Problem;

/// The first row that breaks the order of its keys.
fn first_break<K: Ord>(keys: impl Iterator<Item = K>, strict: bool) -> Option<usize> {
    let mut previous: Option<K> = None;
    for (row, key) in keys.enumerate() {
        if let Some(before) = &previous {
            if key < *before || (strict && key == *before) {
                return Some(row);
            }
        }
        previous = Some(key);
    }
    None
}

fn check<K: Ord>(
    table: &'static str,
    keys: impl Iterator<Item = K>,
    strict: bool,
    found: &mut Vec<Problem>,
) {
    if let Some(row) = first_break(keys, strict) {
        found.push(Problem::RowOrder { table, row });
    }
}

/// Edges: module edges first, then component, then package.
fn edge_rank(level: crate::codes::Code<Level>) -> u8 {
    match level.known() {
        Some(Level::Module) => 0,
        Some(Level::Component) => 1,
        Some(Level::Package) => 2,
        Some(Level::System) | None => 3,
    }
}

pub(crate) fn order(p: &Payload, found: &mut Vec<Problem>) {
    check("rules", p.rules.iter().map(|r| r.id.as_str()), true, found);
    check(
        "components",
        p.components.iter().map(|c| c.node),
        true,
        found,
    );
    check("run.not_carried", p.run.not_carried.iter(), true, found);
    nodes(p, found);
    let m = &p.measures;
    check("measures", m.node.iter().zip(&m.def), true, found);
    let u = &p.units;
    let unit_keys = u.module.iter().zip(&u.line).zip(u.name.iter().zip(&u.kind));
    check("units", unit_keys, false, found);
    check("variants", p.variants.unit.iter(), false, found);
    let e = &p.edges;
    let edge_keys = e
        .level
        .iter()
        .map(|l| edge_rank(*l))
        .zip(e.from.iter().zip(&e.to));
    check("edges", edge_keys, true, found);
    check(
        "crossings",
        p.crossings.edge.iter().zip(&p.crossings.name),
        false,
        found,
    );
    let t = &p.permissions;
    check(
        "permissions",
        t.component.iter().zip(&t.target),
        true,
        found,
    );
    let k = &p.unknowns;
    let unknown_keys = k
        .source
        .iter()
        .zip(&k.node)
        .zip(k.reason.iter().zip(&k.kind))
        .zip(k.detail.iter().zip(&k.rule));
    check("unknowns", unknown_keys, false, found);
    let f = &p.findings;
    let finding_keys = f
        .disposition
        .iter()
        .zip(&f.kind)
        .zip(f.value.iter().map(Reverse).zip(&f.subject));
    check("findings", finding_keys, false, found);
    let c = &p.carriers;
    let carrier_keys = c
        .finding
        .iter()
        .zip(c.importers.iter().map(Reverse).zip(&c.name));
    check("carriers", carrier_keys, false, found);
    if let Some(t) = &p.fields {
        check("fields", t.unit.iter(), false, found);
    }
    if let Some(t) = &p.params {
        check("params", t.unit.iter().zip(&t.pos), false, found);
    }
}

/// Nodes: level, then depth, then key. The structure check proved that each parent is earlier.
/// The depth of a package or a component is its depth in its tree. A module has depth 0, as the
/// Python producer writes it: its parent is a component, and modules sort by key only.
fn nodes(p: &Payload, found: &mut Vec<Problem>) {
    let n = &p.nodes;
    let mut depth: Vec<usize> = Vec::with_capacity(n.parent.len());
    for parent in &n.parent {
        let above = usize::try_from(*parent)
            .ok()
            .and_then(|parent| depth.get(parent).copied());
        depth.push(above.map_or(0, |d| d.saturating_add(1)));
    }
    let module_depth = |(level, depth): (&crate::codes::Code<Level>, &usize)| {
        if level.is(Level::Module) {
            0
        } else {
            *depth
        }
    };
    let depths = n.level.iter().zip(&depth).map(module_depth);
    let keys = n.level.iter().zip(depths.zip(&n.key));
    check("nodes", keys, true, found);
}
