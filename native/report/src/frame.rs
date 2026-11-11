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
use std::fmt;

use archkeel_model::{Decision, Unsupported, Verdict as ModelVerdict};

use crate::build_tables::{self as layout, node_of, Strings, UnknownCell, CROSSING_CAP};
use crate::check_rows::counted;
use crate::codes::{
    Code, Disposition, EdgeTarget, FindingKind, Gap, Kind, Level, Relation, UnknownSource,
    NOT_CARRIED,
};
use crate::head::{
    Counts, GapRow, NotRanked, PayloadBudget, RuleResult, RuleVerdict, Run, Source, Status, Summary,
};
use crate::input::{EdgeRow, Outcome, Produced, Records, RuleDecision, RuleOutcome, Target, Tree};
use crate::payload::{Payload, MAX_BYTES, SCHEMA_VERSION};
use crate::problem::Problem;
use crate::report::{Decided, Report};
use crate::status::Unexplained;

/// Why no `Report` can be built.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BuildError {
    /// A table that the schema requires and cannot mark as not produced has no rows yet.
    NotProduced {
        table: &'static str,
        part: Unsupported,
    },
    /// A rule decides PASS without an evaluator receipt (AD-117).
    PassWithoutReceipt { rule: String },
    /// A status other than PASS has no row that explains it (AD-361 point 5).
    Unexplained(Vec<Unexplained>),
    /// The frame breaks other rules of the check, such as the status rule.
    Invalid(Vec<Problem>),
    /// The canonical bytes are above the budget; the payload is never cut in silence.
    TooLarge { bytes: u64 },
    /// The bytes cannot be written.
    Encode(String),
}

impl fmt::Display for BuildError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            BuildError::NotProduced { table, part } => {
                write!(formatter, "the {table} table is not produced: {part}")
            }
            BuildError::PassWithoutReceipt { rule } => {
                write!(formatter, "rule {rule} decides PASS without a receipt")
            }
            BuildError::Unexplained(found) => write!(formatter, "{found:?}"),
            BuildError::Invalid(found) => write!(formatter, "{found:?}"),
            BuildError::TooLarge { bytes } => {
                write!(
                    formatter,
                    "the payload has {bytes} bytes, above {MAX_BYTES}"
                )
            }
            BuildError::Encode(error) => formatter.write_str(error),
        }
    }
}

fn rows<T>(table: &'static str, produced: Produced<T>) -> Result<T, BuildError> {
    match produced {
        Produced::Rows(rows) => Ok(rows),
        Produced::NotProduced(part) => Err(BuildError::NotProduced { table, part }),
    }
}

fn status(decision: &Decision) -> Status {
    match decision.verdict() {
        ModelVerdict::Pass(_) => Status::Pass,
        ModelVerdict::Fail => Status::Fail,
        ModelVerdict::Unknown => Status::Unknown,
    }
}

fn rule_verdict(decision: &RuleDecision) -> RuleVerdict {
    match decision {
        RuleDecision::Declaration => RuleVerdict::Declaration,
        RuleDecision::Decided(decision) => match status(decision) {
            Status::Pass => RuleVerdict::Pass,
            Status::Fail => RuleVerdict::Fail,
            Status::Unknown => RuleVerdict::Unknown,
        },
    }
}

/// The unknowns rows: each record, each diagnostic, and a missing Target.
fn unknown_cells(
    outcome: &Outcome,
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

/// The rule rows, by id; the violation count of each is the number of violation rows citing it.
fn rule_rows(
    rules: &[RuleOutcome],
    violations: &[crate::input::ViolationRow],
) -> Result<Vec<RuleResult>, BuildError> {
    let mut cited: BTreeMap<&str, u64> = BTreeMap::new();
    for row in violations {
        let names: BTreeSet<&str> = row.rules.iter().map(String::as_str).collect();
        for name in names {
            *cited.entry(name).or_insert(0) += 1;
        }
    }
    let mut out = Vec::with_capacity(rules.len());
    for rule in rules {
        let verdict = rule_verdict(&rule.decision);
        if verdict == RuleVerdict::Pass && !rule.evaluated {
            return Err(BuildError::PassWithoutReceipt {
                rule: rule.id.clone(),
            });
        }
        out.push(RuleResult {
            id: rule.id.clone(),
            kind: rule.kind.clone(),
            title: rule.title.clone(),
            verdict,
            evaluated: rule.evaluated,
            violations: cited.get(rule.id.as_str()).copied().unwrap_or(0),
            undecided: u64::try_from(rule.undecided.len()).unwrap_or(u64::MAX),
            reason: rule.reason,
            rationale: rule.rationale.clone(),
            decided_by: rule.decided_by.clone(),
        });
    }
    out.sort_by(|a, b| a.id.cmp(&b.id));
    Ok(out)
}

/// The gaps that the rows reference and the rows that each blocks. `G-CONTRACT-LINES` blocks the
/// contract link of each component edge with a target; `G-TREND` is listed while the payload
/// has fewer than two trend points.
fn gap_rows(payload: &Payload) -> Vec<GapRow> {
    let mut blocks: BTreeMap<u32, u64> = BTreeMap::new();
    for gap in payload.measures.gap.iter().chain(&payload.findings.gap) {
        if let Ok(code) = u32::try_from(*gap) {
            *blocks.entry(code).or_insert(0) += 1;
        }
    }
    let e = &payload.edges;
    let lines = e
        .level
        .iter()
        .zip(&e.target)
        .filter(|(l, t)| l.is(Level::Component) && !t.is(EdgeTarget::NoTarget));
    let lines = u64::try_from(lines.count()).unwrap_or(u64::MAX);
    *blocks
        .entry(Code::of(Gap::ContractLines).value())
        .or_insert(0) += lines;
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
        .filter(|e| e.level == Level::Module)
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

fn run_of(outcome: &Outcome, records: &Records, graph: bool) -> Run {
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
        observation: status(&outcome.observation),
        not_ranked: Vec::new(),
        not_carried,
        payload_budget: PayloadBudget {
            max_bytes: MAX_BYTES,
        },
    }
}

/// Build the `Report` frame of one run.
pub fn build(outcome: Outcome, records: Records) -> Result<Report<Decided>, BuildError> {
    let run = run_of(
        &outcome,
        &records,
        matches!(records.graph, Produced::Rows(_)),
    );
    let tree = rows("nodes", records.tree)?;
    let measures = rows("measures", records.measures)?;
    let units = rows("units", records.units)?;
    let permissions = rows("permissions", records.permissions)?;
    let violations = rows("violations", records.violations)?;
    let unknowns = rows("unknowns", records.unknowns)?;
    let findings = rows("findings", records.findings)?;
    let edges = match records.graph {
        Produced::Rows(graph) => graph.edges,
        Produced::NotProduced(_) => Vec::new(),
    };
    let rules = rule_rows(&outcome.rules, &violations)?;
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
    let mut payload = payload_of(run, rules, &body, &cells, tree.unowned_modules);
    let rollup = findings
        .iter()
        .filter(|f| f.kind == FindingKind::Cycle && f.disposition == Disposition::Context)
        .count();
    payload.run.not_ranked = vec![NotRanked {
        kind: "rollup_only_package_cycle".to_owned(),
        count: u64::try_from(rollup).unwrap_or(u64::MAX),
    }];
    payload.gaps = gap_rows(&payload);
    payload.summary = Summary {
        status: status(&outcome.status),
        counts: counted(&payload),
    };
    let decided = Decided {
        status: outcome.status,
        observation: outcome.observation,
        rules: outcome
            .rules
            .into_iter()
            .map(|r| {
                (
                    r.id,
                    match r.decision {
                        RuleDecision::Decided(d) => Some(d),
                        RuleDecision::Declaration => None,
                    },
                )
            })
            .collect(),
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
