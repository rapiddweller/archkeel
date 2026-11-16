// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The macros of `std` that the collector knows, written once, each with the roles that a reader
//! selects. The roles differ on purpose: each one is a fact that a proof reads (AD-524, AD-614),
//! and the doc of the role says which.

/// The role of a macro name.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) struct Role(u8);

impl Role {
    /// A function-like macro of `std`, `core` and `alloc` whose expansion writes only paths of
    /// those crates and the call tokens. `include!` reads a file and `thread_local!` writes
    /// items: they are not here.
    pub(crate) const PATHS_ONLY: Role = Role(1);
    /// A macro of the standard library or of `serde_json` whose body is an expression, so a path
    /// inside is a path of this file. A macro of another name that holds a path is UNKNOWN.
    pub(crate) const EXPRESSION_BODY: Role = Role(1 << 1);
    /// A macro that expands to an expression of the place of the call and names no item of the
    /// crate that defines a macro (AD-614).
    pub(crate) const PLACE_EXPRESSION: Role = Role(1 << 2);
    /// A macro that binds no name in the code around its call (AD-524).
    pub(crate) const NO_BIND: Role = Role(1 << 3);
}

use Role as R;

const fn roles(parts: &[Role]) -> u8 {
    let mut flags = 0;
    let mut index = 0;
    while index < parts.len() {
        flags |= parts[index].0;
        index += 1;
    }
    flags
}

/// The roles of a macro that is an expression of `std` and binds nothing.
const SILENT: u8 = roles(&[R::PATHS_ONLY, R::EXPRESSION_BODY, R::NO_BIND]);
/// The roles of an expression macro of the place of the call.
const PLACE: u8 = roles(&[R::PATHS_ONLY, R::EXPRESSION_BODY, R::PLACE_EXPRESSION]);
/// The roles of a macro of `std` with neither narrower role: it is no place expression, and the
/// reader does not state that it binds no name.
const STD_ONLY: u8 = roles(&[R::PATHS_ONLY, R::EXPRESSION_BODY]);

/// Each macro name with its roles.
const TABLE: [(&str, u8); 34] = [
    ("assert", SILENT),
    ("assert_eq", SILENT),
    ("assert_ne", SILENT),
    ("debug_assert", SILENT),
    ("debug_assert_eq", SILENT),
    ("debug_assert_ne", SILENT),
    ("format", SILENT),
    ("format_args", SILENT),
    ("print", SILENT),
    ("println", SILENT),
    ("eprint", SILENT),
    ("eprintln", SILENT),
    ("write", SILENT),
    ("writeln", SILENT),
    ("panic", SILENT),
    ("unreachable", SILENT),
    ("todo", STD_ONLY),
    ("unimplemented", STD_ONLY),
    ("vec", SILENT),
    ("matches", SILENT),
    ("dbg", STD_ONLY),
    ("env", PLACE),
    ("option_env", PLACE),
    ("concat", PLACE),
    ("stringify", PLACE),
    ("line", PLACE),
    ("file", PLACE),
    ("column", PLACE),
    ("module_path", PLACE),
    ("include_str", STD_ONLY),
    ("include_bytes", STD_ONLY),
    ("cfg", STD_ONLY),
    ("compile_error", roles(&[R::PATHS_ONLY])),
    ("json", roles(&[R::EXPRESSION_BODY])),
];

/// True when the macro name has the role.
pub(crate) fn has(name: &str, role: Role) -> bool {
    TABLE
        .iter()
        .any(|(candidate, flags)| *candidate == name && flags & role.0 != 0)
}
