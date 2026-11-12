// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts behind the scope proof (slice S4, AD-378).
//!
//! The reference engine passes a rule only when the observation is complete
//! (`ir/coverage.py` `observation_complete`, `ir/decisions.py` `_rule_scope_complete`), the rule
//! has its receipt and the rule has no undecided position (`ir/decisions.py` `_rule_status`).
//! The observation is complete when the coverage records no failure and the run has no
//! diagnostic. The model checks each cause of a failure here, one time per model:
//!
//! 1. what the reply proves not seen (`coverage.rs`, slices S1 and S2);
//! 2. a gap between two modules that the contract does not allow (`pair_gaps.py`);
//! 3. a work tree that the host could not read, a runtime outside its requirement, a reply of an
//!    external collector (`observation_diagnostics`, AD-344);
//! 4. the profile limits of the contract and the layer metadata of `layer_order` (`limits.rs`);
//! 5. the subject check of every rule (`subjects.rs`).
//!
//! A cause that holds in every profile is `Cause` (a fact: the reference engine gives UNKNOWN). A
//! cause that the core cannot read is `Part` (a named gap: the reference engine can give PASS).
//! A fact comes first: with one, the verdict is UNKNOWN in both engines.

use std::fmt;

use archkeel_contract::{Component, Contract, Rule, RuleKind};

use crate::graph::Graph;
use crate::ids::{ComponentId, Table};
use crate::limits::{self, Limit};
use crate::observed::Runtime;
use crate::ownership::{in_scope, owner_of};
use crate::reason::{Reason, Unsupported};
use crate::subjects::{self, Names, Subjects};

/// A cause that makes the scope of a run incomplete in the reference engine for every profile.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Cause {
    /// Gaps between two modules that the contract does not allow (their number).
    PairGaps(usize),
    /// The host could not read the head or the state of the work tree.
    WorkTree,
    /// The collector runtime does not satisfy its declared requirement.
    Runtime,
    /// The reply comes from an external collector without a pinned digest (AD-344).
    Producer,
    /// A profile limit of the contract: the subject that it names.
    ProfileLimit(String),
    /// A `layer_order` rule whose components have no layer of its order: the rule id.
    LayerMetadata(String),
    /// A rule side that matches no module: the rule id.
    NoRuleSubjects(String),
    /// A dynamic import that the collector could not resolve reaches the rule.
    DynamicImport,
}

/// A part of the scope proof that the core cannot read. The rule is a named gap.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Part {
    /// A gap between two modules that the contract allows: the host drops it for one profile.
    AllowedPairGap,
    /// A runtime requirement form or state that the core does not read.
    RuntimeRequirement,
    /// A limit of some profiles only: the subject that it names.
    ProfileLimit(String),
    /// A `forbidden_construct` rule that selects no module: a symbol can be its subject.
    ConstructSubjects(String),
    /// The rule is not a rule of the contract of this model.
    ForeignRule,
}

/// The state of the scope of one model, made one time when the model is made.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(crate) enum State {
    /// No cause and no unread part.
    Complete,
    /// The first cause.
    Incomplete(Reason),
    /// The first part that the core cannot read.
    Unread(Part),
}

/// The scope state of a contract, its components and the reply part of its run. `trusted` is
/// false for a reply of an external collector (AD-344).
pub(crate) fn state(
    contract: &Contract,
    components: &Table<ComponentId, Component>,
    graph: &Graph,
    trusted: bool,
) -> State {
    let mut unread: Option<Part> = None;
    if let Some(incomplete) = graph.incomplete() {
        return State::Incomplete(Reason::Incomplete(incomplete));
    }
    let observed = graph.observed();
    let (kept, allowed) = pair_gaps(contract, components, &observed.pair_gaps);
    if kept > 0 {
        return cause(Cause::PairGaps(kept));
    }
    if allowed {
        note(&mut unread, Part::AllowedPairGap);
    }
    if observed.git_unknown {
        return cause(Cause::WorkTree);
    }
    match observed.runtime {
        Runtime::Mismatch => return cause(Cause::Runtime),
        Runtime::Unread => note(&mut unread, Part::RuntimeRequirement),
        Runtime::Satisfied => {}
    }
    if !trusted {
        return cause(Cause::Producer);
    }
    for limit in limits::limits(contract, observed) {
        match limit {
            Limit::Certain(subject) => return cause(Cause::ProfileLimit(subject)),
            Limit::Unread(subject) => note(&mut unread, Part::ProfileLimit(subject)),
        }
    }
    if let Some(found) = rule_failures(contract, graph, &mut unread) {
        return cause(found);
    }
    unread.map_or(State::Complete, State::Unread)
}

fn cause(cause: Cause) -> State {
    State::Incomplete(Reason::NotComplete(cause))
}

/// Keep the first part that the core cannot read.
fn note(unread: &mut Option<Part>, part: Part) {
    if unread.is_none() {
        *unread = Some(part);
    }
}

/// The first rule failure of `rule_subject_failures` (with the layer metadata of each
/// `layer_order` rule); an unread subject count goes to `unread`.
fn rule_failures(contract: &Contract, graph: &Graph, unread: &mut Option<Part>) -> Option<Cause> {
    let components = contract.components();
    let builtins = graph.builtins();
    let names = Names {
        subjects: graph
            .modules()
            .iter()
            .map(|(_, module)| module.name())
            .chain(subjects::planned(components))
            .collect(),
        builtins,
    };
    for rule in contract.rules() {
        let id = archkeel_contract::head_of(rule).id().as_text();
        if let Rule::LayerOrder(order) = rule {
            if !limits::layer_gaps(contract, order).is_empty() {
                return Some(Cause::LayerMetadata(id.to_owned()));
            }
        }
        if limits::undecided_kind(archkeel_contract::kind_of(rule)) {
            continue;
        }
        match subjects::check(rule, components, &names) {
            Subjects::Found => {}
            Subjects::Missing => return Some(Cause::NoRuleSubjects(id.to_owned())),
            Subjects::Unread => note(unread, Part::ConstructSubjects(id.to_owned())),
        }
    }
    None
}

/// The pair gaps that the drop rule of the host keeps for certain (their number), and whether
/// one gap is a gap that the rule can drop.
///
/// `drop_allowed_pair_gaps` keeps a gap when an end has no owner or a rule names an end; else it
/// drops a gap inside one component and a gap of a `requires` without `through`, unless a cycle
/// rule sees a cycle through it. It drops gaps only for one profile. So a gap that it keeps is a
/// fact for every profile, and a gap that it can drop is a part that the core cannot read.
fn pair_gaps(
    contract: &Contract,
    components: &Table<ComponentId, Component>,
    gaps: &[(String, String)],
) -> (usize, bool) {
    let owner = |module: &str| owner_of(components, module).and_then(|id| components.get(id));
    let mut kept = 0;
    let mut allowed = false;
    for (source, target) in gaps {
        let (Some(from), Some(to)) = (owner(source), owner(target)) else {
            kept += 1;
            continue;
        };
        if named(contract, [source, target]) || !(from.id() == to.id() || crossing(from, to)) {
            kept += 1;
        } else {
            allowed = true;
        }
    }
    (kept, allowed)
}

/// True when `from` requires `to` with an entry without `through`.
fn crossing(from: &Component, to: &Component) -> bool {
    from.requires()
        .iter()
        .flatten()
        .any(|required| required.component() == to.label() && required.through().is_empty())
}

/// `_named`: a rule names an end by a selector field, or the rule is of a kind that the drop
/// rule does not know.
fn named(contract: &Contract, ends: [&String; 2]) -> bool {
    contract.rules().iter().any(|rule| {
        let names: Vec<&str> = match rule {
            Rule::ForbiddenDependency(rule) => [rule.source(), rule.target()]
                .into_iter()
                .chain(rule.allowed_sources())
                .map(|s| s.as_text())
                .collect(),
            Rule::AllowedDependency(rule) => vec![rule.source().as_text(), rule.target().as_text()],
            Rule::SiblingIsolation(rule) => rule.members().iter().map(|s| s.as_text()).collect(),
            other => return !EDGE_FREE.contains(&archkeel_contract::kind_of(other)),
        };
        names.iter().any(|name| {
            ends.iter()
                .any(|end| in_scope(end, name) || in_scope(name, end))
        })
    })
}

/// The kinds that the drop rule of the host knows as free of edges (`_EDGE_FREE`).
const EDGE_FREE: &[RuleKind] = &[
    RuleKind::CompleteAssignment,
    RuleKind::CompleteExternalScope,
    RuleKind::CompleteRequires,
    RuleKind::ExternalDependencyScope,
    RuleKind::ForbiddenConstruct,
    RuleKind::RootLayout,
    RuleKind::NoComponentCycles,
];

impl fmt::Display for Cause {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Cause::PairGaps(count) => write!(
                formatter,
                "{count} gaps between two modules that the contract does not allow"
            ),
            Cause::WorkTree => formatter.write_str("the host could not read the work tree"),
            Cause::Runtime => {
                formatter.write_str("the collector runtime does not satisfy its requirement")
            }
            Cause::Producer => {
                formatter.write_str("the reply comes from an external collector without a pin")
            }
            Cause::ProfileLimit(subject) => {
                write!(formatter, "the profile cannot decide {subject}")
            }
            Cause::LayerMetadata(rule) => {
                write!(formatter, "a component of {rule} has no layer of its order")
            }
            Cause::NoRuleSubjects(rule) => write!(formatter, "the rule {rule} selects no module"),
            Cause::DynamicImport => {
                formatter.write_str("an unresolved dynamic import reaches the rule")
            }
        }
    }
}

impl fmt::Display for Part {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Part::AllowedPairGap => formatter.write_str(
                "a gap between two modules that the contract allows; the host drops it for one \
                 profile, the core does not know the profile",
            ),
            Part::RuntimeRequirement => {
                formatter.write_str("a runtime requirement that the core does not read")
            }
            Part::ProfileLimit(subject) => write!(
                formatter,
                "{subject} is a limit of some profiles; the core does not know the profile"
            ),
            Part::ConstructSubjects(rule) => write!(
                formatter,
                "{rule} selects no module; the core does not read the symbols of its source"
            ),
            Part::ForeignRule => formatter.write_str("the rule is not a rule of this model"),
        }
    }
}

impl From<Part> for Reason {
    fn from(part: Part) -> Reason {
        Reason::Unsupported(Unsupported::ScopeProof(part))
    }
}
