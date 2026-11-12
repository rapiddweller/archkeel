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
//! 2. a gap between two modules that the contract does not allow (`pair_gaps.rs`): since slice
//!    S7 it holds only the rules that it can change, so it is not part of this state;
//! 3. a work tree that the host could not read, a runtime outside its requirement, a reply of an
//!    external collector (`observation_diagnostics`, AD-344);
//! 4. the profile limits of the contract and the layer metadata of `layer_order` (`limits.rs`);
//! 5. the subject check of every rule (`subjects.rs`).
//!
//! A cause that holds in every profile is `Cause` (a fact: the reference engine gives UNKNOWN). A
//! cause that the core cannot read is `Part` (a named gap: the reference engine can give PASS).
//! A fact comes first: with one, the verdict is UNKNOWN in both engines.

use archkeel_contract::{Contract, Rule};

use crate::causes::{Cause, Part};
use crate::graph::Graph;
use crate::limits::{self, Limit};
use crate::observed::Runtime;
use crate::reason::Reason;
use crate::subjects::{self, Names, Subjects};

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

/// The scope state of a contract and the reply part of its run. `trusted` is
/// false for a reply of an external collector (AD-344).
pub(crate) fn state(contract: &Contract, graph: &Graph, trusted: bool) -> State {
    let mut unread: Option<Part> = None;
    // AD-379: a root that mounts inside contracts is never complete. The reference engine reads
    // the mounts for the root verdicts; the core decides only the root rules.
    if contract
        .components()
        .iter()
        .any(|item| item.inside().is_some())
    {
        note(&mut unread, Part::MountedTree);
    }
    if let Some(incomplete) = graph.incomplete() {
        return State::Incomplete(Reason::Incomplete(incomplete));
    }
    // Slice S7 (AD-384): a pair gap is not a cause of the state; `pair_gaps.rs` gives the rules
    // that each kept gap holds, and the run names every gap.
    let observed = graph.observed();
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
