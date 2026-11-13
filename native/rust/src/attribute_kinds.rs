// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Attribute classes from https://doc.rust-lang.org/reference/attributes.html#built-in-attributes-index.
//! Unknown names stay unclassified. Custom derives are never an expansion proof.

use std::collections::BTreeSet;
use syn::parse::Parser;
use syn::{Attribute, Meta, Path, Token};

#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) enum Kind {
    Builtin,
    Derive,
    Conditional,
    Unsafe,
}

/// The one table of built-in attribute names and their interpretation.
const BUILTINS: &[(&str, Kind)] = &[
    ("cfg", Kind::Builtin),
    ("cfg_attr", Kind::Conditional),
    ("test", Kind::Builtin),
    ("ignore", Kind::Builtin),
    ("should_panic", Kind::Builtin),
    ("derive", Kind::Derive),
    ("automatically_derived", Kind::Builtin),
    ("macro_export", Kind::Builtin),
    ("macro_use", Kind::Builtin),
    ("proc_macro", Kind::Builtin),
    ("proc_macro_derive", Kind::Builtin),
    ("proc_macro_attribute", Kind::Builtin),
    ("allow", Kind::Builtin),
    ("expect", Kind::Builtin),
    ("warn", Kind::Builtin),
    ("deny", Kind::Builtin),
    ("forbid", Kind::Builtin),
    ("deprecated", Kind::Builtin),
    ("must_use", Kind::Builtin),
    ("link", Kind::Builtin),
    ("link_name", Kind::Builtin),
    ("link_ordinal", Kind::Builtin),
    ("no_link", Kind::Builtin),
    ("repr", Kind::Builtin),
    ("crate_type", Kind::Builtin),
    ("no_main", Kind::Builtin),
    ("export_name", Kind::Builtin),
    ("link_section", Kind::Builtin),
    ("no_mangle", Kind::Builtin),
    ("used", Kind::Builtin),
    ("crate_name", Kind::Builtin),
    ("inline", Kind::Builtin),
    ("cold", Kind::Builtin),
    ("naked", Kind::Builtin),
    ("no_builtins", Kind::Builtin),
    ("target_feature", Kind::Builtin),
    ("track_caller", Kind::Builtin),
    ("instruction_set", Kind::Builtin),
    ("doc", Kind::Builtin),
    ("no_std", Kind::Builtin),
    ("no_implicit_prelude", Kind::Builtin),
    ("path", Kind::Builtin),
    ("recursion_limit", Kind::Builtin),
    ("type_length_limit", Kind::Builtin),
    ("panic_handler", Kind::Builtin),
    ("global_allocator", Kind::Builtin),
    ("windows_subsystem", Kind::Builtin),
    ("debugger_visualizer", Kind::Builtin),
    ("collapse_debuginfo", Kind::Builtin),
    ("unsafe", Kind::Unsafe),
];

pub(crate) fn kind(path: &Path) -> Option<Kind> {
    let name = path.get_ident()?.to_string();
    BUILTINS
        .iter()
        .find_map(|(n, k)| (*n == name).then_some(*k))
}

/// Tool names from the tool-attributes section of the same Rust reference.
pub(crate) fn tool(path: &Path) -> bool {
    path.segments.len() > 1
        && path.segments.first().is_some_and(|s| {
            ["clippy", "rustfmt", "diagnostic", "miri", "rust_analyzer"]
                .contains(&s.ident.to_string().as_str())
        })
}

pub(crate) fn paths(meta: &Meta) -> Option<Vec<Path>> {
    let Meta::List(list) = meta else { return None };
    syn::punctuated::Punctuated::<Path, Token![,]>::parse_terminated
        .parse2(list.tokens.clone())
        .ok()
        .map(|p| p.into_iter().collect())
}

/// Built-in derives can be shadowed by an imported macro. Such a name is not a proof.
/// Source: https://doc.rust-lang.org/reference/attributes/derive.html.
pub(crate) fn builtin_derive(path: &Path, names: &BTreeSet<String>) -> bool {
    let parts: Vec<_> = path.segments.iter().map(|s| s.ident.to_string()).collect();
    let Some(last) = parts.last() else {
        return false;
    };
    let module = match last.as_str() {
        "Clone" => "clone",
        "Copy" => "marker",
        "Debug" => "fmt",
        "Default" => "default",
        "Eq" | "PartialEq" | "Ord" | "PartialOrd" => "cmp",
        "Hash" => "hash",
        _ => return false,
    };
    match parts.as_slice() {
        [name] => !names.contains(name),
        [root, owner, _] => {
            ["std", "core"].contains(&root.as_str()) && owner == module && !names.contains(root)
        }
        _ => false,
    }
}

/// Known helper registrations. A custom derive still has its own gap; these names add no expansion.
/// Sources: serde_derive and schemars_derive `proc_macro_derive(..., attributes(...))` declarations.
pub(crate) fn helpers(attrs: &[Attribute]) -> Vec<String> {
    attrs
        .iter()
        .filter(|a| a.path().is_ident("derive"))
        .filter_map(|a| paths(&a.meta))
        .flatten()
        .filter_map(|p| {
            let name = p.segments.last()?.ident.to_string();
            match name.as_str() {
                "Serialize" | "Deserialize" => Some("serde".to_owned()),
                "JsonSchema" => Some("schemars".to_owned()),
                "Default" => Some("default".to_owned()),
                _ => None,
            }
        })
        .collect()
}
