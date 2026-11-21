// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A trait impl in a third module (#1004, AD-516). An impl of a trait for a type runs wherever
//! the types fit, and no `use` brings it in: `y.into()`, `?`, `a + b`, `x.to_string()`, `for i in
//! x`, `==`, `Drop`, and `fn f<T: Tr>(t: T)` all run an `impl` that the caller never names. The
//! scan reads no types, so it cannot tell which caller runs which impl.
//!
//! An orphan-module impl is a trait impl in a module that defines neither its trait nor its self
//! type. Every module that may reach it gets a pair gap to the module of the impl: the modules of
//! its crate, and of each crate that depends on that crate. A trait or a type that the scan cannot
//! resolve to a definition counts as not defined here, so the impl is an orphan. The host drops a
//! pair gap when the contract lets the caller use the module (AD-357).
//!
//! An anchored impl runs in code that never names its module either (#1515, #1516, AD-806): a
//! method call on a value that another module gives, an operator, `?`, `for`, a format macro, a
//! drop, a `dyn` value, a generic function of another module with a bound on its trait, a
//! supertrait or a re-export. A caller can hold such a value or reach such a function only over a
//! chain of dependencies that ends in the module of the impl. So each module that reaches it over
//! the edges and the pair gaps gets the pair gap (`impl_flow::settle`), when the module holds a
//! trait impl that runs code: a block with an item other than an associated type, or a derive
//! other than `Copy`.

use std::collections::HashSet;

use crate::attrs::model::Proof;
use crate::builder::Builder;
use crate::crates::Workspace;
use crate::definitions::{Form, Owner, TraitImpl};
use crate::impl_globs::{depends, once_gap};
use crate::modules::{Index, TypeOf};
use crate::site::Site;
use crate::tree::Module;

use super::flow::{LazyHome, LazyHomes};

/// What the blocks around an impl say of its self type: `Some(anchored)` when they decide it,
/// `None` when no block item or `use` can bind its first name and the module decides.
fn in_blocks(home: &Module, found: &TraitImpl, path: &[String]) -> Option<bool> {
    if found.blocks.is_empty() {
        return None;
    }
    if !found.scope.is_empty() {
        return Some(false);
    }
    let around =
        (home.scan.orphans.block_items.iter()).filter(|item| found.blocks.contains(&item.end));
    let around: Vec<_> = around.collect();
    if around.iter().any(|item| item.name.is_none()) {
        return Some(false);
    }
    let mut named = around
        .iter()
        .filter(|item| item.name.as_ref() == path.first());
    match (named.next(), named.next(), path.len()) {
        (None, _, _) => None,
        (Some(item), None, 1) => Some(item.nominal),
        _ => Some(false),
    }
}

/// The lexical module and the form of the item that a path names, when the file `home` defines it
/// (a struct, enum or union as `Form::Struct` or `Form::Enum`, or a trait).
fn defined(index: &Index<'_>, home: &Module, found: &TraitImpl, path: &[String]) -> Option<Form> {
    let frame = index.frame(&home.module)?;
    let TypeOf::Known(lexical, name) = index.local_type_of(frame, &found.scope, path) else {
        return None;
    };
    if index.file_of(&lexical) != Some(home.module.as_str()) {
        return None;
    }
    let named = home.scan.definitions.iter();
    let mut named = named.filter(|d| d.name == name && d.owner == Owner::Module);
    named.find_map(|d| matches!(d.form, Form::Struct | Form::Enum | Form::Trait).then_some(d.form))
}

/// Whether the file `home` defines the outermost nominal type of the self type of the impl, or the
/// trait of the impl. A trait argument never anchors; a trait in a block never anchors.
fn anchored(index: &Index<'_>, home: &Module, found: &TraitImpl) -> bool {
    let by_type = found.self_path.as_ref().map(|path| {
        in_blocks(home, found, path)
            .unwrap_or_else(|| defined(index, home, found, path).is_some_and(|f| f != Form::Trait))
    });
    let by_trait = (found.blocks.is_empty())
        .then_some(found.trait_path.as_ref())
        .flatten()
        .is_some_and(|path| defined(index, home, found, path) == Some(Form::Trait));
    by_type == Some(true) || by_trait
}

/// Whether the impl is an orphan of the module `home`.
fn orphan(index: &Index<'_>, home: &Module, found: &TraitImpl) -> bool {
    !anchored(index, home, found)
}

/// The modules that may run an impl of `home`: its crate and each crate that depends on it.
fn callers<'a>(
    workspace: &'a Workspace,
    modules: &'a [Module],
    home: &'a Module,
) -> impl Iterator<Item = &'a Module> {
    let reach = move |caller: &&Module| {
        caller.crate_index == home.crate_index || depends(workspace, caller, home)
    };
    modules.iter().filter(reach)
}

/// A pair gap from each module that may reach an orphan-module impl to the module of the impl.
pub(super) fn orphan_impl_gaps(
    builder: &mut Builder,
    (workspace, index, modules): (&Workspace, &Index<'_>, &[Module]),
    edges: &HashSet<(u32, u32)>,
) {
    // #1371: a macro call may write an impl that the scan does not read.
    let homes = builder.macro_impl_homes.clone();
    for home in modules {
        let Some((rel, site)) = homes.get(&home.module) else {
            continue;
        };
        let target = home.module.as_str();
        let why = format!(
            "A macro call in {target} may write a trait impl or a method that the scan does not read: code of the caller may run it"
        );
        for caller in callers(workspace, modules, home) {
            once_gap(
                builder,
                edges,
                (caller.module.as_str(), target),
                (rel, site),
                &why,
                None,
                false,
            );
        }
    }
    for home in modules {
        let target = home.module.as_str();
        let why = format!(
            "A trait impl in {target} defines neither its trait nor its type: code of the caller may run it"
        );
        let mut impls = home.scan.orphans.impls.iter();
        let Some(found) = impls.find(|found| orphan(index, home, found)) else {
            continue;
        };
        for caller in callers(workspace, modules, home) {
            let pair = (caller.module.as_str(), target);
            once_gap(
                builder,
                edges,
                pair,
                (&home.rel, &found.site),
                &why,
                None,
                false,
            );
        }
    }
}

/// One module whose trait impl or destructor runs code, evaluated lazily in settlement (#1942).
/// Precompute trait and `Drop` homes plus crate dependencies without `homes x callers` expansion.
pub(super) fn lazy_homes(
    builder: &mut Builder,
    workspace: &Workspace,
    modules: &[Module],
) -> LazyHomes {
    LazyHomes {
        trait_homes: trait_impl_homes(builder, modules),
        drop_homes: drop_impl_homes(builder, modules),
        crate_deps: crate_dependency_matrix(workspace, modules),
    }
}

/// The modules that hold a trait impl that runs code, without materializing `homes x callers`.
fn trait_impl_homes(builder: &mut Builder, modules: &[Module]) -> Vec<LazyHome> {
    modules
        .iter()
        .filter_map(|module| {
            let site = runs_code(module)?;
            let target = &module.module;
            Some(LazyHome {
                target: builder.intern_text(target),
                crate_index: module.crate_index,
                rel: module.rel.clone(),
                site: site.clone(),
                reason: format!(
                    "A trait impl in {target} may run in code that reaches {target} without naming it: a method or an operator on a value of its type, a drop, a format, a generic or dyn call"
                ),
            })
        })
        .collect()
}

/// The modules with a `Drop` impl, evaluated lazily against erased value ingress (#1942).
fn drop_impl_homes(builder: &mut Builder, modules: &[Module]) -> Vec<LazyHome> {
    let mut homes = Vec::new();
    for home in modules {
        let Some(found) = home.scan.orphans.impls.iter().find(|found| found.may_drop) else {
            continue;
        };
        let target = &home.module;
        homes.push(LazyHome {
            target: builder.intern_text(target),
            crate_index: home.crate_index,
            rel: home.rel.clone(),
            site: found.site.clone(),
            reason: format!("An unproved value origin may run a destructor in {target}"),
        });
    }
    homes
}

/// Crate dependency matrix (`deps[caller_crate][home_crate]`) computed once per settlement.
fn crate_dependency_matrix(workspace: &Workspace, modules: &[Module]) -> Vec<Vec<bool>> {
    let count = workspace.crates.len();
    let mut rep: Vec<Option<&Module>> = vec![None; count];
    for module in modules {
        if let Some(slot @ None) = rep.get_mut(module.crate_index) {
            *slot = Some(module);
        }
    }
    (0..count)
        .map(|from| {
            let Some(caller) = rep.get(from).copied().flatten() else {
                return vec![false; count];
            };
            (0..count)
                .map(|to| {
                    from == to
                        || rep
                            .get(to)
                            .copied()
                            .flatten()
                            .is_some_and(|home| depends(workspace, caller, home))
                })
                .collect()
        })
        .collect()
}

/// The place of a trait impl of the file that runs code: a written impl block with an item other
/// than an associated type, or a derive other than `Copy`, which writes an impl in the module of its
/// item. `None` when the file has neither.
fn runs_code(home: &Module) -> Option<&Site> {
    let written = home.scan.orphans.impls.iter().find(|found| found.runs);
    let derived = home.scan.concerns.iter().find(|concern| {
        matches!(&concern.proof, Some(Proof::Derive(usage))
            if usage.path.last().map(String::as_str) != Some("Copy"))
    });
    written
        .map(|found| &found.site)
        .or(derived.map(|concern| &concern.site))
}
