// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Whether a module may get a name from a macro call. A glob `use` of such a module may bring in
//! a name that the scan does not see.

use crate::tree::Module;

/// Whether the file of `target` has a macro call at module level. Any such call may expand to a
/// `mod`, `use` or other item, of any name: the scan does not read the expansion.
pub(crate) fn may_fill(target: &Module) -> bool {
    target.scan.macro_calls.iter().any(|call| call.fills)
}
