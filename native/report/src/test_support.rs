// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test support: the outcome and the records that an oracle payload was built from.
//!
//! It reads a decoded payload back into the inputs of `build`, so a test can build the frame
//! again and compare the bytes with the Python producer. A PASS can only come from the scope
//! proof of the model (AD-363), so a payload with a PASS rule or a complete observation has no
//! inputs here: `inputs` answers `None` for it.

use std::path::PathBuf;

use crate::{
    Code, CodeList, ComponentText, CrossingRow, Diagnostic, EdgeRow, FindingRow, Graph, Level,
    MeasureRow, NodeRow, OptId, Payload, PermissionRow, Produced, Records, RuleDecision,
    RuleOutcome, RuleReason, RuleVerdict, RunFacts, RunOutcome, Status, Target, Tree, Undecided,
    UnitRow, UnknownRecord, UnknownSource, ViolationRow, WhyUnknown,
};
use archkeel_model::{Decision, Reason, Unsupported};

pub(crate) const BUILDABLE: [&str; 4] = [
    "E-runtime",
    "F-typescript-story",
    "L-nest-realworld",
    "golden-synthetic-excluded-tests",
];

pub(crate) fn bytes(name: &str) -> Vec<u8> {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("testdata")
        .join(format!("{name}.report-v2.json"));
    std::fs::read(&path).unwrap()
}

fn text(p: &Payload, id: u32) -> String {
    p.strings[usize::try_from(id).unwrap()].clone()
}

fn opt_text(p: &Payload, id: i64) -> Option<String> {
    u32::try_from(id).ok().map(|id| text(p, id))
}

fn opt_u32(id: OptId) -> Option<u32> {
    u32::try_from(id).ok()
}

fn opt_u64(value: i64) -> Option<u64> {
    u64::try_from(value).ok()
}

fn known<L: CodeList>(code: Code<L>) -> L {
    code.known().unwrap()
}

fn gap(cell: i64) -> Option<crate::Gap> {
    crate::opt_gap(cell).map(known)
}

fn decision(status: Status) -> Option<Decision> {
    match status {
        Status::Pass => None,
        Status::Fail => Some(Decision::fail()),
        Status::Unknown => Some(Decision::unknown(Reason::Unsupported(
            Unsupported::ScopeProof,
        ))),
    }
}

fn tree(p: &Payload) -> Tree {
    let n = &p.nodes;
    let nodes = (0..n.level.len())
        .map(|i| NodeRow {
            level: known(n.level[i]),
            parent: opt_u32(n.parent[i]),
            key: text(p, n.key[i]),
            name: text(p, n.name[i]),
            path: opt_text(p, n.path[i]),
            package: opt_u32(n.package[i]),
            modules: n.modules[i],
            units: n.units[i],
            fan_in: n.fan_in[i],
            fan_out: n.fan_out[i],
        })
        .collect();
    let components = p
        .components
        .iter()
        .map(|c| ComponentText {
            node: c.node,
            does: c.does.clone(),
            never: c.never.clone(),
            decided_by: c.decided_by.clone(),
            provenance: c.provenance.clone(),
            role: c.role.clone(),
            public_api: c.public_api.clone(),
        })
        .collect();
    Tree {
        nodes,
        components,
        unowned_modules: p.summary.counts.unowned_modules,
    }
}

fn measures(p: &Payload) -> Vec<MeasureRow> {
    let m = &p.measures;
    (0..m.node.len())
        .map(|i| MeasureRow {
            node: m.node[i],
            measure: known(m.def[i]),
            state: known(m.state[i]),
            value: opt_u64(m.value[i]),
            of: opt_u64(m.of[i]),
            gap: gap(m.gap[i]),
            budget: opt_u64(m.budget[i]),
            budget_source: opt_text(p, m.budget_source[i]),
            baseline: opt_u64(m.baseline[i]),
            baseline_source: opt_text(p, m.baseline_source[i]),
            verdict: known(m.verdict[i]),
        })
        .collect()
}

fn units(p: &Payload) -> Vec<UnitRow> {
    let u = &p.units;
    (0..u.module.len())
        .map(|i| UnitRow {
            module: u.module[i],
            name: text(p, u.name[i]),
            kind: known(u.kind[i]),
            vis: known(u.vis[i]),
            line: u.line[i],
            end_line: opt_u64(u.end_line[i]),
            parent: opt_u32(u.parent[i]),
            decl: text(p, u.decl[i]),
            is_static: u.is_static[i] == 1,
            variants: (0..p.variants.unit.len())
                .filter(|v| usize::try_from(p.variants.unit[*v]).unwrap() == i)
                .map(|v| text(p, p.variants.name[v]))
                .collect(),
        })
        .collect()
}

fn graph(p: &Payload) -> Graph {
    let e = &p.edges;
    let mut module_edge = 0u32;
    let mut start = 0usize;
    let mut edges = Vec::new();
    for i in 0..e.level.len() {
        let end = usize::try_from(e.via_end[i]).unwrap();
        let level: Level = known(e.level[i]);
        let c = &p.crossings;
        let crossings: Vec<CrossingRow> = if level == Level::Module {
            (0..c.edge.len())
                .filter(|x| c.edge[*x] == module_edge)
                .map(|x| CrossingRow {
                    name: text(p, c.name[x]),
                    kind: known(c.kind[x]),
                    unit: opt_u32(c.unit[x]),
                    sites: c.sites[x],
                    line: opt_u64(c.line[x]),
                    reexport: c.reexport[x] == 1,
                })
                .collect()
        } else {
            Vec::new()
        };
        assert_eq!(
            e.omitted[i], 0,
            "the support reads no edge above the crossing cap"
        );
        if level == Level::Module {
            module_edge += 1;
        }
        edges.push(EdgeRow {
            level,
            from: e.from[i],
            to: e.to[i],
            names: e.names[i],
            sites: e.sites[i],
            target: known(e.target[i]),
            rationale: opt_text(p, e.rationale[i]),
            via: p.via[start..end].to_vec(),
            crossings,
        });
        start = end;
    }
    Graph { edges }
}

fn flat(p: &Payload, list: &[u32], ends: &[u64], row: usize) -> Vec<String> {
    let start = if row == 0 {
        0
    } else {
        usize::try_from(ends[row - 1]).unwrap()
    };
    let end = usize::try_from(ends[row]).unwrap();
    list[start..end].iter().map(|id| text(p, *id)).collect()
}

fn violations(p: &Payload) -> Vec<ViolationRow> {
    let v = &p.violations;
    (0..v.kind.len())
        .map(|i| ViolationRow {
            kind: text(p, v.kind[i]),
            rules: flat(p, &p.violation_rules, &v.rules_end, i),
            subjects: flat(p, &p.violation_subjects, &v.subjects_end, i),
            source_module: opt_text(p, v.source_module[i]),
            target_module: opt_text(p, v.target_module[i]),
            symbol: opt_text(p, v.symbol[i]),
            source_component: opt_u32(v.source_component[i]),
            target_component: opt_u32(v.target_component[i]),
            evidence: flat(p, &p.violation_evidence, &v.evidence_end, i),
            path: opt_text(p, v.path[i]),
            line: opt_u64(v.line[i]),
            node: opt_u32(v.node[i]),
        })
        .collect()
}

/// The names that lead `build` to the node of an unknowns row.
fn names_of(p: &Payload, node: u32) -> Vec<String> {
    let i = usize::try_from(node).unwrap();
    if node == 0 {
        return Vec::new();
    }
    vec![text(p, p.nodes.name[i])]
}

fn unknowns(p: &Payload) -> (Vec<UnknownRecord>, Vec<Diagnostic>) {
    let u = &p.unknowns;
    let (mut records, mut diagnostics) = (Vec::new(), Vec::new());
    for i in 0..u.source.len() {
        let names = names_of(p, u.node[i]);
        let (kind, detail) = (text(p, u.kind[i]), text(p, u.detail[i]));
        match known(u.source[i]) {
            UnknownSource::Record => records.push(UnknownRecord {
                kind,
                module: None,
                subjects: names,
                rules: opt_text(p, u.rule[i]).into_iter().collect(),
                title: detail,
            }),
            UnknownSource::Diagnostic => diagnostics.push(Diagnostic {
                kind,
                subject: names.into_iter().next().unwrap_or_default(),
                claim: detail,
            }),
            UnknownSource::Run => {}
        }
    }
    (records, diagnostics)
}

fn findings(p: &Payload) -> Vec<FindingRow> {
    let f = &p.findings;
    let c = &p.carriers;
    (0..f.kind.len())
        .map(|i| FindingRow {
            kind: known(f.kind[i]),
            subject: f.subject[i],
            value: f.value[i],
            pool: opt_u64(f.pool[i]),
            absolute: opt_u64(f.absolute[i]),
            relative_permille: opt_u64(f.relative_permille[i]),
            disposition: known(f.disposition[i]),
            reason: known(f.reason[i]),
            carrier_total: f.carrier_total[i],
            gap: gap(f.gap[i]),
            carriers: (0..c.finding.len())
                .filter(|x| usize::try_from(c.finding[*x]).unwrap() == i)
                .map(|x| (text(p, c.name[x]), c.importers[x], opt_u32(c.unit[x])))
                .collect(),
        })
        .collect()
}

/// The inputs of a payload without PASS, or `None` when a PASS needs the scope proof.
pub(crate) fn inputs(p: &Payload) -> Option<(RunOutcome, Records)> {
    let mut rules = Vec::new();
    for r in &p.rules {
        let decision = match r.verdict {
            RuleVerdict::Pass => return None,
            RuleVerdict::Fail => RuleDecision::Decided(Decision::fail()),
            RuleVerdict::Unknown => RuleDecision::Decided(decision(Status::Unknown)?),
            RuleVerdict::Declaration => RuleDecision::Declaration,
        };
        let undecided = usize::try_from(r.undecided).unwrap();
        rules.push(RuleOutcome {
            id: r.id.clone(),
            kind: r.kind.clone(),
            title: r.title.clone(),
            decision,
            evaluated: r.evaluated,
            why_unknown: match r.reason {
                RuleReason::ScopeIncomplete => Some(WhyUnknown::ScopeIncomplete),
                RuleReason::NoReceipt => Some(WhyUnknown::NoReceipt),
                RuleReason::Undecided => Some(WhyUnknown::Undecided),
                RuleReason::OwnershipBlocker => Some(WhyUnknown::OwnershipBlocker),
                _ => None,
            },
            undecided: vec![
                Undecided {
                    subject: String::new()
                };
                undecided
            ],
            rationale: r.rationale.clone(),
            decided_by: r.decided_by.clone(),
        });
    }
    let (unknown_records, diagnostics) = unknowns(p);
    decision(p.summary.status)?;
    let outcome = RunOutcome {
        target: if p.run.target {
            Target::Present
        } else {
            Target::Absent
        },
        observation: decision(p.run.observation)?,
        rules,
        diagnostics,
    };
    let records = Records {
        run: RunFacts {
            language: p.run.language.clone(),
            git_head: p.run.source.git_head.clone(),
            dirty: p.run.source.dirty,
            scope: p.run.source.scope.clone(),
            contract: p.run.contract.clone(),
            coverage: p.run.coverage,
        },
        tree: Produced::Rows(tree(p)),
        measures: Produced::Rows(measures(p)),
        units: Produced::Rows(units(p)),
        graph: Produced::Rows(graph(p)),
        permissions: Produced::Rows(
            (0..p.permissions.component.len())
                .map(|i| PermissionRow {
                    component: p.permissions.component[i],
                    target: p.permissions.target[i],
                    status: known(p.permissions.status[i]),
                    rule: opt_text(p, p.permissions.rule[i]),
                })
                .collect(),
        ),
        violations: Produced::Rows(violations(p)),
        unknowns: Produced::Rows(unknown_records),
        findings: Produced::Rows(findings(p)),
    };
    Some((outcome, records))
}
