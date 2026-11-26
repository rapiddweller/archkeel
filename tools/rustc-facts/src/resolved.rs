// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A method call `x.m()` whose callee the compiler resolved (AD-1185).
//!
//! The record states a fact of the compiler for one call site: the operand types are concrete and the call goes
//! to one function. The site is the span of `m(..)` (`fn_span`), the place where the scan reads the method name.
//! A call with a type parameter, a trait object or a call that a macro wrote gives no record.

use crate::items::absolute;
use crate::state::{Resolved, State};
use rustc_hir::def_id::DefId;
use rustc_middle::ty::{self, Ty, TyCtxt, TypeVisitableExt};
use rustc_span::{FileName, Span};

/// Add a record when `func_ty` is a method call that the compiler resolves to one function. `owner` is the root
/// of the body that makes the call, `caller` the id of its module. `span` is the whole call, `fn_span` its `m(..)`.
pub(crate) fn method_site<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    (owner, caller): (DefId, u32),
    func_ty: Ty<'tcx>,
    (span, fn_span): (Span, Span),
) {
    // A path call `T::m(..)` starts where its function starts: only a dot call has a receiver before `m`.
    if fn_span.from_expansion() || fn_span.lo() == span.lo() {
        return;
    }
    let ty::FnDef(def, args) = *func_ty.kind() else {
        return;
    };
    let trait_of = tcx.trait_of_assoc(def);
    if trait_of.is_some() && trait_of == tcx.lang_items().eq_trait() {
        return;
    }
    let callee = if trait_of.is_some() {
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
        if instance.args.has_param() {
            return;
        }
        selected
    } else {
        def
    };
    let start = tcx.sess.source_map().lookup_char_pos(fn_span.lo());
    if !matches!(start.file.name, FileName::Real(_)) {
        return;
    }
    let path = absolute(&start.file.name.prefer_local_unconditionally().to_string());
    let Some(rel) = path.strip_prefix(&st.root).map(str::to_string) else {
        return;
    };
    let file = st.names.text(&rel);
    let callee_id = st.names.def(tcx, callee);
    let inside = crate::body::inside(st, tcx, callee);
    let to = inside.then(|| {
        let module = crate::selected::module_of(tcx, callee);
        st.names.def(tcx, module)
    });
    let callee_file = inside.then(|| crate::items::file(tcx, st, callee));
    st.calls.insert(Resolved {
        from: caller,
        to,
        callee: callee_id,
        file,
        callee_file,
        line: u32::try_from(start.line).unwrap_or(u32::MAX),
        column: u32::try_from(start.col.0).unwrap_or(u32::MAX),
    });
}
