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

use archkeel_contract::{Component, Contract, Rule};

use crate::causes::{Cause, Held, Part};
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

/// The facts of one mount that the scope of its tree reads (AD-385): the clipped inside
/// contract, whether the clip cut a claim, the parent key and the names of its source domain.
pub(crate) struct MountFacts<'a> {
    pub(crate) contract: &'a Contract,
    pub(crate) outside: bool,
    pub(crate) parent_id: &'a str,
    pub(crate) domain: Vec<&'a str>,
}

/// The scope state of a contract and the reply part of its run. `mounts` holds the facts of each
/// mount of a tree, or `None` when the core reads no mount: then a root that mounts inside
/// contracts is never complete (AD-379). A reply of an external collector is a cause (AD-344).
pub(crate) fn state(
    contract: &Contract,
    graph: &Graph,
    mounts: Option<&[MountFacts<'_>]>,
) -> State {
    let mut unread: Option<Part> = None;
    let mounting = contract
        .components()
        .iter()
        .any(|item| item.inside().is_some());
    if mounting && mounts.is_none() {
        note(&mut unread, Part::MountedTree);
    }
    if let Some(incomplete) = graph.incomplete() {
        return State::Incomplete(Reason::Incomplete(incomplete));
    }
    let observed = graph.observed();
    // Slice S7 (AD-384): without mounts a pair gap is not a cause of the state; `pair_gaps.rs`
    // gives the rules that each kept gap holds. AD-385: `drop_allowed_pair_gaps` keeps every
    // pair gap of a contract with mounts (`has_insides`), and the reference engine makes each
    // rule of the tree UNKNOWN for it. So in a tree each pair gap is a cause of the one state of
    // every model: no rule reading of one mount can release a rule of any model.
    if mounts.is_some_and(|mounted| !mounted.is_empty()) {
        let gaps = observed.pair_gaps.iter();
        if let Some(held) = Held::of(gaps.map(|(a, b)| (a.as_str(), b.as_str()))) {
            return cause(Cause::PairGaps(held));
        }
    }
    if observed.git_unknown {
        return cause(Cause::WorkTree);
    }
    match observed.runtime {
        Runtime::Mismatch => return cause(Cause::Runtime),
        Runtime::Unread => note(&mut unread, Part::RuntimeRequirement),
        Runtime::Satisfied => {}
    }
    if graph.settings().producer() != crate::settings::Producer::Trusted {
        return cause(Cause::Producer);
    }
    // AD-450 review: the reference engine refuses a contract that names a module outside the
    // namespace, so no rule of such a run passes here.
    if let Some(reference) = outside_namespace(contract, graph.settings().namespace()) {
        return cause(Cause::OutsideNamespace(reference));
    }
    let all = names(graph, contract.components(), None);
    if let Some(found) = contract_failures(contract, observed, &all, &mut unread) {
        return cause(found);
    }
    // `_inside_rule_results`: the clip, the limits and the subject check of each mount are
    // coverage failures of the whole run.
    for mount in mounts.into_iter().flatten() {
        if mount.outside {
            return cause(Cause::InsideSourceDomain(mount.parent_id.to_owned()));
        }
        let scoped = names(graph, mount.contract.components(), Some(&mount.domain));
        if let Some(found) = contract_failures(mount.contract, observed, &scoped, &mut unread) {
            return cause(found);
        }
    }
    unread.map_or(State::Complete, State::Unread)
}

/// The names that the subject check of one contract reads: the source subjects (the domain of a
/// mount, or every module) and the target subjects (every module), each with the planned modules
/// of the components (`rule_subject_failures`).
fn names<'a>(
    graph: &'a Graph,
    components: &'a [Component],
    domain: Option<&[&'a str]>,
) -> Names<'a> {
    let modules = || graph.modules().iter().map(|(_, module)| module.name());
    let targets: Vec<&str> = modules().chain(subjects::planned(components)).collect();
    let subjects = match domain {
        Some(domain) => domain
            .iter()
            .copied()
            .chain(subjects::planned(components))
            .collect(),
        None => targets.clone(),
    };
    Names {
        subjects,
        targets,
        builtins: graph.builtins(),
        symbols: graph
            .constructs()
            .symbols()
            .iter()
            .filter_map(|(module, name)| {
                (in_module_domain(graph, domain, module)
                    && crate::ownership::in_scope(name, module))
                .then_some(name.as_str())
            })
            .collect(),
    }
}

fn in_module_domain(graph: &Graph, domain: Option<&[&str]>, module: &str) -> bool {
    graph.modules().iter().any(|(_, m)| m.name() == module)
        && domain.is_none_or(|d| d.contains(&module))
}

/// The profile limits and the first rule failure of one contract (`root_limits` or
/// `inside_limits`, then `rule_subject_failures`).
fn contract_failures(
    contract: &Contract,
    observed: &crate::observed::Observed,
    names: &Names<'_>,
    unread: &mut Option<Part>,
) -> Option<Cause> {
    for limit in limits::limits(contract, observed) {
        match limit {
            Limit::Certain(subject) => return Some(Cause::ProfileLimit(subject)),
            Limit::Unread(subject) => note(unread, Part::ProfileLimit(subject)),
        }
    }
    rule_failures(contract, names, unread)
}

/// The first module reference of a component outside the namespace: a package, an exact module,
/// a public, planned or `through` entry (the module part before a colon).
fn outside_namespace(contract: &Contract, namespace: &str) -> Option<String> {
    if namespace.is_empty() {
        return None;
    }
    contract
        .components()
        .iter()
        .flat_map(|component| {
            let through = component
                .requires()
                .iter()
                .flatten()
                .flat_map(|required| required.through());
            component
                .packages()
                .iter()
                .chain(component.exact_modules())
                .map(|entry| entry.as_text())
                .chain(component.public().iter().flatten().map(|e| e.as_text()))
                .chain(component.planned().iter().flatten().map(|e| e.as_text()))
                .chain(through.map(|e| e.as_text()))
                .collect::<Vec<&str>>()
        })
        .map(|entry| entry.split(':').next().unwrap_or(entry))
        .find(|module| !crate::ownership::in_scope(module, namespace))
        .map(str::to_owned)
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
fn rule_failures(
    contract: &Contract,
    names: &Names<'_>,
    unread: &mut Option<Part>,
) -> Option<Cause> {
    let components = contract.components();
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
        match subjects::check(rule, components, names) {
            Subjects::Found => {}
            Subjects::Missing => return Some(Cause::NoRuleSubjects(id.to_owned())),
            Subjects::Unread => note(unread, Part::ConstructSubjects(id.to_owned())),
        }
    }
    None
}
