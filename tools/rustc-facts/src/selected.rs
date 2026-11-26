// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A call of `PartialEq::eq` whose impl the compiler selected in workspace code (AD-1136).
//!
//! The record states a fact of the compiler for one call site: the concrete operand types resolve to the
//! `eq` of one impl, and the impl is in the workspace. A call with a type parameter, a trait object or an
//! impl of another crate gives no record: it proves nothing here.

use crate::items::absolute;
use crate::state::{Selected, State};
use rustc_hir::def::DefKind;
use rustc_hir::def_id::DefId;
use rustc_middle::ty::{self, Ty, TyCtxt, TypeVisitableExt};
use rustc_span::{sym, FileName, Span};

/// The module of the definition: the nearest `mod` above it, the crate root included.
fn module_of(tcx: TyCtxt<'_>, d: DefId) -> DefId {
    let mut at = d;
    while tcx.def_kind(at) != DefKind::Mod {
        at = tcx.parent(at);
    }
    at
}

/// Add a record when `func_ty` is a call of `PartialEq::eq` that the compiler resolves to the `eq` of a
/// workspace impl. `owner` is the root of the body that makes the call, `caller` the id of its module.
pub(crate) fn eq_site<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    (owner, caller): (DefId, u32),
    func_ty: Ty<'tcx>,
    span: Span,
) {
    let ty::FnDef(def, args) = *func_ty.kind() else {
        return;
    };
    let trait_of = tcx.trait_of_assoc(def);
    if trait_of.is_none()
        || trait_of != tcx.lang_items().eq_trait()
        || tcx.item_name(def) != sym::eq
    {
        return;
    }
    let args = tcx.erase_and_anonymize_regions(args);
    if args.has_param() || args.has_infer() {
        return;
    }
    let env = ty::TypingEnv::post_analysis(tcx, owner);
    let Ok(Some(instance)) = ty::Instance::try_resolve(tcx, env, def, args) else {
        return;
    };
    let ty::InstanceKind::Item(selected) = instance.def else {
        return;
    };
    if tcx.trait_impl_of_assoc(selected).is_none()
        || instance.args.has_param()
        || !crate::body::inside(st, tcx, selected)
    {
        return;
    }
    let site = span.source_callsite();
    let sm = tcx.sess.source_map();
    let start = sm.lookup_char_pos(site.lo());
    if !matches!(start.file.name, FileName::Real(_)) {
        return;
    }
    let path = absolute(&start.file.name.prefer_local_unconditionally().to_string());
    let Some(rel) = path.strip_prefix(&st.root).map(str::to_string) else {
        return;
    };
    let file = st.names.text(&rel);
    let impl_module = module_of(tcx, selected);
    let to = st.names.def(tcx, impl_module);
    let impl_file = crate::items::file(tcx, st, selected);
    let imp = st.names.def(tcx, selected);
    st.selected.insert(Selected {
        from: caller,
        to,
        imp,
        file,
        impl_file,
        line: u32::try_from(start.line).unwrap_or(u32::MAX),
        column: u32::try_from(start.col.0).unwrap_or(u32::MAX),
    });
}
