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
//! 4. the layer metadata of `layer_order` (`limits.rs`); since AD-644 a profile limit is not part
//!    of this state: `hold_rule` holds each rule that reads the limited part, and `hold_run`
//!    holds the run with the limits that no rule reads;
//! 5. the subject check of every rule (`subjects.rs`).
//!
//! A cause that holds in every profile is `Cause` (a fact: the reference engine gives UNKNOWN). A
//! cause that the core cannot read is `Part` (a named gap: the reference engine can give PASS).
//! A fact comes first. The dependency scope cause of AD-418 holds a rule when the core cannot
//! replay the former host proof; it does not claim that the former host gave UNKNOWN.

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
        if let Some(held) = Held::of(gaps.map(|(a, b, _, _, _)| (a.as_str(), b.as_str()))) {
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
    if let Some(found) = rule_failures(contract, &all, &mut unread) {
        return cause(found);
    }
    if let Some(path) = split_owner(contract.components(), observed) {
        return cause(Cause::OwnedFileOwner(path));
    }
    // `_inside_rule_results`: the clip and the subject check of each mount are coverage failures
    // of the whole run; the limits of a mount hold what reads them (AD-644).
    for mount in mounts.into_iter().flatten() {
        if mount.outside {
            return cause(Cause::InsideSourceDomain(mount.parent_id.to_owned()));
        }
        if let Some(path) = split_owner(mount.contract.components(), observed) {
            return cause(Cause::OwnedFileOwner(path));
        }
        let scoped = names(graph, mount.contract.components(), Some(&mount.domain));
        if let Some(found) = rule_failures(mount.contract, &scoped, &mut unread) {
            return cause(found);
        }
    }
    unread.map_or(State::Complete, State::Unread)
}

/// The first file without a module of its own whose path module and owner module have other
/// claiming components (AD-468). A rule reads the facts of such a file as facts of its owner, so
/// a rule of the component of its path would miss them: the scope is not complete.
fn split_owner(components: &[Component], observed: &crate::observed::Observed) -> Option<String> {
    let claimants = |module: &str| -> Vec<&str> {
        components
            .iter()
            .filter(|component| crate::ownership::claims(component, module))
            .map(|component| component.id().as_text())
            .collect()
    };
    observed
        .owned_files
        .iter()
        .find(|(_, module, owner)| claimants(module) != claimants(owner))
        .map(|(path, _, _)| path.clone())
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

/// The hold of one rule by its profile limit (AD-644, `limits::rule_limit`), then by a feature
/// that the collector states as unsupported and that the rule reads (AD-500). `Scope::complete`
/// reads it after the state of the scope.
pub(crate) fn hold_rule(
    contract: &Contract,
    graph: &Graph,
    rule: &Rule,
    unread: &mut Option<Part>,
) -> Result<(), Reason> {
    let observed = graph.observed();
    hold(limits::rule_limit(contract, rule, observed), unread)?;
    match limits::stated_hold(contract, rule, observed) {
        Some(subject) => Err(Reason::NotComplete(Cause::ProfileLimit(subject))),
        None => Ok(()),
    }
}

/// The hold of the run by the profile limits that no rule reads (AD-644, `limits::run_limits`):
/// the first part of some profiles, if no limit is a fact. `Scope::run` reads it.
pub(crate) fn hold_run(contract: &Contract, graph: &Graph) -> Result<Option<Part>, Reason> {
    let mut unread = None;
    for limit in limits::run_limits(contract, graph.observed()) {
        hold(Some(limit), &mut unread)?;
    }
    Ok(unread)
}

/// A limit of every store-accepted profile is a fact (`Cause::ProfileLimit`); a limit of some
/// profiles is a named part, and `unread` keeps the first part.
fn hold(limit: Option<Limit>, unread: &mut Option<Part>) -> Result<(), Reason> {
    match limit {
        Some(Limit::Certain(subject)) => Err(Reason::NotComplete(Cause::ProfileLimit(subject))),
        Some(Limit::Unread(subject)) => {
            unread.get_or_insert(Part::ProfileLimit(subject));
            Ok(())
        }
        None => Ok(()),
    }
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

/// The first rule failure of one contract, `rule_subject_failures` (with the layer metadata of
/// each `layer_order` rule); an unread subject count goes to `unread`. The profile limits of
/// `root_limits` and `inside_limits` hold only what reads them (AD-644, `limits::rule_limit`).
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
