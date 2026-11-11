// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The structure part of the check: column lengths, ids, offsets, the node tree, flags and codes.

use crate::codes::{Code, CodeList, Gap, Level};
use crate::payload::Payload;
use crate::problem::Problem;
use crate::tables::OptGap;
use crate::tables::{
    Carriers, Columns, Crossings, Edges, Fields, Findings, Measures, Nodes, Params, Permissions,
    Units, Unknowns, Variants, Violations,
};

/// The length of each column of each table.
fn columns(p: &Payload) -> Vec<(&'static str, Vec<usize>)> {
    let mut out = vec![
        ("nodes", Nodes::lengths(&p.nodes)),
        ("measures", Measures::lengths(&p.measures)),
        ("units", Units::lengths(&p.units)),
        ("variants", Variants::lengths(&p.variants)),
        ("edges", Edges::lengths(&p.edges)),
        ("crossings", Crossings::lengths(&p.crossings)),
        ("permissions", Permissions::lengths(&p.permissions)),
        ("violations", Violations::lengths(&p.violations)),
        ("unknowns", Unknowns::lengths(&p.unknowns)),
        ("findings", Findings::lengths(&p.findings)),
        ("carriers", Carriers::lengths(&p.carriers)),
    ];
    out.extend(p.fields.as_ref().map(|t| ("fields", Fields::lengths(t))));
    out.extend(p.params.as_ref().map(|t| ("params", Params::lengths(t))));
    out
}

fn ids(values: &[u32], size: usize, column: &'static str, found: &mut Vec<Problem>) {
    if let Some(bad) = values
        .iter()
        .find(|v| usize::try_from(**v).map_or(true, |v| v >= size))
    {
        found.push(Problem::IdOutOfRange {
            column,
            value: i64::from(*bad),
            size,
        });
    }
}

fn opt_ids(values: &[i64], size: usize, column: &'static str, found: &mut Vec<Problem>) {
    let outside = |v: i64| v < -1 || (v >= 0 && usize::try_from(v).map_or(true, |v| v >= size));
    if let Some(bad) = values.iter().find(|v| outside(**v)) {
        found.push(Problem::IdOutOfRange {
            column,
            value: *bad,
            size,
        });
    }
}

fn codes<L: CodeList>(values: &[Code<L>], found: &mut Vec<Problem>) {
    if let Some(bad) = values.iter().find(|code| code.known().is_none()) {
        found.push(Problem::UnknownCode {
            list: L::NAME,
            value: bad.value(),
        });
    }
}

fn gap_cells(values: &[OptGap], column: &'static str, found: &mut Vec<Problem>) {
    opt_ids(values, Gap::VALUES.len(), column, found);
}

fn offsets(ends: &[u64], flat: usize, column: &'static str, found: &mut Vec<Problem>) {
    let ascending = ends.windows(2).all(|pair| pair.first() <= pair.get(1));
    let last = ends.last().map_or(0, |end| *end);
    if !ascending
        || usize::try_from(last).is_ok_and(|last| last != flat)
        || usize::try_from(last).is_err()
    {
        found.push(Problem::OffsetEnd { column });
    }
}

fn flags(values: &[u8], column: &'static str, found: &mut Vec<Problem>) {
    if values.iter().any(|flag| *flag > 1) {
        found.push(Problem::FlagRange { column });
    }
}

/// The structure rules. A problem here stops the row rules.
pub(crate) fn structure(p: &Payload, found: &mut Vec<Problem>) {
    for (table, lengths) in columns(p) {
        if lengths.windows(2).any(|pair| pair.first() != pair.get(1)) {
            found.push(Problem::ColumnLengths { table });
        }
    }
    if p.strings.windows(2).any(|pair| pair.first() >= pair.get(1)) {
        found.push(Problem::StringsNotSorted);
    }
    references(p, found);
    strings(p, found);
    optional_tables(p, found);
    offsets(&p.edges.via_end, p.via.len(), "edges.via_end", found);
    offsets(
        &p.violations.rules_end,
        p.violation_rules.len(),
        "violations.rules_end",
        found,
    );
    offsets(
        &p.violations.subjects_end,
        p.violation_subjects.len(),
        "violations.subjects_end",
        found,
    );
    offsets(
        &p.violations.evidence_end,
        p.violation_evidence.len(),
        "violations.evidence_end",
        found,
    );
    let parents = &p.nodes.parent;
    let late = parents
        .iter()
        .enumerate()
        .skip(1)
        .any(|(row, parent)| usize::try_from(*parent).map_or(true, |parent| parent >= row));
    if parents.first() != Some(&-1) || late {
        found.push(Problem::ParentOrder);
    }
    flags(&p.units.is_static, "units.static", found);
    flags(&p.crossings.reexport, "crossings.reexport", found);
    code_columns(p, found);
}

/// The column name of a path such as `p.units.module`, as the problem names it.
fn column(path: &'static str) -> &'static str {
    path.trim_start_matches("p.")
}

/// Each column holds row ids below the size; -1 is absent only in an optional column.
macro_rules! ids {
    ($found:expr, $size:expr; $($column:expr),+ $(,)?) => {
        $(ids(&$column, $size, column(stringify!($column)), $found);)+
    };
}

macro_rules! opt_ids {
    ($found:expr, $size:expr; $($column:expr),+ $(,)?) => {
        $(opt_ids(&$column, $size, column(stringify!($column)), $found);)+
    };
}

fn references(p: &Payload, found: &mut Vec<Problem>) {
    let nodes = p.nodes.level.len();
    let units = p.units.module.len();
    let edges = p.edges.level.iter().filter(|l| l.is(Level::Module)).count();
    ids!(found, nodes; p.measures.node, p.units.module, p.edges.from, p.edges.to);
    ids!(found, nodes; p.permissions.component, p.permissions.target);
    ids!(found, nodes; p.unknowns.node, p.findings.subject);
    ids!(found, units; p.variants.unit);
    ids!(found, edges; p.via, p.crossings.edge);
    ids!(found, p.findings.kind.len(); p.carriers.finding);
    opt_ids!(found, nodes; p.nodes.parent, p.nodes.package, p.violations.node);
    opt_ids!(found, nodes; p.violations.source_component, p.violations.target_component);
    opt_ids!(found, units; p.units.parent, p.crossings.unit, p.carriers.unit);
}

/// The ids of the optional tables: units and strings.
fn optional_tables(p: &Payload, found: &mut Vec<Problem>) {
    let (units, n) = (p.units.module.len(), p.strings.len());
    if let Some(fields) = &p.fields {
        ids!(found, units; fields.unit);
        opt_ids!(found, units; fields.type_unit);
        ids!(found, n; fields.name, fields.type_name);
    }
    if let Some(params) = &p.params {
        ids!(found, units; params.unit);
        opt_ids!(found, units; params.type_unit);
        ids!(found, n; params.type_name);
        opt_ids!(found, n; params.name);
    }
}

fn strings(p: &Payload, found: &mut Vec<Problem>) {
    let n = p.strings.len();
    ids!(found, n; p.nodes.key, p.nodes.name, p.units.name, p.units.decl, p.variants.name);
    ids!(found, n; p.crossings.name, p.violations.kind, p.unknowns.kind, p.unknowns.detail);
    ids!(found, n; p.carriers.name, p.violation_rules, p.violation_subjects);
    ids!(found, n; p.violation_evidence);
    opt_ids!(found, n; p.nodes.path, p.measures.budget_source, p.measures.baseline_source);
    opt_ids!(found, n; p.edges.rationale, p.permissions.rule, p.unknowns.rule);
    opt_ids!(found, n; p.violations.source_module, p.violations.target_module);
    opt_ids!(found, n; p.violations.symbol, p.violations.path);
}

/// Each code column holds only codes that this crate can read.
macro_rules! codes {
    ($found:expr; $($column:expr),+ $(,)?) => {
        $(codes(&$column, $found);)+
    };
}

fn code_columns(p: &Payload, found: &mut Vec<Problem>) {
    let (m, u, e, k, f) = (&p.measures, &p.units, &p.edges, &p.unknowns, &p.findings);
    codes!(found; p.nodes.level, m.def, m.state, m.verdict, u.kind, u.vis, e.level, e.target);
    codes!(found; p.crossings.kind, p.permissions.status, k.source, k.reason, f.kind);
    codes!(found; f.disposition, f.reason, p.run.not_carried);
    gap_cells(&m.gap, "measures.gap", found);
    gap_cells(&f.gap, "findings.gap", found);
    let gaps: Vec<Code<Gap>> = p.gaps.iter().map(|row| row.gap).collect();
    codes(&gaps, found);
    for point in &p.trend {
        codes(&point.measure, found);
    }
}
