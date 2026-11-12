// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The identifier characters that `ruff_python_parser` accepts and CPython refuses (AD-334).
//!
//! ruff reads an identifier with `unicode-ident` 1.0.27 (Unicode 17). Each CPython checks it with
//! its own Unicode database: 3.11 has Unicode 14, 3.12 has 15, 3.13 has 15.1 and 3.14 has 16. A
//! table holds the code point ranges that ruff accepts and the CPython of one minor version
//! refuses: `ast.parse(chr(c) + "=1")` for a first character, `ast.parse("a" + chr(c) + "=1")` for
//! a later one, on CPython 3.11.12, 3.12.10, 3.13.15 and 3.14.7. The ranges are in
//! `identifier.txt`; `build.rs` fails the build when a line of it does not parse, so the lookup
//! below never skips a range.
//! `tests/test_collector_native_python_hostile.py` compares the ends of each range with the running
//! interpreter.

/// One range a line: `<version> <start|continue> <first> <last>` (see `identifier.txt`).
const TABLE: &str = include_str!("identifier.txt");
use archkeel_facts::pyminor::PyMinor;

/// Whether CPython 3.`minor` refuses `c` in an identifier that ruff accepts: `first` for the first
/// character of the name. Only a name with a character outside ASCII comes here.
pub fn refused(minor: PyMinor, first: bool, c: char) -> bool {
    let version = match minor {
        PyMinor::Py311 => "3.11",
        PyMinor::Py312 => "3.12",
        PyMinor::Py313 => "3.13",
        PyMinor::Py314 => "3.14",
    };
    let kind = if first { "start" } else { "continue" };
    let code = u32::from(c);
    TABLE.lines().any(|line| {
        let fields: Vec<&str> = line.split(' ').collect();
        let [found, found_kind, low, high] = fields.as_slice() else {
            return false;
        };
        let range = |field: &str| u32::from_str_radix(field, 16).ok();
        *found == version
            && *found_kind == kind
            && range(low).is_some_and(|low| low <= code)
            && range(high).is_some_and(|high| code <= high)
    })
}
