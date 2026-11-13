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
const BUILTINS: &[(Kind, &str)] = &[
    (
        Kind::Builtin,
        "cfg test ignore should_panic automatically_derived macro_export macro_use
         proc_macro proc_macro_derive proc_macro_attribute allow expect warn deny forbid
         deprecated must_use link link_name link_ordinal no_link repr crate_type no_main
         export_name link_section no_mangle used crate_name inline cold naked no_builtins
         target_feature track_caller instruction_set doc no_std no_implicit_prelude path
         recursion_limit type_length_limit panic_handler global_allocator windows_subsystem
         debugger_visualizer collapse_debuginfo feature non_exhaustive",
    ),
    (Kind::Derive, "derive"),
    (Kind::Conditional, "cfg_attr"),
    (Kind::Unsafe, "unsafe"),
];

pub(crate) fn kind(path: &Path) -> Option<Kind> {
    let name = path.get_ident()?.to_string();
    BUILTINS
        .iter()
        .find_map(|(kind, names)| names.split_whitespace().any(|n| n == name).then_some(*kind))
}

/// Tool names from the tool-attributes section of the same Rust reference.
pub(crate) fn tool(path: &Path) -> bool {
    path.segments.len() > 1
        && path.segments.first().is_some_and(|s| {
            ["clippy", "rustfmt", "diagnostic", "miri", "rust_analyzer"]
                .contains(&s.ident.to_string().as_str())
        })
}

pub(crate) fn no_tools(attrs: &[Attribute]) -> bool {
    attrs.iter().any(|attr| {
        if attr.path().is_ident("no_implicit_prelude") {
            return true;
        }
        let Meta::List(list) = &attr.meta else {
            return false;
        };
        if !attr.path().is_ident("cfg_attr") {
            return false;
        }
        let mut names = BTreeSet::new();
        crate::net::walk(list.tokens.clone(), &mut names);
        names.contains("no_implicit_prelude")
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
                "Serialize" | "Deserialize" => Some(&["serde"][..]),
                "JsonSchema" => Some(&["schemars", "serde", "validate", "garde"][..]),
                "JsonSchema_repr" => Some(&["schemars", "serde"][..]),
                "Default" => Some(&["default"][..]),
                _ => None,
            }
        })
        .flatten()
        .map(|name| (*name).to_owned())
        .collect()
}
