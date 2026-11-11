// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Record the provenance of the binary when it is built (`archkeel-build-support`), and check the
//! identifier ranges of `src/identifier.txt` that `src/identifier.rs` reads at run time.

use std::collections::BTreeMap;

const TABLES: [&str; 8] = [
    "3.11 start",
    "3.11 continue",
    "3.12 start",
    "3.12 continue",
    "3.13 start",
    "3.13 continue",
    "3.14 start",
    "3.14 continue",
];

fn main() -> Result<(), String> {
    archkeel_build_support::emit();
    identifier_ranges()
}

/// A line that does not parse, a range out of order or a missing table fails the build, so the
/// lookup at run time cannot skip a range.
fn identifier_ranges() -> Result<(), String> {
    let text = std::fs::read_to_string("src/identifier.txt")
        .map_err(|error| format!("cannot read src/identifier.txt: {error}"))?;
    let mut tables: BTreeMap<String, Vec<(u32, u32)>> = BTreeMap::new();
    for line in text
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
    {
        let fields: Vec<&str> = line.split(' ').collect();
        let [version, kind, low, high] = fields.as_slice() else {
            return Err(format!("identifier.txt: not four fields: {line}"));
        };
        let code = |field: &str| {
            u32::from_str_radix(field, 16).map_err(|_| format!("identifier.txt: {line}"))
        };
        let (low, high) = (code(low)?, code(high)?);
        let name = format!("{version} {kind}");
        let table = tables.entry(name).or_default();
        if low > high || table.last().is_some_and(|last| last.1 >= low) {
            return Err(format!("identifier.txt: a range out of order: {line}"));
        }
        table.push((low, high));
    }
    for name in TABLES {
        if tables.remove(name).is_none() {
            return Err(format!("identifier.txt: no table {name}"));
        }
    }
    match tables.keys().next() {
        Some(name) => Err(format!("identifier.txt: an unknown table {name}")),
        None => Ok(()),
    }
}
