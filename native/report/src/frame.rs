// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `build`: the `Report` frame from the outcome of the evaluator and the rows of the model.
//!
//! The builder copies the Decision and decides no verdict (AD-361 point 3). It derives only what
//! follows from the rows: the string table, the columns, the counts, the gap list, the rule
//! violation counts and the unknowns rows of the diagnostics and of a missing Target. Then it
//! runs the check of this crate, so a frame that breaks the status rule or leaves a status
//! unexplained is a named `BuildError`, never bytes.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_model::{ModelTree, RunGap, RunPass};

use crate::build_error::BuildError;
use crate::build_tables::{self as layout, node_of, Strings, UnknownCell, CROSSING_CAP};
use crate::check_rows::counted;
use crate::codes::{
    Code, Disposition, EdgeTarget, FindingKind, Gap, Kind, NodeLevel, Relation, UnknownSource,
    NOT_CARRIED,
};
use crate::frame_rules::rule_rows;
use crate::head::{
    Counts, GapRow, NotRanked, PayloadBudget, RuleResult, Run, Source, Status, Summary,
};
use crate::input::{
    EdgeRow, Produced, Records, RuleDecision, RunOutcome, Target, Tree, UnknownRecord,
};
use crate::payload::{Payload, MAX_BYTES, SCHEMA_VERSION};
use crate::problem::Problem;
use crate::report::{Decided, Report};
use crate::status::{status_of, Unexplained};

fn rows<T>(table: &'static str, produced: Produced<T>) -> Result<T, BuildError> {
    match produced {
        Produced::Rows(rows) => Ok(rows),
        Produced::NotProduced(part) => Err(BuildError::NotProduced { table, part }),
    }
}

/// The unknowns rows: each record, each diagnostic, and a missing Target.
/// The kind of an unknown row that names a PASS beyond the reference engine (AD-384 point 7).
pub(crate) const BEYOND_KIND: &str = "core_decides_beyond_the_reference";

/// One unknown row for each PASS rule of a model with kept pair gaps: the reference engine gives
/// the rule UNKNOWN for each such gap, and the core passes it because no kept gap can change what
/// it reads (AD-384). The row names the rule, so a reader sees the difference.
fn beyond(rules: &[crate::input::RuleOutcome], models: Option<&ModelTree>) -> Vec<UnknownRecord> {
    let Some(models) = models else {
        return Vec::new();
    };
    // Each PASS row reads the kept gaps of the model whose contract holds its rule (AD-385).
    rules
        .iter()
        .filter(|rule| match &rule.decision {
            RuleDecision::Decided(decision) => {
                matches!(decision.verdict(), archkeel_model::Verdict::Pass(_))
            }
            RuleDecision::Declaration => false,
        })
        .filter_map(|rule| {
            let kept = models.model_of(&rule.id)?.kept_pair_gaps();
            (kept > 0).then(|| UnknownRecord {
                kind: BEYOND_KIND.to_owned(),
                module: None,
                subjects: Vec::new(),
                rules: vec![rule.id.clone()],
                title: format!("no one of the {kept} kept pair gaps can change the rule"),
            })
        })
        .collect()
}

fn unknown_cells(
    outcome: &RunOutcome,
    records: Vec<crate::input::UnknownRecord>,
    tree: &Tree,
) -> Vec<UnknownCell> {
    let mut cells = Vec::new();
    for record in records {
        let names: Vec<&str> = record
            .module
            .iter()
            .chain(&record.subjects)
            .map(String::as_str)
            .collect();
        let node = node_of(&names, &tree.nodes);
        let mut cell = UnknownCell::new(UnknownSource::Record, &record.kind, node, &record.title);
        cell.rule = record.rules.first().cloned();
        cells.push(cell);
    }
    for d in &outcome.diagnostics {
        let node = node_of(&[d.subject.as_str()], &tree.nodes);
        cells.push(UnknownCell::new(
            UnknownSource::Diagnostic,
            &d.kind,
            node,
            &d.claim,
        ));
    }
    if outcome.target == Target::Absent {
        cells.push(UnknownCell::new(UnknownSource::Run, "no_target", 0, ""));
    }
    cells.sort_by(|a, b| {
        let key = |c: &UnknownCell| (c.source, c.node, c.reason, c.kind.clone(), c.detail.clone());
        key(a).cmp(&key(b)).then_with(|| {
            a.rule
                .as_deref()
                .unwrap_or("")
                .cmp(b.rule.as_deref().unwrap_or(""))
        })
    });
    cells
}

/// The gaps that the rows reference and the rows that each blocks. `G-CONTRACT-LINES` blocks the
/// contract link of each component edge with a target; `G-TREND` is listed while the payload
/// has fewer than two trend points.
fn gap_rows(payload: &Payload) -> Vec<GapRow> {
    let mut blocks: BTreeMap<u32, u64> = BTreeMap::new();
    for gap in payload.measures.gap.iter().chain(&payload.findings.gap) {
        if let Ok(code) = u32::try_from(*gap) {
            let count = blocks.entry(code).or_insert(0);
            *count = count.saturating_add(1);
        }
    }
    let e = &payload.edges;
    let lines = e
        .level
        .iter()
        .zip(&e.target)
        .filter(|(l, t)| l.is(NodeLevel::Component) && !t.is(EdgeTarget::NoTarget));
    let lines = u64::try_from(lines.count()).unwrap_or(u64::MAX);
    let contract_lines = blocks
        .entry(Code::of(Gap::ContractLines).value())
        .or_insert(0);
    *contract_lines = contract_lines.saturating_add(lines);
    if payload.trend.len() < 2 {
        blocks.entry(Code::of(Gap::Trend).value()).or_insert(0);
    }
    blocks
        .into_iter()
        .map(|(gap, blocks)| GapRow {
            gap: Code::raw(gap),
            blocks,
        })
        .collect()
}

fn collect_strings(records: &Body<'_>, cells: &[UnknownCell]) -> BTreeSet<String> {
    let mut found: BTreeSet<String> = BTreeSet::new();
    let mut add = |text: &str| {
        found.insert(text.to_owned());
    };
    for n in &records.tree.nodes {
        add(&n.key);
        add(&n.name);
        n.path.iter().for_each(|p| add(p));
    }
    for m in records.measures {
        m.budget_source
            .iter()
            .chain(&m.baseline_source)
            .for_each(|s| add(s));
    }
    for u in records.units {
        add(&u.name);
        add(&u.decl);
        u.variants.iter().for_each(|v| add(v));
    }
    for e in records.edges {
        e.rationale.iter().for_each(|r| add(r));
        e.crossings
            .iter()
            .take(CROSSING_CAP)
            .for_each(|c| add(&c.name));
    }
    records
        .permissions
        .iter()
        .filter_map(|p| p.rule.as_deref())
        .for_each(&mut add);
    for v in records.violations {
        add(&v.kind);
        v.rules
            .iter()
            .chain(&v.subjects)
            .chain(&v.evidence)
            .for_each(|s| add(s));
        let optional = [&v.source_module, &v.target_module, &v.symbol, &v.path];
        optional.into_iter().flatten().for_each(|s| add(s));
    }
    for c in cells {
        add(&c.kind);
        add(&c.detail);
        c.rule.iter().for_each(|r| add(r));
    }
    records
        .findings
        .iter()
        .flat_map(|f| &f.carriers)
        .for_each(|(name, _, _)| add(name));
    found
}

/// The produced rows that the payload body reads.
struct Body<'a> {
    tree: &'a Tree,
    measures: &'a [crate::input::MeasureRow],
    units: &'a [crate::input::UnitRow],
    edges: &'a [EdgeRow],
    permissions: &'a [crate::input::PermissionRow],
    violations: &'a [crate::input::ViolationRow],
    findings: &'a [crate::input::FindingRow],
}

fn payload_of(
    run: Run,
    rules: Vec<RuleResult>,
    body: &Body<'_>,
    cells: &[UnknownCell],
    unowned: u64,
) -> Payload {
    let strings = Strings::of(collect_strings(body, cells));
    let (units, variants) = layout::units(body.units, &strings);
    let (edges, via, crossings) = layout::edges(body.edges, &strings);
    let (violations, [violation_rules, violation_subjects, violation_evidence]) =
        layout::violations(body.violations, &strings);
    let (findings, carriers) = layout::findings(body.findings, &strings);
    let module_crossings = body
        .edges
        .iter()
        .filter(|e| e.level == NodeLevel::Module)
        .flat_map(|e| &e.crossings);
    let unbound = u64::try_from(module_crossings.filter(|c| c.kind == Kind::Unknown).count())
        .unwrap_or(u64::MAX);
    let summary = Summary {
        status: Status::Unknown,
        counts: Counts {
            unowned_modules: unowned,
            crossing_names_unbound: unbound,
            ..Counts::default()
        },
    };
    Payload {
        schema_version: SCHEMA_VERSION.to_owned(),
        run,
        summary,
        rules,
        gaps: Vec::new(),
        components: body.tree.components.iter().map(component).collect(),
        trend: Vec::new(),
        nodes: layout::nodes(&body.tree.nodes, &strings),
        measures: layout::measures(body.measures, &strings),
        units,
        variants,
        edges,
        via,
        crossings,
        permissions: layout::permissions(body.permissions, &strings),
        violations,
        violation_rules,
        violation_subjects,
        violation_evidence,
        unknowns: layout::unknowns(cells, &strings),
        findings,
        carriers,
        fields: None,
        params: None,
        strings: strings.into_list(),
    }
}

fn component(c: &crate::input::ComponentText) -> crate::head::Component {
    crate::head::Component {
        node: c.node,
        does: c.does.clone(),
        never: c.never.clone(),
        decided_by: c.decided_by.clone(),
        provenance: c.provenance.clone(),
        role: c.role.clone(),
        public_api: c.public_api.clone(),
    }
}

fn run_of(outcome: &RunOutcome, records: &Records, graph: bool, observation: Status) -> Run {
    let facts = &records.run;
    let mut not_carried: Vec<Relation> = NOT_CARRIED.to_vec();
    if !graph {
        not_carried.extend([Relation::Imports, Relation::Reexports]);
    }
    let mut not_carried: Vec<Code<Relation>> = not_carried.into_iter().map(Code::of).collect();
    not_carried.sort();
    let target = outcome.target == Target::Present;
    Run {
        language: facts.language.clone(),
        source: Source {
            git_head: facts.git_head.clone(),
            dirty: facts.dirty,
            scope: facts.scope.clone(),
        },
        contract: if target { facts.contract.clone() } else { None },
        coverage: facts.coverage,
        target,
        observation,
        not_ranked: Vec::new(),
        not_carried,
        payload_budget: PayloadBudget {
            max_bytes: MAX_BYTES,
        },
    }
}

/// Build the `Report` frame of one run.
///
/// The status is the status rule over the rows (`status_of`). The observation is PASS only when
/// the scope of each model of `models` is complete (`Scope::run`). A rule row is PASS only with
/// a PASS of its own rule of the model whose contract holds the rule: the root, or the mount of
/// an inside rule (AD-385). Only when the status is PASS does the builder ask the models for the
/// run proof (`ModelTree::pass_run`, one `Scope::run_complete` for each model, L-35b); without
/// it the build fails with `BuildError::PassWithoutProof`. A run without models has no PASS
/// (AD-381).
pub fn build(
    outcome: RunOutcome,
    records: Records,
    models: Option<&ModelTree>,
) -> Result<Report<Decided>, BuildError> {
    let graph = matches!(records.graph, Produced::Rows(_));
    let complete = models.is_some_and(|models| {
        models
            .models()
            .all(|model| model.scope(|scope| scope.run()).is_ok())
    });
    let observation = if complete {
        Status::Pass
    } else {
        Status::Unknown
    };
    let run = run_of(&outcome, &records, graph, observation);
    let tree = rows("nodes", records.tree)?;
    let measures = rows("measures", records.measures)?;
    let units = rows("units", records.units)?;
    let permissions = rows("permissions", records.permissions)?;
    let violations = rows("violations", records.violations)?;
    let mut unknowns = rows("unknowns", records.unknowns)?;
    unknowns.extend(beyond(&outcome.rules, models));
    let findings = rows("findings", records.findings)?;
    let edges = match records.graph {
        Produced::Rows(graph) => graph.edges,
        Produced::NotProduced(_) => Vec::new(),
    };
    let rules = rule_rows(&outcome.rules, &violations, models)?;
    let cells = unknown_cells(&outcome, unknowns, &tree);
    let body = Body {
        tree: &tree,
        measures: &measures,
        units: &units,
        edges: &edges,
        permissions: &permissions,
        violations: &violations,
        findings: &findings,
    };
    let payload = payload_of(run, rules, &body, &cells, tree.unowned_modules);
    finish(payload, &findings, outcome, models)
}

/// The derived head, the status from the rows, the PASS proof, the check and the budget.
fn finish(
    mut payload: Payload,
    findings: &[crate::input::FindingRow],
    outcome: RunOutcome,
    models: Option<&ModelTree>,
) -> Result<Report<Decided>, BuildError> {
    let rollup = findings
        .iter()
        .filter(|f| f.kind == FindingKind::Cycle && f.disposition == Disposition::Context)
        .count();
    payload.run.not_ranked = vec![NotRanked {
        kind: "rollup_only_package_cycle".to_owned(),
        count: u64::try_from(rollup).unwrap_or(u64::MAX),
    }];
    payload.gaps = gap_rows(&payload);
    payload.summary.counts = counted(&payload).0;
    let status = status_of(&payload);
    payload.summary.status = status;
    let proof = match status {
        Status::Pass => Some(run_pass(&outcome, models).map_err(BuildError::PassWithoutProof)?),
        Status::Fail | Status::Unknown => None,
    };
    let observation = payload.run.observation;
    let rules = outcome.rules.into_iter().map(|r| {
        let decision = match r.decision {
            RuleDecision::Decided(d) => Some(d),
            RuleDecision::Declaration => None,
        };
        (r.id, decision)
    });
    let decided = Decided {
        status,
        pass: proof,
        observation,
        rules: rules.collect(),
    };
    let report = Report::checked(payload, decided).map_err(refusal)?;
    let bytes = report
        .encode()
        .map_err(|error| BuildError::Encode(error.to_string()))?;
    let size = u64::try_from(bytes.len()).unwrap_or(u64::MAX);
    if size > MAX_BYTES {
        return Err(BuildError::TooLarge { bytes: size });
    }
    Ok(report)
}

/// The run proof of every model over the decided rules (L-35b, AD-385): `None` without models.
fn run_pass(outcome: &RunOutcome, models: Option<&ModelTree>) -> Result<RunPass, Option<RunGap>> {
    let decisions = outcome
        .rules
        .iter()
        .filter_map(|rule| match &rule.decision {
            RuleDecision::Decided(decision) => Some(decision),
            RuleDecision::Declaration => None,
        });
    models.ok_or(None)?.pass_run(decisions).map_err(Some)
}

fn refusal(found: Vec<Problem>) -> BuildError {
    let unexplained: Vec<Unexplained> = found
        .iter()
        .filter_map(|p| match p {
            Problem::Unexplained(u) => Some(*u),
            _ => None,
        })
        .collect();
    if unexplained.is_empty() {
        BuildError::Invalid(found)
    } else {
        BuildError::Unexplained(unexplained)
    }
}
