// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The import matchers of the direction rule kinds (slice S5, AD-380).
//!
//! Each matcher judges the resolved imports of the reply for one rule. The evaluator writes a
//! violation for each `Judged::Fail`; the scope proof counts each `Judged::Undecided` as an
//! undecided position. One matcher serves both, as `_forbidden_dependency_verdicts` and
//! `_requires_import_verdicts` serve the violations and `symbol_limits` in the reference engine.
//!
//! Reference engine: `check/evaluation/rule_support.py:98` `_forbidden_dependency_verdicts`,
//! `ir/dependency.py:111` `DependencySelector.select`, `check/evaluation/rules.py:1387`
//! `_sibling_violations`, `rules.py:1827` `_requires_import_verdicts` and `ir/model.py:318`
//! `requires_covers`, `:340` `_required_port_assessment`, `:356` `requires_import_assessment`.

use std::collections::{BTreeMap, HashMap};

use archkeel_contract::{
    CompleteRequires, Component, ExternalDependencyScope, ForbiddenDependency, SiblingIsolation,
};
use archkeel_facts::envelope::LimitSupport;

use crate::causes::Cause;
use crate::ids::ComponentId;
use crate::imports::{Import, Resolved};
use crate::model::Model;
use crate::ownership::{in_scope, owner_of, symbol_port_above};
use crate::reason::Reason;
use crate::selection::{
    dependency_sides, unused_by_module, unused_entries, Selection, UnusedAllowance,
};

/// The judgement of one import that a rule names.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Judged {
    /// The rule rejects the import.
    Fail,
    /// The rule accepts the import.
    Pass,
    /// The reply does not prove which names the import uses: an undecided position.
    Undecided,
}

/// The imports that a `forbidden_dependency` rule names before its `allowed_sources` apply. A mount
/// judges only the imports whose source lies in its domain (AD-385).
fn named_imports<'m>(
    model: &'m Model,
    rule: &'m ForbiddenDependency,
) -> impl Iterator<Item = &'m Import> {
    let [sources, targets] = dependency_sides(rule, model.contract().components());
    model
        .graph()
        .imports_for_symbol_rule(*rule.source_symbol_only())
        .filter(move |import| {
            model.selects(import.source_module())
                && sources.matches(import.source_module())
                && targets.matches(import.target_module())
                && !(import.under_type_checking() && !rule.include_type_checking())
        })
}

/// The judgement of each import that a `forbidden_dependency` rule names, in reply order.
pub fn forbidden<'m>(model: &'m Model, rule: &'m ForbiddenDependency) -> Vec<(&'m Import, Judged)> {
    let allowed = |module: &str| rule.allowed_sources().iter().any(|a| a.as_text() == module);
    named_imports(model, rule)
        .filter(|import| !allowed(import.source_module()))
        .map(|import| {
            // AD-434: named type publication does not lift dependency symbol limits.
            let judged = match rule.target_symbol() {
                None => Judged::Fail,
                Some(symbol) => match names_symbol(import, symbol, model.graph().renamed(symbol)) {
                    Some(true) => Judged::Fail,
                    None => Judged::Undecided,
                    Some(false)
                        if import.symbols_known()
                            && (!import.under_type_checking() || import.symbol().is_none()) =>
                    {
                        Judged::Pass
                    }
                    Some(false) => Judged::Undecided,
                },
            };
            (import, judged)
        })
        .collect()
}

/// The imports of the selected modules that name `dependency`: an external import by its package
/// name, any other import by the scope of its target module.
fn named_by<'m>(model: &'m Model, dependency: &'m str) -> impl Iterator<Item = &'m Import> {
    let names = move |import: &Import| match import.resolved() {
        Resolved::External(package) => package == dependency,
        Resolved::Local | Resolved::Builtin => in_scope(import.target_module(), dependency),
    };
    let imports = model.graph().imports().iter();
    imports.filter(move |import| model.selects(import.source_module()) && names(import))
}

/// True when an import that the scan cannot resolve can come from a module below `scope`. The
/// import can be the subject that an exception entry names, so the entry is not reported.
fn unresolved(model: &Model, scope: &str) -> bool {
    let limits = &model.graph().observed().dynamic_imports;
    let below = |module: &str| in_scope(module, scope);
    limits
        .iter()
        .any(|limit| limit.source.as_deref().is_none_or(below))
}

/// The `allowed_sources` entries of a `forbidden_dependency` rule that name no import (AD-1070).
pub(crate) fn unused_dependency_allowances(
    model: &Model,
    rule: &ForbiddenDependency,
) -> Vec<UnusedAllowance> {
    let imports: Vec<_> = named_imports(model, rule).collect();
    // An indirect rule judges a chain start too, and `allowed_sources` exempts it (AD-1085).
    let mut starts = Vec::new();
    if *rule.indirect() {
        let [sources, targets] = dependency_sides(rule, model.contract().components());
        starts = chain_starts(&sources, &fewest_imports(&hop_table(model, rule), &targets));
    }
    let used = |entry: &str| {
        unresolved(model, entry)
            || imports.iter().any(|i| i.source_module() == entry)
            || starts.iter().any(|(start, _)| *start == entry)
    };
    unused_entries("allowed_sources", rule.allowed_sources(), used)
}

/// The exception entries of an `external_dependency_scope` rule that name no module (AD-1070).
pub(crate) fn unused_scope_allowances(
    model: &Model,
    rule: &ExternalDependencyScope,
) -> Vec<UnusedAllowance> {
    let dependency = rule.dependency().as_text();
    let modules: Vec<&str> = named_by(model, dependency)
        .map(Import::source_module)
        .collect();
    let (allowed, exact) = (rule.allowed_sources(), rule.exact_sources());
    unused_by_module(allowed, exact, &modules, |entry| unresolved(model, entry))
}

/// The first import of each pair of modules, by id: the hops that a chain can use.
type Hops<'m> = BTreeMap<&'m str, BTreeMap<&'m str, &'m Import>>;

/// The shortest chain of imports from each source module that reaches the target side only through
/// other modules, for an `indirect` rule. A source module with a direct import of the target has its
/// direct judgement and no chain. The next hop is the smallest module name on a shortest path, and
/// the import of a hop is the one with the smallest id, so one run gives one chain (AD-1085).
/// `allowed_sources` exempts only the first module of a chain.
pub fn forbidden_chains<'m>(
    model: &'m Model,
    rule: &'m ForbiddenDependency,
) -> Vec<Vec<&'m Import>> {
    let [sources, targets] = dependency_sides(rule, model.contract().components());
    let next = hop_table(model, rule);
    let fewest = fewest_imports(&next, &targets);
    let allowed = |module: &str| rule.allowed_sources().iter().any(|a| a.as_text() == module);
    let mut starts = chain_starts(&sources, &fewest);
    starts.retain(|(start, _)| !allowed(start));
    starts.sort_unstable();
    starts
        .into_iter()
        .map(|(start, length)| chain_from(start, length, &next, &fewest, &targets))
        .collect()
}

/// The modules of the source side that reach the target side only through other modules.
fn chain_starts<'m>(
    sources: &Selection<'_>,
    fewest: &HashMap<&'m str, usize>,
) -> Vec<(&'m str, usize)> {
    let starts = HashMap::iter(fewest).filter(|(m, n)| **n >= 2 && sources.matches(m));
    starts.map(|(module, length)| (*module, *length)).collect()
}

/// The imports that a chain can use: a module of the model, no self import, and `TYPE_CHECKING`
/// only when the rule counts it.
fn hop_table<'m>(model: &'m Model, rule: &ForbiddenDependency) -> Hops<'m> {
    let mut next: Hops<'m> = BTreeMap::new();
    for import in model.graph().imports() {
        let (from, to) = (Import::source_module(import), Import::target_module(import));
        let hidden = import.under_type_checking() && !rule.include_type_checking();
        if !model.selects(from) || from == to || hidden {
            continue;
        }
        let by_target = BTreeMap::entry(&mut next, from).or_default();
        let hop = BTreeMap::entry(by_target, to).or_insert(import);
        if Import::id(import) < Import::id(hop) {
            *hop = import;
        }
    }
    next
}

/// For each module, the fewest imports to a module of the target side (a breadth-first walk
/// against the direction of the imports). A module of the target side can have a count too.
fn fewest_imports<'m>(next: &Hops<'m>, target: &Selection<'_>) -> HashMap<&'m str, usize> {
    let mut preceding: BTreeMap<&str, Vec<&str>> = BTreeMap::new();
    for (from, hops) in next {
        for to in hops.keys() {
            Vec::push(BTreeMap::entry(&mut preceding, to).or_default(), from);
        }
    }
    let mut fewest: HashMap<&str, usize> = HashMap::new();
    let mut level: Vec<&str> = BTreeMap::iter(next)
        .filter(|(_, hops)| hops.keys().any(|to| target.matches(to)))
        .map(|(from, _)| *from)
        .collect();
    for count in 1.. {
        if level.is_empty() {
            break;
        }
        let mut upstream = Vec::new();
        for module in level {
            if fewest.insert(module, count).is_none() {
                upstream.extend(
                    BTreeMap::get(&preceding, module)
                        .into_iter()
                        .flatten()
                        .copied(),
                );
            }
        }
        level = upstream
            .into_iter()
            .filter(|module| !fewest.contains_key(module))
            .collect();
    }
    fewest
}

/// The chain of `length` imports from `start`: at each module, the smallest name that is one
/// import closer to the target side.
fn chain_from<'m>(
    start: &'m str,
    length: usize,
    next: &Hops<'m>,
    fewest: &HashMap<&'m str, usize>,
    target: &Selection<'_>,
) -> Vec<&'m Import> {
    let (mut chain, mut at) = (Vec::new(), start);
    for left in (1..=length).rev() {
        let closer = |to: &str| {
            if left == 1 {
                target.matches(to)
            } else {
                HashMap::get(fewest, to) == Some(&(left - 1))
            }
        };
        let step = BTreeMap::get(next, at)
            .into_iter()
            .flatten()
            .find(|(to, _)| closer(to));
        let Some((to, import)) = step else { break };
        Vec::push(&mut chain, *import);
        at = to;
    }
    chain
}

/// A chain can run through a module outside the domain of a mount, and the mount reads none of
/// its edges or gaps, so an `indirect` rule of a mount has no PASS (AD-1085).
pub(crate) fn chains_readable(model: &Model, rule: &ForbiddenDependency) -> Result<(), Reason> {
    if *rule.indirect() && model.is_mount() {
        return Err(Reason::NotComplete(Cause::Receipt(
            "an indirect rule reads no module outside the domain of a mounted contract",
        )));
    }
    Ok(())
}

/// A PASS needs an import that names `dependency`, else a typo in the name looks like a clean
/// project (AD-1048). The scan gives the import root, not the distribution name.
pub(crate) fn dependency_named(model: &Model, dependency: &str) -> Result<(), Reason> {
    if named_by(model, dependency).next().is_some() {
        Ok(())
    } else {
        Err(Reason::NotComplete(Cause::Receipt(
            "the named package matches no import",
        )))
    }
}

/// A PASS of a `target_symbol` rule needs a proof that the symbol exists in the target: an import
/// of the target that may name it, or a module-level declaration of it in the target. Else the
/// symbol can be a typo, and no import of it can break the rule (AD-1048).
pub(crate) fn symbol_named(model: &Model, rule: &ForbiddenDependency) -> Result<(), Reason> {
    let Some(symbol) = rule.target_symbol() else {
        return Ok(());
    };
    let [_, targets] = dependency_sides(rule, model.contract().components());
    let renamed = model.graph().renamed(symbol);
    let imported = model.graph().imports().iter().any(|import| {
        targets.matches(import.target_module())
            && names_symbol(import, symbol, renamed) != Some(false)
    });
    if imported
        || model
            .graph()
            .declared(|module| targets.matches(module), symbol)
    {
        Ok(())
    } else {
        Err(Reason::NotComplete(Cause::Receipt(
            "the target symbol is named by no import and declared in no target module",
        )))
    }
}

/// Whether an import names the item `symbol` (AD-668): by its own name, or by a re-export whose
/// route passes that name (`pub use vocab::Profile as Lang`). `None` when the import may name it
/// and the facts do not tell: a glob (`*`) takes names that the scan does not list, and a route
/// that the collector does not prove to its end may reach a later hop of that name. Such a hop
/// needs a record that binds `symbol` under another name (`renamed`), so without one the name of
/// the import is the name of its item.
fn names_symbol(import: &Import, symbol: &str, renamed: bool) -> Option<bool> {
    let hop_named = |hop: &String| hop.rsplit_once('.').is_some_and(|(_, name)| name == symbol);
    match import.symbol() {
        Some(name) if name == symbol => Some(true),
        _ if import.reexport_chain().iter().any(hop_named) => Some(true),
        Some("*") => None,
        Some(_) if renamed && !import.route_complete() => None,
        _ => Some(false),
    }
}

/// Each import from one member of a `sibling_isolation` rule to another member, with the member
/// of its source. The rule rejects each of them.
pub fn peers<'m>(model: &'m Model, rule: &'m SiblingIsolation) -> Vec<(&'m Import, &'m str)> {
    let member = |module: &str| {
        rule.members()
            .iter()
            .map(|m| m.as_text())
            .find(|m| in_scope(module, m))
    };
    model
        .graph()
        .imports()
        .iter()
        .filter(|import| model.selects(import.source_module()))
        .filter_map(|import| {
            let source = member(import.source_module())?;
            let target = member(import.target_module())?;
            let hidden = import.under_type_checking() && !rule.include_type_checking();
            (source != target && !hidden).then_some((import, source))
        })
        .collect()
}

/// One import between two components that a `complete_requires` rule judges.
#[derive(Clone, Copy, Debug)]
pub struct Crossing<'m> {
    /// The import that crosses.
    pub import: &'m Import,
    /// The component of the importing module.
    pub source: &'m Component,
    /// The component of the imported module.
    pub target: &'m Component,
    /// How the rule judged the crossing.
    pub judged: Judged,
}

/// The judgement of each import between two owned components, in reply order.
///
/// Without the symbol feature a profile does not judge an import whose target has a `through`
/// entry with a symbol (`dependency_symbols` is false): the import is left out, and the profile
/// limit of the scope proof (`limits.rs`) names such an entry. Without a statement of the
/// collector it holds the whole run; with a stated `Unsupported` it holds each `complete_requires`
/// rule (AD-500).
pub fn crossings<'m>(model: &'m Model, rule: &CompleteRequires) -> Vec<Crossing<'m>> {
    let components = model.components();
    // `dependency_symbols`: a profile judges symbol ports only with the symbol feature
    // (`check/evaluation/evaluate.py:1061`).
    let observed = model.graph().observed();
    let symbols = observed.symbol_feature
        || observed
            .profile_limits
            .is_some_and(|limits| limits.dependency_symbols == LimitSupport::Supported);
    let mut owners: HashMap<&str, Option<ComponentId>> = HashMap::new();
    let mut owner = |module: &'m str| {
        *owners
            .entry(module)
            .or_insert_with(|| owner_of(components, module))
    };
    let mut found = Vec::new();
    // A mount judges only the imports of its domain (`source_modules`, AD-385).
    let imports = model.graph().imports().iter();
    for import in imports.filter(|import| model.selects(import.source_module())) {
        let (Some(from), Some(to)) = (owner(import.source_module()), owner(import.target_module()))
        else {
            continue;
        };
        if from == to || (import.under_type_checking() && !rule.include_type_checking()) {
            continue;
        }
        let (Some(source), Some(target)) = (components.get(from), components.get(to)) else {
            continue;
        };
        if !symbols && symbol_port(source, target) {
            continue;
        }
        let named = import.symbols_known()
            && (!import.under_type_checking() || import.symbol().is_none())
            && import.symbol() != Some("*");
        let (module, symbol) = (import.target_module(), import.symbol());
        let mut judged = assessment(source, target, module, symbol, named);
        // The compiler names the module of the impl, not the symbol of a port (AD-1136).
        if judged == Judged::Fail && import.selected_impl() && symbol_port_above(source, module) {
            judged = Judged::Undecided;
        }
        found.push(Crossing {
            import,
            source,
            target,
            judged,
        });
    }
    found
}

/// True when a `requires` entry of `source` for `target` has a symbol port.
fn symbol_port(source: &Component, target: &Component) -> bool {
    source.requires().iter().flatten().any(|entry| {
        entry.component() == target.label()
            && entry
                .through()
                .iter()
                .any(|port| port.as_text().contains(':'))
    })
}

/// Assess a known import or a possible edge without a proven symbol.
pub(crate) fn assessment(
    source: &Component,
    target: &Component,
    module: &str,
    symbol: Option<&str>,
    named: bool,
) -> Judged {
    let entries = || {
        source
            .requires()
            .iter()
            .flatten()
            .filter(|entry| entry.component() == target.label())
    };
    let covered = entries().any(|entry| {
        entry.through().is_empty()
            || entry.through().iter().any(|port| {
                port_judged(
                    port.as_text(),
                    module,
                    if named { symbol } else { None },
                    true,
                ) == Judged::Pass
            })
    });
    if covered {
        return Judged::Pass;
    }
    let undecided = !named
        && entries().any(|entry| {
            entry
                .through()
                .iter()
                .any(|port| port_judged(port.as_text(), module, symbol, false) == Judged::Undecided)
        });
    if undecided {
        Judged::Undecided
    } else {
        Judged::Fail
    }
}

/// `_required_port_assessment`: a module prefix, or an exact `module:symbol` port.
fn port_judged(port: &str, module: &str, symbol: Option<&str>, known: bool) -> Judged {
    let Some((port_module, port_symbol)) = port.split_once(':') else {
        return if in_scope(module, port) {
            Judged::Pass
        } else {
            Judged::Fail
        };
    };
    if module != port_module {
        Judged::Fail
    } else if !known {
        Judged::Undecided
    } else if symbol == Some(port_symbol) {
        Judged::Pass
    } else {
        Judged::Fail
    }
}

/// The number of undecided positions in judgements (`symbol_limits`).
pub(crate) fn undecided(judged: impl Iterator<Item = Judged>) -> usize {
    judged.filter(|judged| *judged == Judged::Undecided).count()
}
