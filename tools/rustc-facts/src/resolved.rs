// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A method call `x.m()` whose callee the compiler resolved (AD-1185).
//!
//! The record states a fact of the compiler for one call site: the operand types are concrete and the call goes
//! to one function. The site is the span of `m(..)` (`fn_span`), the place where the scan reads the method name.
//! A call with a type parameter, a trait object or a call that a macro wrote gives no record.

use crate::items::absolute;
use crate::state::{ImplIndex, Resolved, State};
use rustc_hir::def_id::{DefId, LOCAL_CRATE};
use rustc_middle::ty::{self, GenericArgsRef, Ty, TyCtxt, TypeVisitableExt};
use rustc_span::{FileName, Span};
use std::collections::BTreeSet;

/// The impls of the workspace by the self type that they name: an ADT, a type parameter (blanket) or another type.
fn impl_index(st: &mut State, tcx: TyCtxt<'_>) -> ImplIndex {
    let mut index = ImplIndex::default();
    let crates = std::iter::once(LOCAL_CRATE).chain(tcx.crates(()).iter().copied());
    for cnum in crates {
        let root = DefId {
            krate: cnum,
            index: rustc_hir::def_id::CRATE_DEF_INDEX,
        };
        if cnum != LOCAL_CRATE && !crate::body::inside(st, tcx, root) {
            continue;
        }
        for imp in tcx.trait_impls_in_crate(cnum) {
            let file = crate::items::file(tcx, st, *imp);
            match tcx.type_of(*imp).skip_binder().kind() {
                ty::Adt(def, _) => {
                    index.by_adt.entry(def.did()).or_default().insert(file);
                }
                ty::Param(_) => {
                    index.blanket.insert(file);
                }
                _ => {
                    index.other.insert(file);
                }
            }
        }
    }
    index
}

/// What the type arguments of a call can run: the files that hold the types, the closures and the impls of them.
/// `open` when an argument is not fully known (a trait object, a type parameter): then nothing is proven.
fn touch<'tcx>(
    st: &mut State,
    tcx: TyCtxt<'tcx>,
    env: ty::TypingEnv<'tcx>,
    args: GenericArgsRef<'tcx>,
) -> (BTreeSet<u32>, bool) {
    if st.impls.is_none() {
        let index = impl_index(st, tcx);
        st.impls = Some(index);
    }
    let mut files = BTreeSet::new();
    let mut open = false;
    let mut non_adt = false;
    for arg in args.iter() {
        let Some(ty) = arg.as_type() else { continue };
        let ty = tcx.try_normalize_erasing_regions(env, ty::Unnormalized::new(ty)).unwrap_or(ty);
        for node in ty.walk().filter_map(|g| g.as_type()) {
            match node.kind() {
                ty::Adt(def, _) => {
                    files.insert(crate::items::file(tcx, st, def.did()));
                    for imp in tcx.inherent_impls(def.did()) {
                        files.insert(crate::items::file(tcx, st, *imp));
                    }
                    if let Some(found) = st.impls.as_ref().and_then(|i| i.by_adt.get(&def.did())) {
                        files.extend(found.iter().copied());
                    }
                }
                ty::Closure(d, _)
                | ty::CoroutineClosure(d, _)
                | ty::Coroutine(d, _)
                | ty::FnDef(d, _)
                | ty::Foreign(d) => {
                    files.insert(crate::items::file(tcx, st, *d));
                }
                ty::Dynamic(..)
                | ty::Param(_)
                | ty::Infer(_)
                | ty::Placeholder(_)
                | ty::Bound(..)
                | ty::Alias(..)
                | ty::Error(_) => open = true,
                _ => non_adt = true,
            }
        }
    }
    if let Some(index) = st.impls.as_ref() {
        files.extend(index.blanket.iter().copied());
        if non_adt {
            files.extend(index.other.iter().copied());
        }
    }
    (files, open)
}

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
    let env = ty::TypingEnv::post_analysis(tcx, owner);
    let args = tcx.erase_and_anonymize_regions(args);
    let (callee, instance_args) = if trait_of.is_some() {
        if args.has_param() || args.has_infer() {
            return;
        }
        let Ok(Some(instance)) = ty::Instance::try_resolve(tcx, env, def, args) else {
            return;
        };
        let ty::InstanceKind::Item(selected) = instance.def else {
            return;
        };
        if instance.args.has_param() {
            return;
        }
        (selected, instance.args)
    } else {
        (def, args)
    };
    let (touch, open) = touch(st, tcx, env, instance_args);
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
        callee_line: inside
            .then(|| crate::items::line(tcx, callee))
            .and_then(|l| u32::try_from(l).ok()),
        touch,
        open,
        line: u32::try_from(start.line).unwrap_or(u32::MAX),
        column: u32::try_from(start.col.0).unwrap_or(u32::MAX),
    });
}
