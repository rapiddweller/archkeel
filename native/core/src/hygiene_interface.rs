// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The interface lifecycle checks of contract hygiene (AD-514; `check/validation/public_api.py`,
//! `interface_diagnostics`, and `check/validation/inside.py`, `_inside_imports_by_target`).
//!
//! Release 4.0.1 refuses a contract with an `interface_boundary` rule when a component receives
//! imports and declares no `public` entry (`interface.undeclared`), when a `public` entry is
//! reached by no import and no declared facade signature (`interface.unused`, `interface.missing`,
//! `interface.usage_unknown`), or when a built `planned` entry is reached (`interface.planned_built`).
//!
//! The core reads the imports and, since AD-580, the written types of the declared facade
//! signatures, so it can prove a use and never an absence of use. It counts only a use that it can prove, and it names each other case:
//!
//! - a component that receives imports and has no `public` entry: `interface.undeclared`;
//! - an import counts when it crosses components, or crates of one component (AD-622);
//! - a `public` entry that no proven import reaches: `interface.usage_unknown`, because a facade
//!   signature may still reach it (4.0.1 then says unused, missing or nothing);
//! - a `planned` entry whose module was scanned: `interface.planned_built` when an import reaches
//!   it, else `interface.usage_unknown`; a module that was not scanned has no finding.
//!
//! For a mount, an import from outside its domain counts only when each boundary publishes it.
//! This module walks every owner of a mount up to the root, as 4.0.1 does (AD-514, amended).
//! A row holds back a PASS.

use std::collections::{BTreeMap, HashMap, HashSet};

use archkeel_contract::policy::InsideMount;
use archkeel_contract::Component;
use archkeel_model::{
    facade_types, publishes, withheld_cause, withheld_hops, ComponentId, Import, Model, ModelTree,
};

use crate::hygiene_refs::Finding;

/// The two answers to `interface.usage_unknown` (#1963): the action word of each, and its text.
const NO_IMPORT: (&str, &str) = (
    "no_import_found",
    "No import of this module reaches the component, and the core reads no declared facade \
     signature that could reach it. Remove the entry from `public`, or name the component that \
     imports it.",
);
const ROUTE_HELD: (&str, &str) = (
    "route_held",
    "A route from an import to this entry is held, not absent: the core cannot prove it. The \
     entry may be in use, so the core does not recommend removing it",
);
const IMPORT_SEEN: (&str, &str) = (
    "import_seen",
    "An import of this module reaches the component, but the core proves no use of this entry",
);

/// A finding, and the word of the action that it asks for when its code has more than one.
pub(crate) type Row = (Finding, Option<&'static str>);

/// The findings of the contract of `index` (the root when `None`) in the order of its components.
pub(crate) fn findings(tree: &ModelTree, mounts: &[InsideMount], index: Option<usize>) -> Vec<Row> {
    let Some(model) = index.map_or(Some(tree.root()), |at| tree.mounts().get(at)) else {
        return Vec::new();
    };
    let uses = uses(tree, mounts, index, model);
    let signatures = facade_types(model);
    let scanned: HashSet<&str> = model
        .graph()
        .modules()
        .iter()
        .map(|(_, module)| module.name())
        .collect();
    let root = match index.and_then(|at| mounts.get(at)) {
        Some(mount) => format!("{}/components", mount.pointer()),
        None => "/components".to_owned(),
    };
    let mut found = Vec::new();
    for (position, component) in model.contract().components().iter().enumerate() {
        let records = uses.get(component.label().as_text());
        let records: &[&Import] = records.map_or(&[], Vec::as_slice);
        let place = format!("{root}/{position}");
        match component.public() {
            None if !records.is_empty() => found.push((
                (
                    "interface.undeclared",
                    place.clone(),
                    component.label().as_text().to_owned(),
                    "The component receives cross-component imports but declares no public \
                     interface."
                        .to_owned(),
                ),
                None,
            )),
            Some(entries) => found.extend(
                entries
                    .iter()
                    .enumerate()
                    .filter(|(_, entry)| {
                        !used(entry.as_text(), records)
                            && !signatures
                                .as_ref()
                                .is_some_and(|names| exposed(entry.as_text(), names))
                    })
                    .map(|(item, entry)| {
                        unknown(format!("{place}/public/{item}"), entry.as_text(), records)
                    }),
            ),
            None => {}
        }
        for (item, entry) in component.planned().iter().flatten().enumerate() {
            let text = entry.as_text();
            let module = text.split(':').next().unwrap_or(text);
            if !scanned.contains(module) {
                continue;
            }
            let pointer = format!("{place}/planned/{item}");
            found.push(if used(text, records) {
                (
                    (
                        "interface.planned_built",
                        pointer,
                        text.to_owned(),
                        "The planned entry's module has been scanned; it is no longer planned."
                            .to_owned(),
                    ),
                    None,
                )
            } else {
                unknown(pointer, text, records)
            });
        }
    }
    found
}

/// An entry that no proven import reaches. An import of its module that proves no use is a
/// different answer than no import at all: the first one needs a read, the second a delete. The
/// first one names why each import proves no use (#2089).
fn unknown(pointer: String, entry: &str, records: &[&Import]) -> Row {
    let module = entry.split(':').next().unwrap_or(entry);
    let touches = |hop: &String| {
        hop.rsplit_once('.')
            .is_some_and(|(found, _)| found == module)
    };
    let seen: Vec<&&Import> = records
        .iter()
        .filter(|r| r.target_module() == module || r.reexport_chain().iter().any(touches))
        .collect();
    // A route that the collector withholds (AD-1210) may pass a facade to this entry: an import
    // of the entry's name, or of a name that a re-export gives it, with a stated cause is a held
    // route, not an absent one (#2198, #2203).
    let name = entry.split_once(':').map(|(_, name)| name);
    let held: Vec<&&Import> = records
        .iter()
        .filter(|r| withheld_cause(r).is_some())
        .filter(|r| {
            name.map_or_else(
                || seen.iter().any(|s| std::ptr::eq(*s, *r)),
                |n| r.symbol() == Some(n) || withheld_hops(r).contains(&format!("{module}.{n}")),
            )
        })
        .collect();
    let (action, claim) = if !held.is_empty() {
        (ROUTE_HELD.0, import_seen(ROUTE_HELD.1, &held))
    } else if seen.is_empty() {
        (NO_IMPORT.0, NO_IMPORT.1.to_owned())
    } else {
        (IMPORT_SEEN.0, import_seen(IMPORT_SEEN.1, &seen))
    };
    (
        ("interface.usage_unknown", pointer, entry.to_owned(), claim),
        Some(action),
    )
}

/// Why an import that reaches the module of an entry proves no use of it: the word of the cause
/// that the collector states for its route (AD-1210), or the form of the import.
fn block(record: &Import) -> &'static str {
    if record.call_form() {
        "call_form"
    } else if record.unbound_type() {
        "unbound_type"
    } else if record.symbol().is_some() && record.reexport_chain().is_empty() {
        withheld_cause(record).map_or("not_stated", |(word, _)| word)
    } else {
        "other_symbol"
    }
}

/// The text of an `import_seen` hold: the number of imports for each cause, and the first import
/// with the module or hop that withheld its route.
fn import_seen(claim: &str, seen: &[&&Import]) -> String {
    let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
    for record in seen {
        *counts.entry(block(record)).or_default() += 1;
    }
    let mut causes: Vec<(&str, usize)> = counts.into_iter().collect();
    causes.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(b.0)));
    let causes: Vec<String> = causes
        .iter()
        .map(|(word, count)| format!("{count} {word}"))
        .collect();
    let first = seen
        .iter()
        .min_by_key(|r| (r.source_module(), r.symbol()))
        .map(|record| {
            let at = withheld_cause(record)
                .and_then(|(_, at)| at)
                .map(|at| format!(" ({at})"))
                .unwrap_or_default();
            format!(
                " First: {} imports {}, {}{at}.",
                record.source_module(),
                record.symbol().unwrap_or("*"),
                block(record)
            )
        })
        .unwrap_or_default();
    format!(
        "{}. Cause of each of {} imports: {}.{first}",
        claim,
        seen.len(),
        causes.join(", ")
    )
}

/// The imports that reach each component of the model, by component label.
fn uses<'m>(
    tree: &'m ModelTree,
    mounts: &[InsideMount],
    index: Option<usize>,
    model: &'m Model,
) -> HashMap<String, Vec<&'m Import>> {
    let owner_of = |module: &str, of: &Model| owner_name(of, module);
    let mut found: HashMap<String, Vec<&Import>> = HashMap::new();
    for import in model.graph().imports() {
        let (source, target) = (import.source_module(), import.target_module());
        if model.selects(source) {
            let Some(from) = owner_of(source, model) else {
                continue;
            };
            let owners: Vec<String> = match owner_of(target, model) {
                Some(to) => vec![to],
                None => {
                    let mut owners: Vec<String> = import
                        .reexport_chain()
                        .iter()
                        .filter_map(|hop| owner_of(hop.rsplit_once('.')?.0, model))
                        .collect();
                    owners.sort();
                    owners.dedup();
                    owners
                }
            };
            // AD-622: an import from another crate of the same component is a use of a public
            // entry: the library publishes it for that crate (a binary target, AD-608).
            let crossing = |to: &String| *to != from || import.other_crate();
            for to in owners.into_iter().filter(crossing) {
                found.entry(to).or_default().push(import);
            }
        } else if let Some(to) = index.and_then(|at| outside(tree, mounts, at, model, import)) {
            found.entry(to).or_default().push(import);
        }
    }
    found
}

/// The component that an import from outside the domain of the mount `at` reaches, when each
/// boundary publishes it.
fn outside(
    tree: &ModelTree,
    mounts: &[InsideMount],
    at: usize,
    model: &Model,
    import: &Import,
) -> Option<String> {
    let target = import.target_module();
    let published = model.selects(target) && published(tree, mounts, at, import);
    published
        .then(|| owner_name(model, target))
        .flatten()
        .and_then(|owner| reached(model, import, owner))
}

/// The label of the component that owns a module of the model.
fn owner_name(model: &Model, module: &str) -> Option<String> {
    let (id, _) = model
        .graph()
        .modules()
        .iter()
        .find(|(_, m)| m.name() == module)?;
    let owner = model.owner(id)?;
    Some(model.components().get(owner)?.label().as_text().to_owned())
}

/// The component of the mount that an outside import reaches through a public entry or a planned
/// entry, or `None` (`_inside_imports_by_target`, the second loop).
fn reached(model: &Model, import: &Import, label: String) -> Option<String> {
    let id = model.component(&label)?;
    let component = model.components().get(id)?;
    let owned: Vec<String> = import
        .reexport_chain()
        .iter()
        .filter(|hop| {
            hop.rsplit_once('.').is_some_and(|(module, _)| {
                model
                    .graph()
                    .modules()
                    .iter()
                    .find(|(_, m)| m.name() == module)
                    .and_then(|(module_id, _)| model.owner(module_id))
                    == Some(id)
            })
        })
        .cloned()
        .collect();
    let public = publishes(
        model,
        component,
        import.target_module(),
        import.symbol(),
        &owned,
    );
    let planned = component
        .planned()
        .iter()
        .flatten()
        .any(|entry| used(entry.as_text(), &[import]));
    (public || planned).then_some(label)
}

/// An outside import is published when every boundary that it crosses publishes it
/// (`_import_published_through_ancestors`). From the mount `at` the walk goes up one owner at a
/// time: the owner contract must own the target in the component that holds the mount, and the
/// `public` entries of that component must cover the imported name. The walk ends at the first
/// owner whose domain holds the source (both modules need an owner in its contract), or at the
/// root (the source needs an owner there). An owner mount that is not in the tree publishes
/// nothing.
fn published(tree: &ModelTree, mounts: &[InsideMount], at: usize, import: &Import) -> bool {
    let (source, target) = (import.source_module(), import.target_module());
    let hop = import.symbol().map(|name| vec![format!("{target}.{name}")]);
    let owned = |model: &Model, module: &str| -> Option<ComponentId> {
        let (id, _) = model
            .graph()
            .modules()
            .iter()
            .find(|(_, m)| m.name() == module)?;
        model.owner(id)
    };
    let mut ancestor = at;
    // The walk visits each mount at most once: the owner chain of a tree is finite.
    for _ in 0..=mounts.len() {
        let Some(mount) = mounts.get(ancestor) else {
            return false;
        };
        if ancestor != at {
            let Some(local) = tree.mounts().get(ancestor) else {
                return false;
            };
            if local.selects(source) {
                return owned(local, source).is_some() && owned(local, target).is_some();
            }
        }
        let owner = mount.owner_id();
        let upper = (!owner.is_empty()).then(|| mounts.iter().position(|m| m.parent_id() == owner));
        let model = match upper {
            None => tree.root(),
            Some(Some(index)) => match tree.mounts().get(index) {
                Some(model) => model,
                None => return false,
            },
            Some(None) => return false,
        };
        let parent: &Component = mount.parent();
        let Some(parent_id) = model.component(parent.label().as_text()) else {
            return false;
        };
        if !model.selects(target)
            || owned(model, target) != Some(parent_id)
            || !publishes(
                model,
                parent,
                target,
                import.symbol(),
                hop.as_deref().unwrap_or(&[]),
            )
        {
            return false;
        }
        match upper {
            None => return owned(model, source).is_some(),
            Some(index) => ancestor = index.unwrap_or(usize::MAX),
        }
    }
    false
}

/// A declared signature names the entry: the dotted name `module.Name` for a `module:Name` entry,
/// any name of the module for a `module` entry (`_entry_reached_by` of 4.0.1, AD-580).
fn exposed(entry: &str, names: &std::collections::HashSet<String>) -> bool {
    match entry.split_once(':') {
        Some((module, name)) => names.contains(&format!("{module}.{name}")),
        None => names.iter().any(|name| {
            name.rsplit_once('.')
                .is_some_and(|(module, _)| module == entry)
        }),
    }
}

/// `_entry_used`: a name of the route reaches the entry, or the import names the entry's module
/// without a symbol of its own (`module` entry) or with unread symbols. A call-form import proves
/// no use (AD-514).
fn used(entry: &str, records: &[&Import]) -> bool {
    let (module, colon, name) = match entry.split_once(':') {
        Some((module, name)) => (module, true, name),
        None => (entry, false, ""),
    };
    let entry = Entry {
        module,
        colon,
        name,
    };
    records
        .iter()
        .filter(|record| !record.call_form() && !record.unbound_type())
        .any(|record| entry.reached_by(record))
}

/// A `public` or `planned` entry: its module, whether it names a symbol, and the symbol.
struct Entry<'e> {
    module: &'e str,
    colon: bool,
    name: &'e str,
}

impl Entry<'_> {
    fn reached_by(&self, record: &Import) -> bool {
        let hop = |hop: &String| {
            hop.rsplit_once('.').is_some_and(|(module, name)| {
                module == self.module && (!self.colon || name == self.name)
            })
        };
        let module_import =
            record.target_module() == self.module && (!self.colon || !record.symbols_known());
        record.reexport_chain().iter().any(hop) || module_import
    }
}
