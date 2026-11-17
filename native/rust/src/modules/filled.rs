// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a module may get a name from a macro call. A glob `use` of such a module may bring in
//! a name that the scan does not see.

use std::collections::BTreeSet;

use super::state::{Frame, Index};
use crate::std_macros;
use crate::tree::Module;

/// Whether the file of `target` has a macro call at module level. Any such call may expand to a
/// `mod`, `use` or other item, of any name: the scan does not read the expansion.
pub(crate) fn may_fill(target: &Module) -> bool {
    target.scan.macro_calls.iter().any(|call| call.fills)
}

/// Whether each macro call in item place of the file adds no `use`, `extern` or `mod`, so it can
/// add a definition and never bind a name of another module (AD-608, AD-614, #1346).
///
/// The proof needs that each such call names a macro that the scan reads:
/// - the call is by its plain name, and no `use` leaf and no glob of the file can bring in a
///   macro of that name;
/// - no `extern crate` of the crate can bring in macros (`#[macro_use]`), and no macro of the
///   crate defines a macro, which no scan of a definition sees;
/// - the name has one crate-wide `macro_rules!`, or none and is a silent macro of `std`;
/// - the call tokens write none of the three words, and the expansion writes none at item level
///   and calls only such macros there, by their plain names (`macro_items::item_level`).
pub(crate) fn binds_nothing(index: &Index<'_>, frame: &Frame<'_>) -> bool {
    let crate_index = frame.module.crate_index;
    let crate_frames = || {
        index
            .frames()
            .filter(move |other| other.module.crate_index == crate_index)
    };
    let opened = crate_frames().any(|other| {
        let scan = &other.module.scan;
        !scan.extern_crates.is_empty()
            || scan
                .macro_defs
                .iter()
                .any(|def| def.item_level.defines_macros)
    });
    if opened || frame.globs().next().is_some() {
        return false;
    }
    let mut seen = BTreeSet::new();
    let calls = frame
        .module
        .scan
        .macro_calls
        .iter()
        .filter(|call| call.fills);
    calls.collect::<Vec<_>>().into_iter().all(|call| {
        call.placed
            && call.path.len() == 1
            && !call.writes_use
            && frame.bound(&call.name).is_empty()
            && expands_to_no_binding(index, frame, &call.name, &mut seen)
    })
}

fn expands_to_no_binding(
    index: &Index<'_>,
    frame: &Frame<'_>,
    name: &str,
    seen: &mut BTreeSet<String>,
) -> bool {
    if !seen.insert(name.to_owned()) {
        return true;
    }
    let crate_index = frame.module.crate_index;
    let definitions: Vec<_> = index
        .frames()
        .filter(|other| other.module.crate_index == crate_index)
        .flat_map(|other| other.module.scan.macro_defs.iter())
        .filter(|def| def.name == name)
        .collect();
    // A macro of the crate shadows the `std` macro of its name (`vec`, `write`).
    let def = match definitions.as_slice() {
        [] => return std_macros::has(name, std_macros::NO_BIND),
        [def] => def,
        _ => return false,
    };
    let items = &def.item_level;
    def.local.is_none()
        && !items.writes_use
        && !items.path_calls
        && !items.defines_macros
        && (items.calls.iter()).all(|inner| expands_to_no_binding(index, frame, inner, seen))
}
