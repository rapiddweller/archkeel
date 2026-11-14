// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a module may get a module name or a `use` binding from a macro call. A glob `use` of
//! such a module may bring in a name that the scan does not see.

use crate::tree::Module;

/// Whether a call at module level of `target` may declare a module name. A call is safe when a
/// `macro_rules!` of its crate (in `all`) defines its name, and neither its body nor its tokens
/// hold `mod`, `use` or `extern`, and its body calls no other macro. Any other call may fill it.
pub(crate) fn may_fill<'a>(target: &Module, all: impl Iterator<Item = &'a Module> + Clone) -> bool {
    let same = |module: &&Module| module.crate_index == target.crate_index;
    let defs = all
        .filter(same)
        .flat_map(|module| module.scan.macro_defs.iter());
    target
        .scan
        .macro_calls
        .iter()
        .filter(|call| call.fills)
        .any(|call| {
            let mut named = defs.clone().filter(|def| def.name == call.name).peekable();
            call.declares
                || named.peek().is_none()
                || named.any(|d| d.declares || !d.calls.is_empty())
        })
}
