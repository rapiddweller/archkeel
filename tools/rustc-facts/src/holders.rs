// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The types of the standard library that the closedness proof of a resolved call trusts (AD-1185).

use crate::state::State;
use rustc_hir::def_id::DefId;
use rustc_middle::ty::TyCtxt;

/// The modules of the standard library whose types hold only what their type arguments name: containers,
/// options, smart pointers, cells, ranges and the iterator adapters and sources. The text of a path is the
/// canonical one that the facts use for every definition.
const ARGUMENT_HOLDERS: [&str; 43] = [
    "alloc::vec::",
    "alloc::string::",
    "alloc::boxed::",
    "alloc::rc::",
    "alloc::sync::",
    "alloc::borrow::",
    "alloc::collections::",
    "std::collections::",
    "core::option::",
    "core::result::",
    "core::cell::",
    "core::ops::range::",
    "core::iter::adapters::",
    "core::iter::sources::",
    "core::slice::iter::",
    "core::str::iter::",
    "core::marker::",
    "core::cmp::",
    "core::num::",
    "core::time::",
    "std::time::",
    "std::path::",
    "std::ffi::",
    "core::pin::",
    "alloc::alloc::",
    "alloc::slice::",
    "alloc::str::",
    "core::ptr::",
    "core::mem::",
    "core::hash::",
    "std::hash::",
    "core::convert::",
    "core::ops::control_flow::",
    "core::str::",
    "core::slice::",
    "core::array::",
    "core::char::",
    "alloc::raw_vec::",
    "core::ffi::",
    "core::sync::",
    "core::ops::",
    "core::iter::",
    "std::sys::",
];

/// For a type of the standard library: whether it holds only what its type arguments name, and whether it is a
/// type of `alloc`. Both read the path of the definition, so the answer is kept for each definition.
pub(crate) fn classify(tcx: TyCtxt<'_>, st: &mut State, d: DefId) -> (bool, bool) {
    if let Some(known) = st.holders.get(&d) {
        return *known;
    }
    let path = crate::names::path(tcx, d);
    let known = (
        ARGUMENT_HOLDERS
            .iter()
            .any(|prefix| path.starts_with(prefix)),
        path.starts_with("alloc::"),
    );
    st.holders.insert(d, known);
    known
}
