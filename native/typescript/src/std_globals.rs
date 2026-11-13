// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The names that the standard `lib` files of the pinned compiler declare (`config.standard_globals`,
//! AD-261). The catalog is the data file of the Python collector, copied into `native/` by
//! `tools/typescript_libs.py` (a test compares the copies), so both read the same names.

use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

use serde_json::{Map, Value};

use crate::options::{Options, Target};

/// The compiler supplies `undefined` itself, so no lib file declares it.
const INTRINSIC: &str = "undefined";

const CATALOG: &str = include_str!("../standard_libs.json");

/// One lib: the globals it declares and the libs that it references.
struct Lib {
    globals: Vec<String>,
    references: Vec<String>,
}

struct Catalog {
    libs: HashMap<String, Lib>,
    defaults: HashMap<String, Vec<String>>,
}

fn strings(value: Option<&Value>) -> Vec<String> {
    let items = value.and_then(Value::as_array).into_iter().flatten();
    items.filter_map(Value::as_str).map(str::to_owned).collect()
}

fn catalog() -> &'static Catalog {
    static CELL: OnceLock<Catalog> = OnceLock::new();
    CELL.get_or_init(|| {
        let data: Value = serde_json::from_str(CATALOG).unwrap_or(Value::Null);
        let object = |key: &str| -> Map<String, Value> {
            data.get(key)
                .and_then(Value::as_object)
                .cloned()
                .unwrap_or_default()
        };
        let libs = object("libs")
            .into_iter()
            .map(|(name, entry)| {
                let lib = Lib {
                    globals: strings(entry.get("globals")),
                    references: strings(entry.get("references")),
                };
                (name, lib)
            })
            .collect();
        let defaults = object("defaults")
            .into_iter()
            .map(|(name, list)| (name, strings(Some(&list))))
            .collect();
        Catalog { libs, defaults }
    })
}

/// `config._libraries`: the `lib` values in order, each once, and whether one is not a lib of the
/// pinned compiler (or the value is not a list of text).
pub(crate) fn libraries(raw: &Map<String, Value>) -> (Option<Vec<String>>, bool) {
    let Some(value) = raw.get("lib").filter(|value| !value.is_null()) else {
        return (None, false);
    };
    let Some(items) = value.as_array().filter(|a| a.iter().all(Value::is_string)) else {
        return (Some(Vec::new()), true);
    };
    let mut found: Vec<String> = Vec::new();
    let mut unsupported = false;
    for name in items.iter().filter_map(Value::as_str) {
        let name = name.to_lowercase();
        if !catalog().libs.contains_key(&name) {
            unsupported = true;
        } else if !found.contains(&name) {
            found.push(name);
        }
    }
    (Some(found), unsupported)
}

/// Read the `lib` setting into the options: the libs and whether one is unknown to the compiler.
pub(crate) fn apply(options: &mut Options, raw: &Map<String, Value>) {
    let (libs, unsupported) = libraries(raw);
    options.libs = libs;
    options.lib_unmodeled |= unsupported;
}

/// `config._default_target`: the target when none is set; ES3 counts as unset.
fn default_target(options: &Options) -> Target {
    match options.target {
        Some(target) if target != Target::Es3 => target,
        _ => options.module_default_target(),
    }
}

/// `config._closure`: the libs and every lib that they reference, however deep.
fn closure(libraries: &[String]) -> HashSet<&str> {
    let mut seen: HashSet<&str> = HashSet::new();
    let mut pending: Vec<&str> = libraries.iter().map(String::as_str).collect();
    while let Some(name) = pending.pop() {
        let Some(lib) = catalog().libs.get_key_value(name) else {
            continue;
        };
        if seen.insert(lib.0.as_str()) {
            pending.extend(lib.1.references.iter().map(String::as_str));
        }
    }
    seen
}

/// `config.standard_globals`: the names that the libs of the options declare; none where the
/// options replace the libs in a way that the catalog cannot know.
pub(crate) fn standard_globals(options: &Options) -> HashSet<String> {
    if options.no_lib || !options.unmodeled.is_empty() || options.lib_unmodeled {
        return HashSet::new();
    }
    let defaults = catalog().defaults.get(&default_target(options).name());
    let listed = options
        .libs
        .as_ref()
        .or(defaults)
        .map_or(&[][..], Vec::as_slice);
    let mut names: HashSet<String> = HashSet::from([INTRINSIC.to_owned()]);
    for name in closure(listed) {
        if let Some(lib) = catalog().libs.get(name) {
            names.extend(lib.globals.iter().cloned());
        }
    }
    names
}

#[cfg(test)]
#[path = "std_globals_tests.rs"]
mod tests;
