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
//!   imported or only read), because the names that the module publishes are unknown.
//!
//! 4.0.1 follows a route past an unproven hop and judges it `UNKNOWN` only when no hop is public.
//! This survey withholds it at once, so it is never less strict.

use std::collections::{BTreeSet, HashMap, HashSet};

use archkeel_facts::envelope::FileFact;
use archkeel_facts::{ImportFact, Record};

type Aliases = HashMap<String, BTreeSet<String>>;

/// One import that re-exports a binding of its module: the aliased name, its target, and whether
/// the survey proved the pair before the walk (`reexport_candidate`, unique bindings).
struct Link {
    binding: String,
    target: String,
    proven: bool,
}

/// Write the route of each import that names a symbol. `opaque` holds the modules whose
/// `__all__` the survey cannot read.
pub(crate) fn resolve(
    imports: &mut [Record<ImportFact>],
    files: &[FileFact],
    opaque: &HashSet<String>,
) {
    let stable: HashMap<&str, HashSet<&str>> = files
        .iter()
        .map(|file| {
            let names = file.stable_bindings.iter().map(String::as_str).collect();
            (file.module.as_str(), names)
        })
        .collect();
    let unique = |module: &str, name: &str| stable.get(module).is_none_or(|set| set.contains(name));
    let links: Vec<Option<Link>> = imports.iter().map(|record| link(record, &unique)).collect();
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
    for record in imports.iter_mut() {
        let data = record.data.data_mut();
        let Some(symbol) = data.symbol.as_deref().filter(|symbol| *symbol != "*") else {
            continue;
        };
        let chain = route(
            &format!("{}.{symbol}", data.target_module.as_str()),
            &reexports,
        );
        let withheld = chain.iter().any(|hop| {
            uncertain.contains(hop)
                || hop
                    .rsplit_once('.')
                    .is_some_and(|(module, _)| opaque.contains(module))
        });
        data.reexport_chain = Some(if withheld { Vec::new() } else { chain });
    }
}

/// The re-export that one import states, when it states one with a binding and a symbol.
fn link(record: &Record<ImportFact>, unique: &impl Fn(&str, &str) -> bool) -> Option<Link> {
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
        proven: !candidate && unique(source, binding) && unique(target, symbol),
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
