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
    Inert,
    Cfg,
    Prelude,
    Derive,
    Conditional,
    Unsafe,
}

/// Non-shadowable names: Rust 1.97 compiler/rustc_feature/src/builtin_attrs.rs, BUILTIN_ATTRIBUTES.
/// Macro names: compiler/rustc_builtin_macros/src/lib.rs, register_attr!; `derive` parses paths.
/// Sources: https://github.com/rust-lang/rust/tree/1.97.0/compiler and the reference index above.
/// `cfg` and `cfg_attr` are active, non-macro attributes; `unsafe` is attribute syntax.
const BUILTINS: &[(Kind, &str)] = &[
    (
        Kind::Inert,
        "ignore should_panic automatically_derived macro_export macro_use
         proc_macro proc_macro_derive proc_macro_attribute allow expect warn deny forbid
         deprecated must_use link link_name link_ordinal no_link repr crate_type no_main
         export_name link_section no_mangle used crate_name inline cold naked no_builtins
         target_feature track_caller instruction_set doc no_std no_implicit_prelude path
         recursion_limit type_length_limit panic_handler windows_subsystem
         debugger_visualizer collapse_debuginfo feature non_exhaustive",
    ),
    (Kind::Cfg, "cfg"),
    (
        Kind::Prelude,
        "test bench global_allocator test_case cfg_accessible cfg_eval alloc_error_handler",
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

pub(crate) fn list<T: syn::parse::Parse>(meta: &Meta) -> Option<Vec<T>> {
    let Meta::List(list) = meta else { return None };
    syn::punctuated::Punctuated::<T, Token![,]>::parse_terminated
        .parse2(list.tokens.clone())
        .ok()
        .map(|p| p.into_iter().collect())
}

/// Built-in derives can be shadowed by an imported macro. Such a name is not a proof.
/// Source: https://doc.rust-lang.org/reference/attributes/derive.html.
pub(crate) fn builtin_parts(parts: &[String], names: &BTreeSet<String>) -> bool {
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
    match parts {
        [name] => !names.contains(name),
        [root, owner, _] => {
            "std core".split_whitespace().any(|name| name == root)
                && owner == module
                && !names.contains(root)
        }
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_table_name_has_one_class() {
        let mut names = BTreeSet::new();
        let mut macros = 0;
        let mut inert = 0;
        for (kind, group) in BUILTINS {
            for name in group.split_whitespace() {
                assert!(names.insert(name), "{name}");
                macros += usize::from(matches!(kind, Kind::Prelude | Kind::Derive));
                inert += usize::from(*kind == Kind::Inert);
            }
        }
        assert_eq!((macros, inert, names.len()), (8, 46, 57));
    }
}
