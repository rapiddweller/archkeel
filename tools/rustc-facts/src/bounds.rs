// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Which type parameters of a callee outside the workspace can be erased there (AD-1047).

use rustc_hir::def_id::DefId;
use rustc_middle::ty::{self, TyCtxt, TypeSuperVisitable, TypeVisitable};

/// The type parameters that a visited clause names.
struct Params(Vec<usize>);

impl<'tcx> ty::TypeVisitor<TyCtxt<'tcx>> for Params {
    type Result = ();

    fn visit_ty(&mut self, t: ty::Ty<'tcx>) {
        if let ty::Param(p) = t.kind() {
            self.0.push(p.index as usize);
        }
        t.super_visit_with(self);
    }
}

/// Which generic parameters of `d` are named by a clause besides their own `Sized`. Code that knows nothing
/// of a parameter but `Sized` can move it and drop it, and nothing else: it cannot coerce it to a `dyn`. Any
/// other clause counts: a trait (`Send`, `Into<U>`), `'static` (`Any` holds for each `'static` type), a lifetime,
/// a projection, and a clause of another type that holds the parameter (`Wrapper<T>: Tr`).
pub(crate) fn bounded_params(tcx: TyCtxt<'_>, d: DefId) -> Vec<bool> {
    let mut bounded = vec![false; tcx.generics_of(d).count()];
    for clause in tcx.predicates_of(d).instantiate_identity(tcx).predicates {
        if let ty::ClauseKind::Trait(bound) = clause.kind().skip_binder() {
            if crate::items::sizedness(tcx, bound.def_id()) {
                continue;
            }
        }
        let mut named = Params(Vec::new());
        clause.visit_with(&mut named);
        for at in named.0 {
            if let Some(slot) = bounded.get_mut(at) {
                *slot = true;
            }
        }
    }
    bounded
}
