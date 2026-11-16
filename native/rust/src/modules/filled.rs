// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a module may get a name from a macro call. A glob `use` of such a module may bring in
//! a name that the scan does not see.

use std::collections::BTreeSet;

use super::state::{Frame, Index};
use crate::tokens::NO_BIND_MACROS;
use crate::tree::Module;

/// Whether the file of `target` has a macro call at module level. Any such call may expand to a
/// `mod`, `use` or other item, of any name: the scan does not read the expansion.
pub(crate) fn may_fill(target: &Module) -> bool {
    target.scan.macro_calls.iter().any(|call| call.fills)
}

/// Whether each macro call in item place of the file adds no `use`, `extern` or `mod`, so it can
/// add a definition and never bind a name of another module (AD-608, AD-614). Each such call is a
/// call by its plain name of the one crate-wide `macro_rules!` of that name in the crate. The call
/// tokens write none of the three words, and the expansion writes none at item level and calls only
/// such macros there (`tokens::item_level`).
pub(crate) fn binds_nothing(index: &Index<'_>, frame: &Frame<'_>) -> bool {
    let mut seen = BTreeSet::new();
    let calls = frame
        .module
        .scan
        .macro_calls
        .iter()
        .filter(|call| call.fills);
    calls.collect::<Vec<_>>().into_iter().all(|call| {
        call.placed
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
    if NO_BIND_MACROS.contains(&name) || !seen.insert(name.to_owned()) {
        return true;
    }
    let crate_index = frame.module.crate_index;
    let definitions: Vec<_> = index
        .frames()
        .filter(|other| other.module.crate_index == crate_index)
        .flat_map(|other| other.module.scan.macro_defs.iter())
        .filter(|def| def.name == name)
        .collect();
    let [def] = definitions.as_slice() else {
        return false;
    };
    let items = &def.item_level;
    def.local.is_none()
        && !items.writes_use
        && (items.calls.iter()).all(|inner| expands_to_no_binding(index, frame, inner, seen))
}
