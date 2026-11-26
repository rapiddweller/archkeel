// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The publication route of each import that names a symbol (AD-504; `ir/reexports.py`,
//! `resolve_reexports`): the names that the symbol passes through when a module re-exports it.
//!
//! The route is the evidence that `interface_boundary` reads. It is written only when each hop is
//! proven. A route that this survey cannot prove stays empty, and the model then gives the named
//! gap "unproven publication route" and never a verdict. The forms that withhold a route:
//!
//! - a hop whose binding is not unique in its module (`stable_bindings`), a cycle, or an alias
//!   with two targets (4.0.1 `reexport_candidate`);
//! - a hop in a module whose `__all__` is not one literal list of strings (dynamic, augmented,
//!   imported or only read), because the names that the module publishes are unknown;
//! - a binding that is not the one plain statement of its module (`bound.rs`): an import in a
//!   function, a class body or a compound statement binds no module name, or another statement
//!   binds the name too;
//! - a hop in a module that another module writes to (`writes.rs`);
//! - a package name that may be the attribute or the submodule (`from pkg import name` where
//!   the package body binds `name` in any form), and a guarded import that passes a re-export.
//!
//! AD-654: a proven key of a lazy table is a hop to the attribute that it gives. Each binder of
//! the key in its module gives the same value (`lazy_agree.rs`), so the hop is certain.
//!
//! 4.0.1 follows a route past an unproven hop and judges it `UNKNOWN` only when no hop is public.
//! This survey withholds it at once, so it is never less strict.

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::envelope::FileFact;
use archkeel_facts::vocab::RouteWithheld;
use archkeel_facts::{ImportFact, Record};

use super::lazy_cover::{self, Sources};

type Aliases = HashMap<String, BTreeSet<String>>;

/// One import that re-exports a binding of its module: the aliased name, its target, and whether
/// the survey proved the pair before the walk (`reexport_candidate`, unique bindings).
struct Link {
    binding: String,
    target: String,
    proven: bool,
}

/// Why a module is opaque: its `__all__` is not read, or code outside the scan can write it.
#[derive(Default)]
pub(crate) struct SurfaceCauses {
    pub(crate) unread_all: HashSet<String>,
    pub(crate) outside: HashSet<String>,
}

impl SurfaceCauses {
    /// The causes: the modules with an unread `__all__` and those that outside code can write.
    pub(crate) fn of(unread_all: HashSet<String>, outside: HashSet<String>) -> Self {
        Self {
            unread_all,
            outside,
        }
    }
}

/// Write the route of each import that names a symbol. `opaque` holds the modules whose
/// `__all__` the survey cannot read.
pub(crate) fn resolve(
    imports: &mut [Record<ImportFact>],
    files: &[FileFact],
    (opaque, causes): (&HashSet<String>, &SurfaceCauses),
    (sole, ambiguous): (&HashSet<String>, &HashSet<String>),
    sources: &Sources,
) {
    let stable: HashMap<&str, HashSet<&str>> = files
        .iter()
        .map(|file| {
            let names = file.stable_bindings.iter().map(String::as_str).collect();
            (file.module.as_str(), names)
        })
        .collect();
    let unique = |module: &str, name: &str| stable.get(module).is_none_or(|set| set.contains(name));
    let links: Vec<Option<Link>> = imports
        .iter()
        .map(|record| link(record, &unique, sole))
        .collect();
    let mut aliases = Aliases::new();
    let mut uncertain = HashSet::new();
    for item in links.iter().flatten() {
        aliases
            .entry(item.binding.clone())
            .or_default()
            .insert(item.target.clone());
        if !item.proven {
            uncertain.insert(item.binding.clone());
        }
    }
    let mut reexports: HashMap<String, String> = HashMap::new();
    for (record, item) in imports.iter().zip(&links) {
        let data = record.data.data();
        let Some(item) = item.as_ref().filter(|item| item.proven && data.reexport) else {
            continue;
        };
        if proven_route(&item.binding, &aliases, &uncertain) {
            reexports.insert(item.binding.clone(), item.target.clone());
        } else {
            uncertain.insert(item.binding.clone());
        }
    }
    for (binding, target) in lazy_cover::links(sources) {
        uncertain.remove(&binding);
        aliases.insert(binding.clone(), BTreeSet::from([target.clone()]));
        reexports.insert(binding, target);
    }
    for record in imports.iter_mut() {
        let skipped = ambiguous.contains(record.id.as_str());
        let data = record.data.data_mut();
        let Some(symbol) = data.symbol.as_deref().filter(|symbol| *symbol != "*") else {
            continue;
        };
        let chain = route(
            &format!("{}.{symbol}", data.target_module.as_str()),
            &reexports,
        );
        // The first cause that withholds the route; the reply states it with the empty chain.
        let guarded = data.under_type_checking && chain.len() > 1;
        let cause = if skipped {
            Some((RouteWithheld::AmbiguousReexport, None))
        } else if let Some(hop) = chain.iter().find(|hop| uncertain.contains(*hop)) {
            Some((RouteWithheld::UncertainHop, Some(hop.clone())))
        } else if let Some(module) = chain
            .iter()
            .filter_map(|hop| hop.rsplit_once('.').map(|(module, _)| module))
            .find(|module| opaque.contains(*module))
        {
            let form = if causes.unread_all.contains(module) {
                RouteWithheld::UnreadAll
            } else if causes.outside.contains(module) {
                RouteWithheld::OutsideWrite
            } else {
                RouteWithheld::Escaped
            };
            Some((form, Some(module.to_owned())))
        } else {
            // A route under `TYPE_CHECKING` that passes a re-export is not proven for the model,
            // which reads the first hop of a guarded import only (the TypeScript type rule).
            guarded.then_some((RouteWithheld::TypeCheckingReexport, None))
        };
        data.reexport_chain = Some(if cause.is_some() { Vec::new() } else { chain });
        (data.route_withheld, data.route_withheld_at) = match cause {
            Some((cause, at)) => (Some(cause), at),
            None => (None, None),
        };
    }
}

/// The re-export that one import states, when it states one with a binding and a symbol.
fn link(
    record: &Record<ImportFact>,
    unique: &impl Fn(&str, &str) -> bool,
    sole: &HashSet<String>,
) -> Option<Link> {
    let data = record.data.data();
    let (symbol, binding) = (data.symbol.as_deref()?, data.binding.as_deref()?);
    let candidate = data.reexport_candidate == Some(true);
    if symbol.is_empty() || !(data.reexport || candidate) {
        return None;
    }
    let (source, target) = (data.source_module.as_str(), data.target_module.as_str());
    Some(Link {
        binding: format!("{source}.{binding}"),
        target: format!("{target}.{symbol}"),
        proven: !candidate
            && sole.contains(record.id.as_str())
            && unique(source, binding)
            && unique(target, symbol),
    })
}

/// `_reexport_route_is_proven`: each alias on the way has one target, no cycle, and is certain.
fn proven_route(binding: &str, aliases: &Aliases, uncertain: &HashSet<String>) -> bool {
    let mut visited = HashSet::new();
    let mut current = binding;
    while let Some(targets) = aliases.get(current) {
        if !visited.insert(current) || uncertain.contains(current) || targets.len() != 1 {
            return false;
        }
        match targets.iter().next() {
            Some(next) => current = next,
            None => return false,
        }
    }
    true
}

/// The hops of one route: the imported name, then each proven re-export (`_record_import_origins`).
fn route(first: &str, reexports: &HashMap<String, String>) -> Vec<String> {
    let mut chain = vec![first.to_owned()];
    let mut seen: HashSet<&str> = HashSet::from([first]);
    let mut current = first;
    while let Some(next) = reexports
        .get(current)
        .filter(|next| !seen.contains(next.as_str()))
    {
        seen.insert(next);
        chain.push(next.clone());
        current = next;
    }
    chain
}

#[cfg(test)]
#[path = "routes_tests.rs"]
mod tests;
