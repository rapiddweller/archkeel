// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The columnar layout of the typed rows and the one string table (AD-361 point 2).
//!
//! A string that the table does not hold gets the id `u32::MAX`, and a number above its column
//! type gets the largest value: the check then refuses the payload by name. So a layout fault
//! can never pass in silence, and the layout needs no panic.

use std::collections::{BTreeMap, BTreeSet};

use crate::codes::{Code, NodeLevel, UnknownReason, UnknownSource};
use crate::input::{
    EdgeRow, FindingRow, MeasureRow, NodeRow, PermissionRow, UnitRow, ViolationRow,
};
use crate::tables::{
    Carriers, Crossings, Edges, Findings, Measures, Nodes, Permissions, Units, Unknowns, Variants,
    Violations,
};

/// The cap of crossings per module edge.
pub(crate) const CROSSING_CAP: usize = 200;

/// The sorted, unique string table and the id of each string.
pub(crate) struct Strings {
    index: BTreeMap<String, u32>,
}

impl Strings {
    pub(crate) fn of(found: BTreeSet<String>) -> Strings {
        let index = found
            .into_iter()
            .enumerate()
            .map(|(id, text)| (text, u32::try_from(id).unwrap_or(u32::MAX)))
            .collect();
        Strings { index }
    }

    pub(crate) fn id(&self, text: &str) -> u32 {
        self.index.get(text).copied().unwrap_or(u32::MAX)
    }

    pub(crate) fn opt(&self, text: Option<&str>) -> i64 {
        text.map_or(-1, |text| i64::from(self.id(text)))
    }

    pub(crate) fn into_list(self) -> Vec<String> {
        self.index.into_keys().collect()
    }
}

pub(crate) fn opt_id(value: Option<u32>) -> i64 {
    value.map_or(-1, i64::from)
}

pub(crate) fn opt_count(value: Option<u64>) -> i64 {
    value.map_or(-1, |value| i64::try_from(value).unwrap_or(i64::MAX))
}

fn count(value: usize) -> u64 {
    u64::try_from(value).unwrap_or(u64::MAX)
}

/// One unknowns row before the layout.
#[derive(Clone, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct UnknownCell {
    pub(crate) source: u32,
    pub(crate) node: u32,
    pub(crate) reason: u32,
    pub(crate) kind: String,
    pub(crate) detail: String,
    pub(crate) rule: Option<String>,
}

impl UnknownCell {
    pub(crate) fn new(source: UnknownSource, kind: &str, node: u32, detail: &str) -> UnknownCell {
        UnknownCell {
            source: Code::of(source).value(),
            node,
            reason: Code::of(UnknownReason::of_kind(kind)).value(),
            kind: kind.to_owned(),
            detail: detail.to_owned(),
            rule: None,
        }
    }
}

/// The node that a reason names: a module first, then a file or a package; else the system.
pub(crate) fn node_of(names: &[&str], nodes: &[NodeRow]) -> u32 {
    let module = names.iter().find_map(|name| {
        nodes
            .iter()
            .position(|n| n.level == NodeLevel::Module && n.name == *name)
    });
    let place = names.iter().find_map(|name| {
        let file = nodes.iter().position(|n| n.path.as_deref() == Some(*name));
        file.or_else(|| {
            nodes
                .iter()
                .position(|n| n.level == NodeLevel::Package && n.name == *name)
        })
    });
    module
        .or(place)
        .map_or(0, |row| u32::try_from(row).unwrap_or(u32::MAX))
}

pub(crate) fn nodes(rows: &[NodeRow], s: &Strings) -> Nodes {
    let mut t = Nodes::default();
    for r in rows {
        t.level.push(Code::of(r.level));
        t.parent.push(opt_id(r.parent));
        t.key.push(s.id(&r.key));
        t.name.push(s.id(&r.name));
        t.path.push(s.opt(r.path.as_deref()));
        t.package.push(opt_id(r.package));
        t.modules.push(r.modules);
        t.units.push(r.units);
        t.fan_in.push(r.fan_in);
        t.fan_out.push(r.fan_out);
    }
    t
}

pub(crate) fn measures(rows: &[MeasureRow], s: &Strings) -> Measures {
    let mut t = Measures::default();
    for r in rows {
        t.node.push(r.node);
        t.def.push(Code::of(r.measure));
        t.state.push(Code::of(r.state));
        t.value.push(opt_count(r.value));
        t.of.push(opt_count(r.of));
        t.gap
            .push(r.gap.map_or(-1, |gap| i64::from(Code::of(gap).value())));
        t.budget.push(opt_count(r.budget));
        t.budget_source.push(s.opt(r.budget_source.as_deref()));
        t.baseline.push(opt_count(r.baseline));
        t.baseline_source.push(s.opt(r.baseline_source.as_deref()));
        t.verdict.push(Code::of(r.verdict));
    }
    t
}

pub(crate) fn units(rows: &[UnitRow], s: &Strings) -> (Units, Variants) {
    let (mut t, mut v) = (Units::default(), Variants::default());
    for (row, r) in rows.iter().enumerate() {
        t.module.push(r.module);
        t.name.push(s.id(&r.name));
        t.kind.push(Code::of(r.kind));
        t.vis.push(Code::of(r.vis));
        t.line.push(r.line);
        t.end_line.push(opt_count(r.end_line));
        t.parent.push(opt_id(r.parent));
        t.decl.push(s.id(&r.decl));
        t.is_static.push(u8::from(r.is_static));
        for name in &r.variants {
            v.unit.push(u32::try_from(row).unwrap_or(u32::MAX));
            v.name.push(s.id(name));
        }
    }
    (t, v)
}

pub(crate) fn edges(rows: &[EdgeRow], s: &Strings) -> (Edges, Vec<u32>, Crossings) {
    let (mut t, mut via, mut c) = (Edges::default(), Vec::new(), Crossings::default());
    let mut module_edge = 0u32;
    for r in rows {
        via.extend(&r.via);
        t.level.push(Code::of(r.level));
        t.from.push(r.from);
        t.to.push(r.to);
        t.names.push(r.names);
        t.sites.push(r.sites);
        t.target.push(Code::of(r.target));
        t.rationale.push(s.opt(r.rationale.as_deref()));
        t.omitted
            .push(count(r.crossings.len().saturating_sub(CROSSING_CAP)));
        t.via_end.push(count(via.len()));
        if r.level != NodeLevel::Module {
            continue;
        }
        for x in r.crossings.iter().take(CROSSING_CAP) {
            c.edge.push(module_edge);
            c.name.push(s.id(&x.name));
            c.kind.push(Code::of(x.kind));
            c.unit.push(opt_id(x.unit));
            c.sites.push(x.sites);
            c.line.push(opt_count(x.line));
            c.reexport.push(u8::from(x.reexport));
        }
        module_edge = module_edge.saturating_add(1);
    }
    (t, via, c)
}

pub(crate) fn permissions(rows: &[PermissionRow], s: &Strings) -> Permissions {
    let mut t = Permissions::default();
    for r in rows {
        t.component.push(r.component);
        t.target.push(r.target);
        t.status.push(Code::of(r.status));
        t.rule.push(s.opt(r.rule.as_deref()));
    }
    t
}

/// The violation table and its flat lists of rules, subjects and evidence.
pub(crate) fn violations(rows: &[ViolationRow], s: &Strings) -> (Violations, [Vec<u32>; 3]) {
    let mut t = Violations::default();
    let [mut rules, mut subjects, mut evidence] = [Vec::new(), Vec::new(), Vec::new()];
    for r in rows {
        rules.extend(r.rules.iter().map(|x| s.id(x)));
        subjects.extend(r.subjects.iter().map(|x| s.id(x)));
        evidence.extend(r.evidence.iter().map(|x| s.id(x)));
        t.kind.push(s.id(&r.kind));
        t.rules_end.push(count(rules.len()));
        t.subjects_end.push(count(subjects.len()));
        t.source_module.push(s.opt(r.source_module.as_deref()));
        t.target_module.push(s.opt(r.target_module.as_deref()));
        t.symbol.push(s.opt(r.symbol.as_deref()));
        t.source_component.push(opt_id(r.source_component));
        t.target_component.push(opt_id(r.target_component));
        t.evidence_end.push(count(evidence.len()));
        t.path.push(s.opt(r.path.as_deref()));
        t.line.push(opt_count(r.line));
        t.node.push(opt_id(r.node));
    }
    (t, [rules, subjects, evidence])
}

pub(crate) fn unknowns(rows: &[UnknownCell], s: &Strings) -> Unknowns {
    let mut t = Unknowns::default();
    for r in rows {
        t.source.push(Code::raw(r.source));
        t.reason.push(Code::raw(r.reason));
        t.kind.push(s.id(&r.kind));
        t.node.push(r.node);
        t.rule.push(s.opt(r.rule.as_deref()));
        t.detail.push(s.id(&r.detail));
    }
    t
}

pub(crate) fn findings(rows: &[FindingRow], s: &Strings) -> (Findings, Carriers) {
    let (mut t, mut c) = (Findings::default(), Carriers::default());
    for (r, row) in rows.iter().zip(0u32..) {
        t.kind.push(Code::of(r.kind));
        t.subject.push(r.subject);
        t.value.push(r.value);
        t.pool.push(opt_count(r.pool));
        t.absolute.push(opt_count(r.absolute));
        t.relative_permille.push(opt_count(r.relative_permille));
        t.disposition.push(Code::of(r.disposition));
        t.reason.push(Code::of(r.reason));
        t.carrier_total.push(r.carrier_total);
        t.gap
            .push(r.gap.map_or(-1, |gap| i64::from(Code::of(gap).value())));
        for (name, importers, unit) in &r.carriers {
            c.finding.push(row);
            c.name.push(s.id(name));
            c.importers.push(*importers);
            c.unit.push(opt_id(*unit));
        }
    }
    (t, c)
}
