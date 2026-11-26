// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The records of ADTs, impls and opaque types, taken after analysis (AD-1047).

use crate::json;
use crate::reach::{scan, Found};
use crate::state::State;
use rustc_hir::def::DefKind;
use rustc_hir::def_id::{DefId, LOCAL_CRATE};
use rustc_hir::ItemKind;
use rustc_hir::LangItem;
use rustc_middle::ty::{self, TyCtxt, TyKind};
use std::collections::BTreeSet;

/// The id of the source file text of a definition, relative to the workspace root when it is inside.
pub(crate) fn file(tcx: TyCtxt<'_>, st: &mut State, d: DefId) -> u32 {
    let sm = tcx.sess.source_map();
    let name = sm.span_to_filename(tcx.def_span(d).source_callsite());
    let text = relative(&st.root, &name.prefer_local_unconditionally().to_string());
    st.names.text(&text)
}

/// The working directory of this process. Cargo runs rustc in the workspace, with relative paths.
fn working_directory() -> &'static str {
    static CWD: std::sync::OnceLock<String> = std::sync::OnceLock::new();
    CWD.get_or_init(|| {
        std::env::current_dir()
            .map(|d| d.display().to_string())
            .unwrap_or_default()
    })
}

/// The absolute path with `/` separators and without `.` and `..` parts.
pub(crate) fn absolute(path: &str) -> String {
    let p = path.replace('\\', "/");
    let full = if std::path::Path::new(&p).is_absolute() {
        p
    } else {
        format!("{}/{p}", working_directory().replace('\\', "/"))
    };
    let mut parts: Vec<&str> = Vec::new();
    for part in full.split('/') {
        match part {
            "." => {}
            ".." => {
                parts.pop();
            }
            other => parts.push(other),
        }
    }
    parts.join("/")
}

/// A path relative to the root when it is inside the root, else the absolute path.
pub(crate) fn relative(root: &str, path: &str) -> String {
    let abs = absolute(path);
    abs.strip_prefix(root).map(str::to_string).unwrap_or(abs)
}

pub(crate) fn line(tcx: TyCtxt<'_>, d: DefId) -> usize {
    let sp = tcx.def_span(d).source_callsite();
    tcx.sess.source_map().lookup_char_pos(sp.lo()).line
}

fn found(tcx: TyCtxt<'_>, st: &mut State, ty: rustc_middle::ty::Ty<'_>, f: &mut Found) {
    scan(tcx, &mut st.names, ty, f);
    for d in &f.opaques {
        st.opaque_defs.insert(*d);
    }
}

/// One `opaque` record for each local opaque type, and one for each coroutine that a type mentions, to
/// a fixpoint: a hidden type can mention another opaque type. A coroutine stands for the locals of its
/// body, which are the types that its future holds across an await.
pub(crate) fn opaques(tcx: TyCtxt<'_>, st: &mut State, out: &mut Vec<String>) {
    for d in tcx.hir_crate_items(()).opaques() {
        st.opaque_defs.insert(d.to_def_id());
    }
    let mut done: std::collections::HashSet<DefId> = std::collections::HashSet::new();
    loop {
        let todo: Vec<DefId> = st
            .opaque_defs
            .iter()
            .filter(|d| !done.contains(*d))
            .copied()
            .collect();
        if todo.is_empty() {
            return;
        }
        for d in todo {
            done.insert(d);
            if d.krate != LOCAL_CRATE {
                continue;
            }
            let id = st.names.def(tcx, d);
            let (adts, dyns, nested) = if tcx.is_coroutine(d) {
                let held = st.coroutines.get(&id);
                let take =
                    |h: &crate::state::Hidden| (h.adts.clone(), h.dyns.clone(), h.opaques.clone());
                held.map(take).unwrap_or_default()
            } else {
                let mut f = Found::new();
                let ty = tcx.type_of(d).instantiate_identity().skip_norm_wip();
                found(tcx, st, ty, &mut f);
                let nested = f.opaques.iter().map(|o| st.names.def(tcx, *o)).collect();
                (f.adts, f.dyns, nested)
            };
            out.push(format!(
                "{{\"k\":\"opaque\",\"d\":{id},\"hidden\":{},\"dyn\":{},\"opaque\":{}}}",
                json::ids(&adts),
                json::ids(&dyns),
                json::ids(&nested)
            ));
        }
    }
}

/// One `adt` record for each struct, enum and union, and one `impl` record for each impl.
pub(crate) fn items(tcx: TyCtxt<'_>, st: &mut State, out: &mut Vec<String>) {
    for id in tcx.hir_free_items() {
        let item = tcx.hir_item(id);
        let did = item.owner_id.to_def_id();
        match item.kind {
            ItemKind::Struct(..) | ItemKind::Enum(..) | ItemKind::Union(..) => {
                adt(tcx, st, did, out)
            }
            ItemKind::Impl(_) => imp(tcx, st, did, out),
            _ => {}
        }
    }
}

fn adt(tcx: TyCtxt<'_>, st: &mut State, did: DefId, out: &mut Vec<String>) {
    let mut f = Found::new();
    for field in tcx.adt_def(did).all_fields() {
        found(
            tcx,
            st,
            tcx.type_of(field.did)
                .instantiate_identity()
                .skip_norm_wip(),
            &mut f,
        );
    }
    let (d, m, fl) = (
        st.names.def(tcx, did),
        st.names.def(
            tcx,
            tcx.parent_module_from_def_id(did.expect_local())
                .to_def_id(),
        ),
        file(tcx, st, did),
    );
    if f.erased {
        st.erased_adts.insert(d);
    }
    st.adt_fields.insert(d, f.adts.clone());
    out.push(format!(
        "{{\"k\":\"adt\",\"d\":{d},\"m\":{m},\"file\":{fl},\"fields\":{},\"dyn\":{},\"erased\":{}}}",
        json::ids(&f.adts),
        json::ids(&f.dyns),
        f.erased
    ));
}

/// An impl runs code when it has a function, or when its trait has a function with a default body.
fn runs_code(tcx: TyCtxt<'_>, did: DefId, trait_id: Option<DefId>) -> bool {
    let own = tcx
        .associated_item_def_ids(did)
        .iter()
        .any(|i| tcx.def_kind(*i) == DefKind::AssocFn);
    let inherited = trait_id.is_some_and(|t| {
        tcx.associated_item_def_ids(t)
            .iter()
            .any(|i| tcx.def_kind(*i) == DefKind::AssocFn && tcx.defaultness(*i).has_value())
    });
    own || inherited
}

fn imp(tcx: TyCtxt<'_>, st: &mut State, did: DefId, out: &mut Vec<String>) {
    let self_ty = tcx.type_of(did).instantiate_identity().skip_norm_wip();
    let mut self_f = Found::new();
    found(tcx, st, self_ty, &mut self_f);
    let self_adt = match self_ty.kind() {
        TyKind::Adt(a, _) => Some(st.names.def(tcx, a.did())),
        _ => None,
    };
    let tr = tcx
        .impl_opt_trait_ref(did)
        .map(|t| t.instantiate_identity().skip_norm_wip().def_id);
    let mut assoc = Found::new();
    for i in tcx.associated_item_def_ids(did) {
        if tcx.def_kind(*i) == DefKind::AssocTy {
            found(
                tcx,
                st,
                tcx.type_of(*i).instantiate_identity().skip_norm_wip(),
                &mut assoc,
            );
        }
    }
    // An opaque type in an associated type is reached by its name, as in a type argument.
    let mut assoc_names = assoc.adts.clone();
    for d in &assoc.opaques {
        assoc_names.insert(st.names.def(tcx, *d));
    }
    let items: BTreeSet<u32> = tcx
        .associated_item_def_ids(did)
        .iter()
        .map(|i| st.names.text(tcx.item_name(*i).as_str()))
        .collect();
    let (m, fl) = (
        st.names.def(
            tcx,
            tcx.parent_module_from_def_id(did.expect_local())
                .to_def_id(),
        ),
        file(tcx, st, did),
    );
    let trait_s = tr.map_or("null".to_string(), |t| st.names.def(tcx, t).to_string());
    let self_s = self_adt.map_or("null".to_string(), |a| a.to_string());
    out.push(format!(
        "{{\"k\":\"impl\",\"trait\":{trait_s},\"self\":{self_s},\"self_adts\":{},\"assoc\":{},\"assoc_dyn\":{},\"items\":{},\"m\":{m},\"file\":{fl},\"line\":{},\"run\":{},\"expansion\":{}}}",
        json::ids(&self_f.adts), json::ids(&assoc_names), json::ids(&assoc.dyns), json::ids(&items), line(tcx, did), runs_code(tcx, did, tr), tcx.def_span(did).from_expansion(),
    ));
}

/// One `adt` record for each ADT of another crate that a type walk met, to a fixpoint: the fields of
/// such an ADT can name more of them. A foreign ADT holds a `dyn` value that no type argument shows
/// (`io::Error` holds `Box<dyn Error>`), so a module that mentions it reaches that `dyn`.
pub(crate) fn foreign(tcx: TyCtxt<'_>, st: &mut State, out: &mut Vec<String>) {
    let mut done: std::collections::HashSet<DefId> = std::collections::HashSet::new();
    loop {
        let todo: Vec<DefId> = st
            .names
            .foreign
            .iter()
            .filter(|d| !done.contains(*d))
            .copied()
            .collect();
        if todo.is_empty() {
            return;
        }
        // The order of a set is no order: sort, so that the same code gives the same file.
        let mut todo = todo;
        todo.sort_by_cached_key(|d| crate::names::path(tcx, *d));
        for did in todo {
            done.insert(did);
            let mut f = Found::new();
            for field in tcx.adt_def(did).all_fields() {
                let ty = tcx
                    .type_of(field.did)
                    .instantiate_identity()
                    .skip_norm_wip();
                found(tcx, st, ty, &mut f);
            }
            let id = st.names.def(tcx, did);
            if f.erased {
                st.erased_adts.insert(id);
            }
            st.adt_fields.insert(id, f.adts.clone());
            out.push(format!(
                "{{\"k\":\"adt\",\"d\":{},\"fields\":{},\"dyn\":{},\"erased\":{}}}",
                st.names.def(tcx, did),
                json::ids(&f.adts),
                json::ids(&f.dyns),
                f.erased
            ));
        }
    }
}

/// The traits of the size of a type (`Sized`, `MetaSized`, `PointeeSized`): they bound each parameter and say
/// nothing of what code can do with it.
pub(crate) fn sizedness(tcx: TyCtxt<'_>, tr: DefId) -> bool {
    [LangItem::Sized, LangItem::MetaSized, LangItem::PointeeSized]
        .iter()
        .any(|item| tcx.is_lang_item(tr, *item))
}

/// One `open` record for each `dyn` trait that a type walk met and whose implementers the workspace impls
/// do not list: an auto trait, or a trait with a blanket impl `impl<T: ..> Tr for T` in any crate (`Any`).
/// Foreign code can coerce a type that flows into it to such a `dyn`, when the type has the traits in
/// `needs` (the bounds of the blanket impl on `T`, without `Sized` and auto traits): `Debug` has a blanket
/// impl for `F: FnPtr` only, so no workspace type has it by that impl.
pub(crate) fn open(tcx: TyCtxt<'_>, st: &mut State, out: &mut Vec<String>) {
    let mut traits: Vec<DefId> = st.names.dyn_traits.iter().copied().collect();
    traits.sort_by_cached_key(|d| crate::names::path(tcx, *d));
    for tr in traits {
        let id = st.names.def(tcx, tr);
        if tcx.trait_is_auto(tr) {
            out.push(format!("{{\"k\":\"open\",\"tr\":{id},\"needs\":[]}}"));
            continue;
        }
        for imp in tcx.trait_impls_of(tr).blanket_impls() {
            let mut needs = BTreeSet::new();
            let self_ty = tcx.type_of(*imp).instantiate_identity().skip_norm_wip();
            if let TyKind::Param(own) = self_ty.kind() {
                for clause in tcx.predicates_of(*imp).instantiate_identity(tcx).predicates {
                    let ty::ClauseKind::Trait(bound) = clause.kind().skip_binder() else {
                        continue;
                    };
                    let on_self =
                        matches!(bound.self_ty().kind(), TyKind::Param(p) if p.index == own.index);
                    let plain = sizedness(tcx, bound.def_id()) || tcx.trait_is_auto(bound.def_id());
                    if on_self && !plain {
                        needs.insert(st.names.def(tcx, bound.def_id()));
                    }
                }
            }
            out.push(format!(
                "{{\"k\":\"open\",\"tr\":{id},\"needs\":{}}}",
                json::ids(&needs)
            ));
        }
    }
}

/// One `super` record for each `dyn` trait that a type walk met and that has supertraits: a value of a
/// `dyn Sub` can be upcast to a `dyn Super` in code that no body of the workspace shows.
pub(crate) fn supers(tcx: TyCtxt<'_>, st: &mut State, out: &mut Vec<String>) {
    let mut traits: Vec<DefId> = st.names.dyn_traits.iter().copied().collect();
    traits.sort_by_cached_key(|d| crate::names::path(tcx, *d));
    for tr in traits {
        let sups: BTreeSet<u32> = supertraits(tcx, tr)
            .into_iter()
            .filter(|s| *s != tr && !sizedness(tcx, *s) && !tcx.trait_is_auto(*s))
            .map(|s| st.names.def(tcx, s))
            .collect();
        if !sups.is_empty() {
            out.push(format!(
                "{{\"k\":\"super\",\"tr\":{},\"sup\":{}}}",
                st.names.def(tcx, tr),
                json::ids(&sups)
            ));
        }
    }
}

/// The supertraits of `tr`, to a fixpoint.
fn supertraits(tcx: TyCtxt<'_>, tr: DefId) -> std::collections::HashSet<DefId> {
    let mut found = std::collections::HashSet::new();
    let mut todo = vec![tr];
    while let Some(next) = todo.pop() {
        for (clause, _) in tcx.explicit_super_predicates_of(next).skip_binder() {
            if let ty::ClauseKind::Trait(bound) = clause.kind().skip_binder() {
                if found.insert(bound.def_id()) {
                    todo.push(bound.def_id());
                }
            }
        }
    }
    found
}

/// Each ADT that holds an erasing ADT in a field erases too (`Waker` holds `RawWaker`), to a fixpoint.
pub(crate) fn close_erased(st: &mut State) {
    loop {
        let more: Vec<u32> = st
            .adt_fields
            .iter()
            .filter(|(d, fields)| {
                !st.erased_adts.contains(*d) && fields.iter().any(|f| st.erased_adts.contains(f))
            })
            .map(|(d, _)| *d)
            .collect();
        if more.is_empty() {
            return;
        }
        st.erased_adts.extend(more);
    }
}
