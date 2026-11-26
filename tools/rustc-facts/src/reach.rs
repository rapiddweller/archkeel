// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The ADTs, `dyn` traits and opaque types that one type mentions (AD-1047).

use crate::names::Names;
use rustc_hir::def_id::DefId;
use rustc_middle::ty::{self, Ty, TyCtxt, TyKind};
use std::collections::BTreeSet;

/// What a walk over one type finds.
pub(crate) struct Found {
    pub(crate) adts: BTreeSet<u32>,
    pub(crate) dyns: BTreeSet<u32>,
    pub(crate) opaques: Vec<DefId>,
    /// The type holds a type parameter: a cast from it has no known source ADT (hole H1).
    pub(crate) param: bool,
    /// The type holds a raw pointer to `()` or `c_void`: a value behind it has no type here.
    pub(crate) erased: bool,
}

impl Found {
    /// No ADT, no `dyn` trait and no opaque type: nothing flows.
    pub(crate) fn is_empty(&self) -> bool {
        self.adts.is_empty() && self.dyns.is_empty() && self.opaques.is_empty()
    }

    pub(crate) fn new() -> Found {
        Found {
            adts: BTreeSet::new(),
            dyns: BTreeSet::new(),
            opaques: Vec::new(),
            param: false,
            erased: false,
        }
    }
}

/// Add every ADT, `dyn` principal trait, opaque type and type parameter inside `ty`.
pub(crate) fn scan<'tcx>(tcx: TyCtxt<'tcx>, names: &mut Names, ty: Ty<'tcx>, out: &mut Found) {
    for arg in ty.walk() {
        let Some(t) = arg.as_type() else { continue };
        match t.kind() {
            TyKind::Adt(def, _) => {
                if !def.did().is_local() {
                    names.foreign.insert(def.did());
                }
                out.adts.insert(names.def(tcx, def.did()));
            }
            TyKind::Alias(a) => {
                if let ty::AliasTyKind::Opaque { def_id } = a.kind {
                    out.opaques.push(def_id);
                }
            }
            // A `dyn Tr + Send` holds the types that were coerced to `Tr`: the auto traits add no type. A `dyn Send`
            // has no principal trait: its auto traits are its keys. A coercion to it from a `dyn Tr` keeps the
            // types of `Tr` (`src_dyn`).
            TyKind::Dynamic(preds, _) => {
                let keys: Vec<DefId> = match preds.principal_def_id() {
                    Some(principal) => vec![principal],
                    None => preds.auto_traits().collect(),
                };
                for d in keys {
                    names.dyn_traits.insert(d);
                    let id = fn_dyn(tcx, names, preds, d).unwrap_or_else(|| names.def(tcx, d));
                    out.dyns.insert(id);
                }
            }
            // The values that a coroutine (async body) holds across an await are the locals of its
            // body: the module that holds the future reaches them (AD-1047, async hole).
            TyKind::Coroutine(def_id, _) | TyKind::CoroutineClosure(def_id, _)
                if def_id.is_local() =>
            {
                out.opaques.push(*def_id);
            }
            TyKind::Param(_) => out.param = true,
            TyKind::RawPtr(inner, _) if erases(tcx, *inner) => out.erased = true,
            _ => {}
        }
    }
}

/// The id of a `dyn Fn*(Args) -> R` that the walk keys by its signature (AD-1160), or `None` for any other `dyn`.
/// A signature that the walk writes in full is a key of its own: a closure coerced to `dyn Fn(u8)` is no value
/// of a `dyn Fn(&str)`. Regions are left out, because a `for<'a> Fn(&'a u8)` and a `Fn(&'static u8)` convert by
/// subtyping. A signature with a type parameter, a projection, an opaque type or any form that the walk does not
/// write names the open key: a coercion site then names the plain trait and a receiver reads every key.
fn fn_dyn<'tcx>(
    tcx: TyCtxt<'tcx>,
    names: &mut Names,
    preds: &'tcx ty::List<ty::Binder<'tcx, ty::ExistentialPredicate<'tcx>>>,
    d: DefId,
) -> Option<u32> {
    tcx.fn_trait_kind_from_def_id(d)?;
    let plain = names.def(tcx, d);
    let base = crate::names::path(tcx, d);
    let sig = signature(tcx, preds);
    let Some(sig) = sig else {
        let open = names.text(&format!("{base}<*>"));
        names.fn_open = true;
        names.fn_site.insert(open, plain);
        return Some(open);
    };
    let id = names.text(&format!("{base}<{sig}>"));
    names.fn_sigs.insert(sig);
    Some(id)
}

/// The text of the argument tuple and the result of a `dyn Fn*`, or `None` when a part is not written in full.
fn signature<'tcx>(
    tcx: TyCtxt<'tcx>,
    preds: &'tcx ty::List<ty::Binder<'tcx, ty::ExistentialPredicate<'tcx>>>,
) -> Option<String> {
    let args = preds.principal()?.skip_binder().args.first()?.as_type()?;
    let output = preds
        .projection_bounds()
        .find(|p| tcx.is_lang_item(p.skip_binder().def_id, rustc_hir::LangItem::FnOnceOutput))?
        .skip_binder()
        .term
        .as_type()?;
    if !matches!(args.kind(), TyKind::Tuple(_)) {
        return None;
    }
    Some(format!(
        "{}->{}",
        type_text(tcx, args)?,
        type_text(tcx, output)?
    ))
}

/// A type that is written in full and has the same text in each unit of a build, or `None`.
fn type_text<'tcx>(tcx: TyCtxt<'tcx>, ty: Ty<'tcx>) -> Option<String> {
    let list = |items: &mut dyn Iterator<Item = Ty<'tcx>>| -> Option<String> {
        let texts: Option<Vec<String>> = items.map(|t| type_text(tcx, t)).collect();
        Some(texts?.join(","))
    };
    match ty.kind() {
        TyKind::Bool | TyKind::Char | TyKind::Str | TyKind::Never => Some(ty.to_string()),
        TyKind::Int(_) | TyKind::Uint(_) | TyKind::Float(_) => Some(ty.to_string()),
        TyKind::Tuple(items) => Some(format!("({})", list(&mut items.iter())?)),
        TyKind::Ref(_, inner, m) => Some(format!("&{}{}", m.prefix_str(), type_text(tcx, *inner)?)),
        TyKind::RawPtr(inner, m) => Some(format!("*{}{}", m.ptr_str(), type_text(tcx, *inner)?)),
        TyKind::Slice(inner) => Some(format!("[{}]", type_text(tcx, *inner)?)),
        TyKind::Array(inner, len) => {
            let len = len.try_to_target_usize(tcx)?;
            Some(format!("[{};{len}]", type_text(tcx, *inner)?))
        }
        TyKind::Adt(def, args) => {
            let mut types = args.iter().filter_map(|a| a.as_type());
            let all = args.iter().filter(|a| a.as_region().is_none()).count();
            let inner = list(&mut types)?;
            let kept = inner.split(',').filter(|s| !s.is_empty()).count();
            // A const argument is not a type: the walk does not write it.
            (kept == all).then(|| format!("{}<{inner}>", crate::names::path(tcx, def.did())))
        }
        _ => None,
    }
}

/// A pointee that says nothing of the value: `()`, `c_void`, an extern type, a number (`*mut u8`).
fn erases(tcx: TyCtxt<'_>, pointee: Ty<'_>) -> bool {
    match pointee.kind() {
        TyKind::Tuple(items) => items.is_empty(),
        TyKind::Foreign(_) | TyKind::Int(_) | TyKind::Uint(_) => true,
        TyKind::Adt(def, _) => tcx.is_diagnostic_item(rustc_span::sym::c_void, def.did()),
        _ => false,
    }
}
