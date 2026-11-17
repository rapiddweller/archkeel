// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The std and outside types that a written path names (#1571, AD-804). A path names a std type
//! only when the prelude or one `use` leaf of `std`, `core` or `alloc` binds its first segment for
//! certain: no item, glob or module-level macro of the file can give the name, and a `use` leaf is
//! unconditional and in the scope of the path. It names an outside type when its first segment is
//! a dependency that the manifest takes from a registry or git.

use super::ty::Std;
use crate::modules::Frame;
use crate::scan::Via;

const PRIMITIVES: [&str; 17] = [
    "bool", "char", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64", "i128",
    "isize", "f32", "f64", "str",
];

/// A written path from the root of its crate: the path itself when nothing of the file binds its
/// first name, or the path of the one unconditional `use` leaf in its scope that binds it.
/// `None` when an item, a glob or a module-level macro of the file can give the first name.
fn rooted(frame: &Frame<'_>, scope: &[String], names: &[String]) -> Option<Rooted> {
    let module = frame.module;
    let scan = &module.scan;
    if module.gated && module.gates.is_none() {
        return None;
    }
    let first = names.first()?;
    match frame.bound(first) {
        [] => {
            let unbound = scan.counts.contains_key(&**first)
                || scan.module_macros
                || frame.globs().next().is_some();
            (!unbound).then(|| Rooted::Written(names.to_vec()))
        }
        [leaf] => {
            let unsure = scan.counts.get(&**first) != Some(&1)
                || scan.conditional_bindings.contains(&**first)
                || !matches!(leaf.via, Via::Use { block: false, .. })
                || frame.lexical_at(scope) != frame.lexical_at(&leaf.scope);
            let full = leaf.names.iter().chain(&names[1..]).cloned();
            (!unsure).then(|| Rooted::Leaf(full.collect(), leaf.absolute))
        }
        _ => None,
    }
}

/// A rooted path: as written, or through a `use` leaf (with its leading `::`).
enum Rooted {
    Written(Vec<String>),
    Leaf(Vec<String>, bool),
}

/// Whether a written path names a type of a crate that the manifest takes from a registry or git
/// for certain. Such a crate cannot depend on a crate of this workspace: no member and no `Deref`
/// of its types leads to an inherent member of the workspace (#1571, AD-804).
pub(super) fn outside_path(frame: &Frame<'_>, scope: &[String], names: &[String]) -> bool {
    let scan = &frame.module.scan;
    let (full, root_free) = match rooted(frame, scope, names) {
        Some(Rooted::Written(full)) => (full, true),
        Some(Rooted::Leaf(full, absolute)) => {
            let root = full.first().map_or("", String::as_str);
            let free =
                absolute || (frame.bound(root).is_empty() && !scan.counts.contains_key(root));
            (full, free)
        }
        None => return false,
    };
    let manifest = &frame.krate().manifest;
    match full.as_slice() {
        [root, _, ..] if root_free && scan.extern_crates.is_empty() => {
            let ours = matches!(
                &**root,
                "std" | "core" | "alloc" | "crate" | "self" | "super"
            );
            !ours && (manifest.dependencies.get(root)).is_some_and(|p| manifest.remote.contains(p))
        }
        _ => false,
    }
}

/// The std type that a written path names for certain.
pub(super) fn std_path(frame: &Frame<'_>, scope: &[String], names: &[String]) -> Option<Std> {
    let full = match rooted(frame, scope, names)? {
        Rooted::Written(full) if matches!(&full[..], [_]) => return prelude(&full[0]),
        Rooted::Written(full) | Rooted::Leaf(full, _) => full,
    };
    let full: Vec<&str> = full.iter().map(String::as_str).collect();
    let [root, rest @ ..] = full.as_slice() else {
        return None;
    };
    if !matches!(*root, "std" | "core" | "alloc") {
        return None;
    }
    Some(match rest {
        ["string", "String"] => Std::String,
        ["vec", "Vec"] => Std::Vec,
        ["option", "Option"] => Std::Option,
        ["result", "Result"] => Std::Result,
        ["boxed", "Box"] => Std::Box,
        ["rc", "Rc"] => Std::Rc,
        ["sync", "Arc"] => Std::Arc,
        ["collections", "HashMap" | "BTreeMap"]
        | ["collections", "hash_map", "HashMap"]
        | ["collections", "btree_map", "BTreeMap"] => Std::Map,
        ["collections", "HashSet" | "BTreeSet"]
        | ["collections", "hash_set", "HashSet"]
        | ["collections", "btree_set", "BTreeSet"] => Std::Set,
        ["collections", "VecDeque"] | ["collections", "vec_deque", "VecDeque"] => Std::Deque,
        ["path", "Path"] => Std::Path,
        ["path", "PathBuf"] => Std::PathBuf,
        ["ffi", "OsStr"] => Std::OsStr,
        ["ffi", "OsString"] => Std::OsString,
        _ => return None,
    })
}

/// A name of the prelude or a primitive type, when nothing of the file binds it.
fn prelude(name: &str) -> Option<Std> {
    let primitives: &[&str] = &PRIMITIVES;
    Some(match name {
        "String" => Std::String,
        "Vec" => Std::Vec,
        "Option" => Std::Option,
        "Result" => Std::Result,
        "Box" => Std::Box,
        "str" => Std::Str,
        other if primitives.contains(&other) => Std::Prim,
        _ => return None,
    })
}
