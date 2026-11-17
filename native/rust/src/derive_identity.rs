// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Prove a derive identity from the file's use records and the crate's checked lock facts.
//! A local type or enum variant cannot shadow a macro. An unproved macro import still can.

use crate::attrs::{
    kinds,
    model::{Known, Proof, Usage, KNOWN},
};
use crate::crates::{Crate, Workspace};
use crate::definitions::Form;
use crate::derive_imports::Local;
use crate::modules::{Index, Outcome};
use crate::registry_overrides::Cited;
use crate::scan::{Concern, Reference, Via};
use crate::tree::Module;
use std::collections::BTreeSet;

pub(crate) fn proven(
    workspace: &Workspace,
    index: &Index<'_>,
    local: &Local<'_>,
    concern: &Concern,
    modules: &[Module],
) -> bool {
    let module = local.module;
    let (Some(proof), Some(scope), Some(krate)) = (
        &concern.proof,
        &concern.source,
        workspace.crates.get(module.crate_index),
    ) else {
        return false;
    };
    match proof {
        Proof::Attribute(usage) => prelude(
            workspace,
            index,
            local,
            scope,
            usage,
            &usage.path[0],
            modules,
        ),
        Proof::Derive(usage) => {
            prelude(workspace, index, local, scope, usage, "derive", modules)
                && (known(workspace, krate, local, scope, usage).is_some()
                    || builtin(workspace, index, local, scope, usage, modules))
        }
        Proof::Helper {
            namespace,
            candidates,
        } => candidates.iter().any(|usage| {
            prelude(workspace, index, local, scope, usage, "derive", modules)
                && (known(workspace, krate, local, scope, usage)
                    .is_some_and(|model| model.helpers.contains(&namespace.as_str()))
                    || (namespace == "default"
                        && usage.path.last().is_some_and(|name| name == "Default")
                        && builtin(workspace, index, local, scope, usage, modules)))
        }),
    }
}

pub(crate) fn binding(
    local: &Local<'_>,
    scope: &[String],
    path: &[String],
    hops: usize,
) -> Option<Vec<String>> {
    let module = local.module;
    if hops > 8 {
        return None;
    }
    let first = path.first()?;
    let count = module.scan.counts.get(first).copied().unwrap_or(0);
    if count > 1 {
        return None;
    }
    match local.binding(scope, first) {
        Some(reference) if reference.names != [first.clone()] => {
            let mut resolved = reference.names.clone();
            resolved.extend_from_slice(&path[1..]);
            if reference.absolute {
                Some(resolved)
            } else {
                binding(local, scope, &resolved, hops + 1)
            }
        }
        Some(_) => Some(path.to_vec()),
        None if count == 0 => Some(path.to_vec()),
        None => None,
    }
}

/// The modeled derive that `usage` names through a registry dependency of the crate, and its
/// package, before the lock facts prove the artifacts.
fn modeled<'k>(
    workspace: &Workspace,
    krate: &'k Crate,
    local: &Local<'_>,
    scope: &[String],
    usage: &Usage,
) -> Option<(&'k str, &'static Known)> {
    let module = local.module;
    if !usage.complete || krate.manifest.legacy() || !module.scan.extern_crates.is_empty() {
        return None;
    }
    let glob = local.globs.iter().any(|r| {
        r.scope == scope && matches!(r.via, Via::Glob { block, .. } if !block || usage.block)
    });
    if glob && !usage.absolute {
        return None;
    }
    let path = if usage.absolute {
        usage.path.clone()
    } else {
        binding(local, scope, &usage.path, 0)?
    };
    let [root, name] = path.as_slice() else {
        return None;
    };
    if !krate.registry.direct.contains(root) {
        return None;
    }
    let package = krate.manifest.dependencies.get(root)?;
    if workspace.crates.iter().any(|c| &c.ident == package) {
        return None;
    }
    let model = KNOWN
        .iter()
        .find(|m| m.package == package && m.name == name)?;
    Some((package.as_str(), model))
}

fn known(
    workspace: &Workspace,
    krate: &Crate,
    local: &Local<'_>,
    scope: &[String],
    usage: &Usage,
) -> Option<&'static Known> {
    let (package, model) = modeled(workspace, krate, local, scope, usage)?;
    let library = krate.registry.packages.get(package)?;
    let implementation = krate.registry.packages.get(model.implementation)?;
    (library.version == model.version
        && implementation.version == model.version
        && library.dependencies.contains(model.implementation))
    .then_some(model)
}

/// The package and the setting of the repository that withhold the proof of the modeled derive
/// of `concern` (AD-774): the derive would have a model, but its library or implementation crate
/// may be built from other code.
pub(crate) fn withheld<'w>(
    workspace: &'w Workspace,
    local: &Local<'_>,
    concern: &Concern,
) -> Option<(&'static str, &'w Cited)> {
    let krate = workspace.crates.get(local.module.crate_index)?;
    let scope = concern.source.as_ref()?;
    let usages: Vec<&Usage> = match concern.proof.as_ref()? {
        Proof::Derive(usage) => vec![usage],
        Proof::Helper { candidates, .. } => candidates.iter().collect(),
        Proof::Attribute(_) => Vec::new(),
    };
    usages.into_iter().find_map(|usage| {
        let (_, model) = modeled(workspace, krate, local, scope, usage)?;
        [model.package, model.implementation]
            .into_iter()
            .find_map(|name| Some((name, krate.registry.withheld.get(name)?)))
    })
}

fn builtin(
    workspace: &Workspace,
    index: &Index<'_>,
    local: &Local<'_>,
    scope: &[String],
    usage: &Usage,
    modules: &[Module],
) -> bool {
    let module = local.module;
    let Some(krate) = workspace.crates.get(module.crate_index) else {
        return false;
    };
    if "std core alloc"
        .split_whitespace()
        .any(|name| krate.manifest.dependencies.contains_key(name))
        || (usage.path.len() == 1 && !usage.prelude)
    {
        return false;
    }
    if !kinds::builtin_parts(&usage.path, &module.scan.names)
        || !module.scan.extern_crates.is_empty()
    {
        return false;
    }
    if usage.path.len() != 1 {
        return true;
    }
    prelude(
        workspace,
        index,
        local,
        scope,
        usage,
        &usage.path[0],
        modules,
    )
}

pub(crate) fn prelude(
    workspace: &Workspace,
    index: &Index<'_>,
    local: &Local<'_>,
    scope: &[String],
    usage: &Usage,
    name: &str,
    modules: &[Module],
) -> bool {
    !local.module.scan.names.contains(name)
        && namespace(workspace, index, local, scope, usage, name, modules)
}

/// No `extern crate` above the module and no glob of the scope can bind the macro `name`, so a
/// plain name of the prelude names it (AD-535). A `use` or a definition of the name is the
/// concern of the caller.
pub(crate) fn namespace(
    workspace: &Workspace,
    index: &Index<'_>,
    local: &Local<'_>,
    scope: &[String],
    usage: &Usage,
    name: &str,
    modules: &[Module],
) -> bool {
    let module = local.module;
    if !usage.prelude
        || modules.iter().any(|parent| {
            parent.crate_index == module.crate_index
                && (parent.module == module.module
                    || module
                        .module
                        .strip_prefix(&parent.module)
                        .is_some_and(|tail| tail.starts_with('.')))
                && !parent.scan.extern_crates.is_empty()
        })
    {
        return false;
    }
    local
        .globs
        .iter()
        .filter(|r| scope.starts_with(&r.scope))
        .all(|glob| {
            if matches!(glob.via, Via::Glob { block: true, .. }) && !usage.block {
                return true;
            }
            no_macro(
                workspace,
                index,
                module,
                glob,
                name,
                modules,
                &mut BTreeSet::new(),
            )
        })
}

fn no_macro(
    workspace: &Workspace,
    index: &Index<'_>,
    module: &Module,
    glob: &Reference,
    name: &str,
    modules: &[Module],
    seen: &mut BTreeSet<String>,
) -> bool {
    if let [root, prelude, ..] = glob.names.as_slice() {
        if "std core alloc".split_whitespace().any(|s| s == root)
            && prelude == "prelude"
            && !module.scan.names.contains(root)
            && workspace
                .crates
                .get(module.crate_index)
                .is_some_and(|c| !c.manifest.dependencies.contains_key(root))
        {
            return true;
        }
    }
    if glob.names.len() == 1
        && module.scan.counts.get(&glob.names[0]) == Some(&1)
        && module
            .scan
            .definitions
            .iter()
            .any(|d| d.form == Form::Enum && d.name == glob.names[0] && d.scope == glob.scope)
    {
        return true;
    }
    let Some(frame) = index.frame(&module.module) else {
        return false;
    };
    let resolved = if glob.names.len() == 1 {
        index.reach(&frame.lexical_at(&glob.scope), &glob.names)
    } else {
        index.resolve(frame, glob)
    };
    let Outcome::Edge(edge) = resolved else {
        return false;
    };
    if edge.symbol.is_some() || !seen.insert(edge.lexical.clone()) || seen.len() > 8 {
        return false;
    }
    let Some(target) = modules.iter().find(|m| m.module == edge.module) else {
        return false;
    };
    let lexical = edge
        .lexical
        .strip_prefix(&target.module)
        .unwrap_or("")
        .trim_start_matches('.');
    let scope: Vec<_> = lexical
        .split('.')
        .filter(|s| !s.is_empty())
        .map(str::to_owned)
        .collect();
    if workspace
        .crates
        .get(target.crate_index)
        .is_none_or(|c| c.manifest.proc_macro)
        || target.gated
        || !target.scan.macro_calls.is_empty()
        || target
            .scan
            .concerns
            .iter()
            .any(|c| c.source.as_ref() == Some(&scope))
    {
        return false;
    }
    if target.scan.macro_defs.iter().any(|d| d.name == name) {
        return false;
    }
    target
        .scan
        .references
        .iter()
        .filter(|r| r.scope == scope)
        .all(|reference| match &reference.via {
            Via::Use {
                binding: Some(bound),
                reexport: true,
                ..
            } => bound != name,
            Via::Glob { reexport: true, .. } => {
                no_macro(workspace, index, target, reference, name, modules, seen)
            }
            _ => true,
        })
}
