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
pub(crate) fn scan(tcx: TyCtxt<'_>, names: &mut Names, ty: Ty<'_>, out: &mut Found) {
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
                    out.dyns.insert(names.def(tcx, d));
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

/// A pointee that says nothing of the value: `()`, `c_void`, an extern type, a number (`*mut u8`).
fn erases(tcx: TyCtxt<'_>, pointee: Ty<'_>) -> bool {
    match pointee.kind() {
        TyKind::Tuple(items) => items.is_empty(),
        TyKind::Foreign(_) | TyKind::Int(_) | TyKind::Uint(_) => true,
        TyKind::Adt(def, _) => tcx.is_diagnostic_item(rustc_span::sym::c_void, def.did()),
        _ => false,
    }
}
