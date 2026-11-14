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
//! The core reads the imports and no declared facade signature, so it can prove a use and never
//! an absence of use. It counts only a use that it can prove, and it names each other case:
//!
//! - a component that receives imports and has no `public` entry: `interface.undeclared`;
//! - a `public` entry that no proven import reaches: `interface.usage_unknown`, because a facade
//!   signature may still reach it (4.0.1 then says unused, missing or nothing);
//! - a `planned` entry whose module was scanned: `interface.planned_built` when an import reaches
//!   it, else `interface.usage_unknown`; a module that was not scanned has no finding.
//!
//! For a mount, an import from outside its domain counts only when each boundary publishes it.
//! This module proves that for a mount of the root; a deeper mount counts only local imports, so
//! it can only give more `usage_unknown` rows than 4.0.1 gives diagnostics. A row holds back a PASS.

use std::collections::{HashMap, HashSet};

use archkeel_contract::policy::InsideMount;
use archkeel_contract::Component;
use archkeel_model::{publishes, Import, Model, ModelTree};

use crate::hygiene_refs::Finding;

const UNKNOWN: &str = "No proven import reaches this entry, and the core reads no declared \
                       facade signature that could reach it.";

/// The findings of the contract of `index` (the root when `None`) in the order of its components.
pub(crate) fn findings(
    tree: &ModelTree,
    mounts: &[InsideMount],
    index: Option<usize>,
) -> Vec<Finding> {
    let model = match index {
        None => tree.root(),
        Some(at) => match tree.mounts().get(at) {
            Some(model) => model,
            None => return Vec::new(),
        },
    };
    let uses = uses(tree, mounts, index, model);
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
                "interface.undeclared",
                place.clone(),
                component.label().as_text().to_owned(),
                "The component receives cross-component imports but declares no public \
                 interface."
                    .to_owned(),
            )),
            Some(entries) => {
                for (item, entry) in entries.iter().enumerate() {
                    if !used(entry.as_text(), records) {
                        let pointer = format!("{place}/public/{item}");
                        found.push(unknown(pointer, entry.as_text()));
                    }
                }
            }
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
                    "interface.planned_built",
                    pointer,
                    text.to_owned(),
                    "The planned entry's module has been scanned; it is no longer planned."
                        .to_owned(),
                )
            } else {
                unknown(pointer, text)
            });
        }
    }
    found
}

fn unknown(pointer: String, entry: &str) -> Finding {
    (
        "interface.usage_unknown",
        pointer,
        entry.to_owned(),
        UNKNOWN.to_owned(),
    )
}

/// The imports that reach each component of the model, by component label.
fn uses<'m>(
    tree: &'m ModelTree,
    mounts: &[InsideMount],
    index: Option<usize>,
    model: &'m Model,
) -> HashMap<String, Vec<&'m Import>> {
    let owner_of = |module: &str, of: &Model| -> Option<String> {
        let (id, _) = of
            .graph()
            .modules()
            .iter()
            .find(|(_, m)| m.name() == module)?;
        let owner = of.owner(id)?;
        Some(of.components().get(owner)?.label().as_text().to_owned())
    };
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
            for to in owners.into_iter().filter(|to| *to != from) {
                found.entry(to).or_default().push(import);
            }
        } else if let Some(at) = index {
            if model.selects(target) && published(tree, mounts, at, import) {
                if let Some(to) = reached(model, import, owner_of(target, model)) {
                    found.entry(to).or_default().push(import);
                }
            }
        }
    }
    found
}

/// The component of the mount that an outside import reaches through a public entry or a planned
/// entry, or `None` (`_inside_imports_by_target`, the second loop).
fn reached(model: &Model, import: &Import, target: Option<String>) -> Option<String> {
    let label = target?;
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

/// An outside import is published when the component that holds the mount publishes it at the
/// root (`_import_published_through_ancestors`, one boundary): the root owns the source, and the
/// public entries of the parent cover the imported name. A deeper mount publishes nothing here.
fn published(tree: &ModelTree, mounts: &[InsideMount], at: usize, import: &Import) -> bool {
    let Some(mount) = mounts.get(at).filter(|mount| mount.owner_id().is_empty()) else {
        return false;
    };
    let root = tree.root();
    let owned = |module: &str| -> Option<archkeel_model::ComponentId> {
        let (id, _) = root
            .graph()
            .modules()
            .iter()
            .find(|(_, m)| m.name() == module)?;
        root.owner(id)
    };
    let parent: &Component = mount.parent();
    let Some(parent_id) = root.component(parent.label().as_text()) else {
        return false;
    };
    let (source, target) = (import.source_module(), import.target_module());
    let hop = import.symbol().map(|name| vec![format!("{target}.{name}")]);
    owned(target) == Some(parent_id)
        && owned(source).is_some()
        && publishes(
            root,
            parent,
            target,
            import.symbol(),
            hop.as_deref().unwrap_or(&[]),
        )
}

/// `_entry_used`: a name of the route reaches the entry, or the import names the entry's module
/// without a symbol of its own (`module` entry) or with unread symbols.
fn used(entry: &str, records: &[&Import]) -> bool {
    let (module, colon, name) = match entry.split_once(':') {
        Some((module, name)) => (module, true, name),
        None => (entry, false, ""),
    };
    records.iter().any(|record| {
        let reaches = record.reexport_chain().iter().any(|hop| {
            if colon {
                hop.rsplit_once('.')
                    .is_some_and(|(hop_module, hop_name)| hop_module == module && hop_name == name)
            } else {
                hop.rsplit_once('.')
                    .is_some_and(|(hop_module, _)| hop_module == module)
            }
        });
        reaches || (record.target_module() == module && (!colon || !record.symbols_known()))
    })
}
