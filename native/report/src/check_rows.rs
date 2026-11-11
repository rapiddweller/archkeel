// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The row part of the check: measures, gaps, counts, the status, the explaining rows, the rule
//! citations and the permissions. It runs only on a payload whose structure is sound, so every id
//! is in range; it still reads cells with `get`, so a broken id can never panic.

use std::collections::{BTreeMap, BTreeSet};

use crate::codes::{
    Code, CodeList, Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, MeasureState,
    Permission, Relation, UnknownSource, Verdict,
};
use crate::head::{Counts, RuleVerdict};
use crate::payload::Payload;
use crate::problem::Problem;
use crate::status::{status_of, unexplained};

pub(crate) fn rows(p: &Payload, found: &mut Vec<Problem>) {
    measures(p, found);
    gaps(p, found);
    counts(p, found);
    let stated = p.summary.status;
    let rule = status_of(p);
    if stated != rule {
        found.push(Problem::Status { stated, rule });
    }
    found.extend(unexplained(p, stated).into_iter().map(Problem::Unexplained));
    citations(p, found);
    for rule in &p.rules {
        if rule.verdict == RuleVerdict::Pass && !rule.evaluated {
            found.push(Problem::PassWithoutReceipt {
                rule: rule.id.clone(),
            });
        }
    }
    if p.run.target && p.unknowns.source.iter().any(|s| s.is(UnknownSource::Run)) {
        found.push(Problem::RunRowWithTarget);
    }
    permissions(p, found);
}

fn measures(p: &Payload, found: &mut Vec<Problem>) {
    let m = &p.measures;
    for row in 0..m.node.len() {
        let cells = (
            m.state.get(row),
            m.value.get(row),
            m.gap.get(row),
            m.budget.get(row),
            m.baseline.get(row),
            m.verdict.get(row),
        );
        let (Some(state), Some(value), Some(gap), Some(budget), Some(baseline), Some(verdict)) =
            cells
        else {
            continue;
        };
        let wanted = if *budget >= 0 {
            Some(if value >= budget {
                Verdict::Within
            } else {
                Verdict::Over
            })
        } else if *baseline < 0 {
            Some(Verdict::None)
        } else {
            None
        };
        if wanted.is_some_and(|wanted| !verdict.is(wanted)) {
            found.push(Problem::MeasureVerdict { row });
        }
        let measured = state.is(MeasureState::Measured);
        if !measured && *gap < 0 {
            found.push(Problem::MeasureWithoutGap { row });
        }
        if measured && *budget < 0 && *baseline < 0 && *gap != i64::from(Gap::Budgets.code()) {
            found.push(Problem::MeasureWithoutBudgetGap { row });
        }
    }
}

fn gaps(p: &Payload, found: &mut Vec<Problem>) {
    let listed: Vec<u32> = p.gaps.iter().map(|row| row.gap.value()).collect();
    if listed.windows(2).any(|pair| pair.first() >= pair.get(1)) {
        found.push(Problem::GapsNotSorted);
    }
    let named = p.measures.gap.iter().chain(&p.findings.gap);
    let listed: BTreeSet<i64> = listed.into_iter().map(i64::from).collect();
    if named
        .filter(|gap| **gap >= 0)
        .any(|gap| !listed.contains(gap))
    {
        found.push(Problem::GapNotListed);
    }
}

fn count_of<T>(values: &[T], wanted: impl Fn(&T) -> bool) -> u64 {
    u64::try_from(values.iter().filter(|value| wanted(value)).count()).unwrap_or(u64::MAX)
}

fn size(rows: usize) -> u64 {
    u64::try_from(rows).unwrap_or(u64::MAX)
}

fn findings_of(p: &Payload, kind: Option<FindingKind>, disposition: Disposition) -> u64 {
    let f = &p.findings;
    let rows = f.kind.iter().zip(&f.disposition);
    size(
        rows.filter(|(k, d)| kind.is_none_or(|kind| k.is(kind)) && d.is(disposition))
            .count(),
    )
}

/// The counts that follow from the rows. `unowned_modules` needs the owner chains of the model,
/// and `crossing_names_unbound` cannot be counted when the cap left crossings out: both keep the
/// stated value.
pub(crate) fn counted(p: &Payload) -> Counts {
    let e = &p.edges;
    let at = |level: Level| count_of(&e.level, |l| l.is(level));
    let component = |row: usize| e.level.get(row).is_some_and(|l| l.is(Level::Component));
    let sites = |row: usize| e.sites.get(row).copied().unwrap_or(0);
    let observed_target = |target: EdgeTarget| {
        size(
            (0..e.level.len())
                .filter(|row| component(*row) && sites(*row) > 0)
                .filter(|row| e.target.get(*row).is_some_and(|t| t.is(target)))
                .count(),
        )
    };
    let omitted: u64 = (0..e.level.len())
        .filter(|row| e.level.get(*row).is_some_and(|l| l.is(Level::Module)))
        .map(|row| e.omitted.get(row).copied().unwrap_or(0))
        .sum();
    let crossings = size(p.crossings.edge.len());
    let stated = p.summary.counts;
    let verdicts = |wanted: RuleVerdict| count_of(&p.rules, |rule| rule.verdict == wanted);
    Counts {
        packages: count_of(&p.nodes.level, |l| l.is(Level::Package)),
        components: count_of(&p.nodes.level, |l| l.is(Level::Component)),
        modules: count_of(&p.nodes.level, |l| l.is(Level::Module)),
        units: size(p.units.module.len()),
        module_edges: at(Level::Module),
        component_edges: at(Level::Component),
        package_edges: at(Level::Package),
        crossing_names: crossings.saturating_add(omitted),
        crossing_names_unbound: if omitted == 0 {
            count_of(&p.crossings.kind, |k| k.is(Kind::Unknown))
        } else {
            stated.crossing_names_unbound
        },
        undeclared_edges: observed_target(EdgeTarget::Undeclared),
        forbidden_edges: observed_target(EdgeTarget::Forbidden),
        unused_edges: size(
            (0..e.level.len())
                .filter(|r| component(*r) && sites(*r) == 0)
                .count(),
        ),
        cycles: findings_of(p, Some(FindingKind::Cycle), Disposition::Ranked),
        unowned_modules: stated.unowned_modules,
        findings_ranked: findings_of(p, None, Disposition::Ranked),
        findings_declared: findings_of(p, None, Disposition::Declared),
        findings_context: findings_of(p, None, Disposition::Context),
        rules_pass: verdicts(RuleVerdict::Pass),
        rules_fail: verdicts(RuleVerdict::Fail),
        rules_unknown: verdicts(RuleVerdict::Unknown),
        rules_declaration: verdicts(RuleVerdict::Declaration),
        violations: size(p.violations.kind.len()),
        unknowns: size(p.unknowns.source.len()),
        undecided: p.rules.iter().map(|rule| rule.undecided).sum(),
        gaps: size(p.gaps.len()),
    }
}

/// The counts in schema order, with their names.
fn named(c: &Counts) -> [(&'static str, u64); 25] {
    [
        ("packages", c.packages),
        ("components", c.components),
        ("modules", c.modules),
        ("units", c.units),
        ("module_edges", c.module_edges),
        ("component_edges", c.component_edges),
        ("package_edges", c.package_edges),
        ("crossing_names", c.crossing_names),
        ("crossing_names_unbound", c.crossing_names_unbound),
        ("undeclared_edges", c.undeclared_edges),
        ("forbidden_edges", c.forbidden_edges),
        ("unused_edges", c.unused_edges),
        ("cycles", c.cycles),
        ("unowned_modules", c.unowned_modules),
        ("findings_ranked", c.findings_ranked),
        ("findings_declared", c.findings_declared),
        ("findings_context", c.findings_context),
        ("rules_pass", c.rules_pass),
        ("rules_fail", c.rules_fail),
        ("rules_unknown", c.rules_unknown),
        ("rules_declaration", c.rules_declaration),
        ("violations", c.violations),
        ("unknowns", c.unknowns),
        ("undecided", c.undecided),
        ("gaps", c.gaps),
    ]
}

fn counts(p: &Payload, found: &mut Vec<Problem>) {
    let rows = counted(p);
    let rollup = findings_of(p, Some(FindingKind::Cycle), Disposition::Context);
    let not_ranked: u64 = p.run.not_ranked.iter().map(|item| item.count).sum();
    if p.summary.counts.cycles != rows.cycles || not_ranked != rollup {
        found.push(Problem::CycleCounts);
    }
    for ((name, stated), (_, counted)) in named(&p.summary.counts).into_iter().zip(named(&rows)) {
        if stated != counted && name != "cycles" {
            found.push(Problem::Count {
                name,
                stated,
                rows: counted,
            });
        }
    }
}

fn citations(p: &Payload, found: &mut Vec<Problem>) {
    let v = &p.violations;
    let mut cited: BTreeMap<&str, u64> = BTreeMap::new();
    let mut start = 0usize;
    for end in &v.rules_end {
        let end = usize::try_from(*end).unwrap_or(start);
        let ids = p.violation_rules.get(start..end).unwrap_or(&[]);
        let names: BTreeSet<&str> = ids
            .iter()
            .filter_map(|id| p.strings.get(usize::try_from(*id).ok()?))
            .map(String::as_str)
            .collect();
        for name in names {
            *cited.entry(name).or_insert(0) += 1;
        }
        start = end;
    }
    for rule in &p.rules {
        let count = cited.get(rule.id.as_str()).copied().unwrap_or(0);
        if count != rule.violations {
            found.push(Problem::RuleCitations {
                rule: rule.id.clone(),
                stated: rule.violations,
                cited: count,
            });
        }
    }
}

/// A forbidden pair names its deciding rule and an undecided pair names none. When the payload
/// carries imports, each component edge carries the permission of its pair (`no_target` without
/// a Target or without a permission row), each package edge is `no_target`, and each allowed
/// pair has a component edge (AD-361 point 6). A module edge takes the pair of the first level
/// where the owner chains differ; the payload holds no chain, so it is not checked.
fn permissions(p: &Payload, found: &mut Vec<Problem>) {
    let t = &p.permissions;
    let mut pairs = BTreeMap::new();
    for row in 0..t.component.len() {
        let cells = (
            t.component.get(row),
            t.target.get(row),
            t.status.get(row),
            t.rule.get(row),
        );
        let (Some(from), Some(to), Some(status), Some(rule)) = cells else {
            continue;
        };
        let decided = *rule >= 0;
        let broken = (status.is(Permission::Forbidden) && !decided)
            || (status.is(Permission::Undecided) && decided);
        if broken {
            found.push(Problem::PermissionRule { row });
        }
        pairs.insert((*from, *to), (row, *status));
    }
    if p.run.not_carried.iter().any(|r| r.is(Relation::Imports)) {
        return;
    }
    edge_targets(p, &pairs, found);
}

/// The target of each edge against the permission of its pair.
fn edge_targets(
    p: &Payload,
    pairs: &BTreeMap<(u32, u32), (usize, Code<Permission>)>,
    found: &mut Vec<Problem>,
) {
    let e = &p.edges;
    let mut edged = BTreeSet::new();
    let rows = e.level.iter().zip(&e.target).zip(e.from.iter().zip(&e.to));
    for (edge, ((level, target), (from, to))) in rows.enumerate() {
        let pair = pairs
            .get(&(*from, *to))
            .filter(|_| level.is(Level::Component));
        if let Some((row, _)) = pair {
            edged.insert(*row);
        }
        let wanted = match (level.known(), pair) {
            (Some(Level::Module), _) => continue,
            (Some(Level::Component), Some((_, status))) if p.run.target => match status.known() {
                Some(Permission::Allowed) => EdgeTarget::Declared,
                Some(Permission::Forbidden) => EdgeTarget::Forbidden,
                Some(Permission::Undecided) | None => EdgeTarget::Undeclared,
            },
            _ => EdgeTarget::NoTarget,
        };
        if !target.is(wanted) {
            found.push(Problem::EdgeTarget { edge });
        }
    }
    for (row, status) in pairs.values() {
        if status.is(Permission::Allowed) && !edged.contains(row) {
            found.push(Problem::AllowedWithoutEdge { row: *row });
        }
    }
}
