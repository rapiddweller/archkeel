// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The receiver types of the resolver and the std types that it knows (#1571, AD-786). A path
//! names a std type only when the prelude or one `use` leaf of `std`, `core` or `alloc` binds its
//! first segment for certain: no item, glob or module-level macro of the file can give the name,
//! and a `use` leaf is unconditional and in the scope of the path.
//!
//! The method table holds inherent methods of std types and the `Iterator` methods of the fixed
//! adapters, with the return type and the `self` form of their std signature. Rust tries each
//! step of the receiver (by value, `&`, `&mut`, then the deref target) and, at each step, an
//! inherent method before a trait method. So a method counts for certain only at the first step:
//! the receiver has the `self` form of the method, and the method is of the receiver's own type.
//! A method of a later step (an autoref or a deref target: `[T]` of `Vec<T>`, `str` of `String`,
//! `Path` of `PathBuf`) counts only when the file can have no trait of a dependency in scope
//! (`closed`, `impl_scope.rs`) and no trait of the prelude has the name; the caller checks the
//! traits of the workspace.

use crate::definitions::SelfKind;
use crate::modules::Frame;
use crate::scan::Via;

/// A std type that the resolver knows.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(in crate::impl_edges) enum Std {
    Str,
    String,
    /// `bool`, `char`, an integer or a float.
    Prim,
    Vec,
    Slice,
    Option,
    Result,
    Box,
    Rc,
    Arc,
    /// `HashMap<K, V>` or `BTreeMap<K, V>`.
    Map,
    /// `HashSet<T>` or `BTreeSet<T>`.
    Set,
    Deque,
    Path,
    PathBuf,
    OsStr,
    OsString,
    /// A std iterator with its item, from the fixed adapters of AD-786.
    Iter,
}

/// A receiver type as far as the written types prove it.
#[derive(Clone, Debug, PartialEq)]
pub(in crate::impl_edges) enum Ty {
    /// An exact struct or enum of the workspace: its lexical module and its name.
    Own(String, String),
    Std(Std, Vec<Ty>),
    Ref(SelfKind, Box<Ty>),
    Unknown,
}

const PRIMITIVES: [&str; 17] = [
    "bool", "char", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64", "i128",
    "isize", "f32", "f64", "str",
];

/// The methods of the traits of the prelude that a std type of this table implements, and the
/// conversions: a deref target loses against them.
const PRELUDE: [&str; 14] = [
    "clone",
    "as_ref",
    "as_mut",
    "into",
    "try_into",
    "into_iter",
    "to_owned",
    "to_string",
    "eq",
    "ne",
    "cmp",
    "partial_cmp",
    "extend",
    "borrow",
];

/// The std type that a written path names for certain.
pub(in crate::impl_edges) fn std_path(
    frame: &Frame<'_>,
    scope: &[String],
    names: &[String],
) -> Option<Std> {
    let module = frame.module;
    let scan = &module.scan;
    if module.gated && module.gates.is_none() {
        return None;
    }
    let first = names.first()?;
    let full: Vec<&str> = match frame.bound(first) {
        [] => {
            if scan.counts.contains_key(first.as_str())
                || scan.module_macros
                || frame.globs().next().is_some()
            {
                return None;
            }
            if let [one] = names {
                return prelude(one);
            }
            names.iter().map(String::as_str).collect()
        }
        [leaf] => {
            if scan.counts.get(first.as_str()) != Some(&1)
                || scan.conditional_bindings.contains(first.as_str())
                || !matches!(leaf.via, Via::Use { block: false, .. })
                || frame.lexical_at(scope) != frame.lexical_at(&leaf.scope)
            {
                return None;
            }
            let rest = names[1..].iter();
            leaf.names.iter().chain(rest).map(String::as_str).collect()
        }
        _ => return None,
    };
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

/// The type of an associated function `T::f(..)` of a std type: a constructor gives the type.
pub(in crate::impl_edges) fn std_function(std: Std, name: &str) -> Ty {
    match (std, name) {
        (Std::Path | Std::OsStr, "new") => {
            Ty::Ref(SelfKind::Shared, Box::new(Ty::Std(std, vec![])))
        }
        (Std::Str | Std::Slice | Std::Prim, _) => Ty::Unknown,
        (_, "new" | "with_capacity" | "default" | "from") => Ty::Std(std, vec![]),
        _ => Ty::Unknown,
    }
}

/// The item of `into_iter()` or of a `for` loop on a std receiver: `&T` and `&mut T` through a
/// reference, `T` from a value. An array by value is left out: its item depends on the edition.
fn items(ty: &Ty) -> Ty {
    let item = |args: &[Ty]| args.first().cloned().unwrap_or(Ty::Unknown);
    match ty {
        Ty::Std(Std::Iter, args) => item(args),
        Ty::Std(Std::Vec | Std::Set | Std::Deque | Std::Option, args) => item(args),
        Ty::Ref(kind, inner) => match (kind, &**inner) {
            (SelfKind::Unique, Ty::Std(Std::Iter, args)) => item(args),
            (_, Ty::Std(Std::Vec | Std::Slice | Std::Deque | Std::Option, args)) => {
                Ty::Ref(*kind, Box::new(item(args)))
            }
            (SelfKind::Shared, Ty::Std(Std::Set, args)) => shared(item(args)),
            _ => Ty::Unknown,
        },
        _ => Ty::Unknown,
    }
}

/// The type of the closure parameter of an adapter of AD-786 on a receiver of type `ty`, or of the
/// variable of `for` (the adapter `for`). A predicate (`filter`, `find`, ..) sees `&Item`. `for`
/// calls `IntoIterator::into_iter` by its path, with no method lookup. An adapter counts for certain
/// on an iterator or an `Option` by value when it takes `self`; else only in a `closed` file.
pub(in crate::impl_edges) fn element(ty: &Ty, adapter: &str, closed: bool) -> Ty {
    if adapter == "for" {
        return items(ty);
    }
    let autoref = matches!(adapter, "find" | "any" | "all" | "position");
    if !closed && (autoref || matches!(ty, Ty::Ref(..))) {
        return Ty::Unknown;
    }
    let mut ty = ty;
    while let Ty::Ref(_, inner) = ty {
        ty = inner;
    }
    let first = |args: &[Ty]| args.first().cloned().unwrap_or(Ty::Unknown);
    let item = match (ty, adapter) {
        (Ty::Std(Std::Iter, args), _) => first(args),
        (Ty::Std(Std::Option, args), "map") => return first(args),
        (Ty::Std(Std::Option, args), "filter") => return shared(first(args)),
        _ => return Ty::Unknown,
    };
    match (item, adapter) {
        (Ty::Unknown, _) => Ty::Unknown,
        (item, "filter" | "find" | "take_while" | "skip_while" | "max_by_key" | "min_by_key") => {
            shared(item)
        }
        (item, _) => item,
    }
}

/// The `self` form of a method of the table.
fn self_kind(kind: Std, name: &str) -> SelfKind {
    match (kind, name) {
        (Std::Iter, "find" | "nth" | "next" | "any" | "all" | "position") => SelfKind::Unique,
        (Std::Iter, _) => SelfKind::Value,
        (
            _,
            "unwrap" | "unwrap_or_default" | "expect" | "unwrap_or" | "unwrap_or_else" | "cloned"
            | "copied" | "ok_or" | "ok_or_else" | "ok" | "err" | "map_err" | "filter",
        ) => SelfKind::Value,
        (
            _,
            "as_mut" | "take" | "pop" | "first_mut" | "last_mut" | "iter_mut" | "get_mut"
            | "remove" | "insert" | "values_mut",
        ) => SelfKind::Unique,
        _ => SelfKind::Shared,
    }
}

/// The type of a method call on a std receiver (see the module notes), and `into_iter` by the
/// form of the receiver: `IntoIterator` is implemented for the receiver type itself.
pub(in crate::impl_edges) fn std_method(ty: &Ty, name: &str, arity: usize, closed: bool) -> Ty {
    if (name, arity) == ("into_iter", 0) {
        return match items(ty) {
            Ty::Unknown => Ty::Unknown,
            item => Ty::Std(Std::Iter, vec![item]),
        };
    }
    let (form, mut current) = match ty {
        Ty::Ref(kind, inner) if !matches!(**inner, Ty::Ref(..)) => (Some(*kind), &**inner),
        Ty::Ref(..) => (None, ty),
        other => (Some(SelfKind::Value), other),
    };
    while let Ty::Ref(_, inner) = current {
        current = inner;
    }
    let mut current = current.clone();
    let mut first = true;
    let prelude: &[&str] = &PRELUDE;
    loop {
        let Ty::Std(kind, args) = &current else {
            return Ty::Unknown;
        };
        if let Some(found) = inherent(*kind, args, name, arity) {
            let certain = first && form == Some(self_kind(*kind, name));
            return if certain || closed {
                found
            } else {
                Ty::Unknown
            };
        }
        if prelude.contains(&name) || !closed {
            return Ty::Unknown;
        }
        first = false;
        current = match kind {
            Std::Vec => Ty::Std(Std::Slice, args.clone()),
            Std::String => Ty::Std(Std::Str, vec![]),
            Std::PathBuf => Ty::Std(Std::Path, vec![]),
            Std::OsString => Ty::Std(Std::OsStr, vec![]),
            _ => return Ty::Unknown,
        };
    }
}

fn shared(ty: Ty) -> Ty {
    Ty::Ref(SelfKind::Shared, Box::new(ty))
}

fn unique(ty: Ty) -> Ty {
    Ty::Ref(SelfKind::Unique, Box::new(ty))
}

fn of(std: Std, args: Vec<Ty>) -> Ty {
    Ty::Std(std, args)
}

/// The inherent methods of the table, with the return type of their std signature. `Unknown` is a
/// known method whose type the table does not follow.
fn inherent(kind: Std, args: &[Ty], name: &str, arity: usize) -> Option<Ty> {
    use Std::{Deque, Iter, Map, OsStr, Path, PathBuf, Result, Set, Slice, Str, Vec};
    let arg = |at: usize| args.get(at).cloned().unwrap_or(Ty::Unknown);
    let prim = || of(Std::Prim, vec![]);
    let text = || shared(of(Str, vec![]));
    let some = |ty: Ty| of(Std::Option, vec![ty]);
    let sized = matches!(kind, Vec | Slice | Str | Std::String | Map | Set | Deque);
    Some(match (kind, name, arity) {
        (_, "len" | "is_empty", 0) if sized => prim(),
        (Std::Option, "unwrap" | "unwrap_or_default", 0) => arg(0),
        (Std::Option, "expect" | "unwrap_or" | "unwrap_or_else", 1) => arg(0),
        (Std::Option, "as_ref", 0) => some(shared(arg(0))),
        (Std::Option, "as_mut", 0) => some(unique(arg(0))),
        (Std::Option, "take", 0) => some(arg(0)),
        (Std::Option, "is_some" | "is_none", 0) => prim(),
        (Std::Option, "cloned" | "copied", 0) => match arg(0) {
            Ty::Ref(_, inner) => some(*inner),
            _ => Ty::Unknown,
        },
        (Std::Option, "ok_or" | "ok_or_else", 1) => of(Result, vec![arg(0), Ty::Unknown]),
        (Result, "unwrap" | "unwrap_or_default", 0) => arg(0),
        (Result, "expect" | "unwrap_or" | "unwrap_or_else", 1) => arg(0),
        (Result, "ok", 0) => some(arg(0)),
        (Result, "err", 0) => some(arg(1)),
        (Result, "as_ref", 0) => of(Result, vec![shared(arg(0)), shared(arg(1))]),
        (Result, "is_ok" | "is_err", 0) => prim(),
        (Result, "map_err", 1) => of(Result, vec![arg(0), Ty::Unknown]),
        (Vec, "as_slice", 0) => shared(of(Slice, vec![arg(0)])),
        (Vec, "pop", 0) => some(arg(0)),
        (Slice, "first" | "last", 0) => some(shared(arg(0))),
        (Slice, "first_mut" | "last_mut", 0) => some(unique(arg(0))),
        (Slice, "contains" | "starts_with" | "ends_with", 1) => prim(),
        (Slice, "to_vec", 0) => of(Vec, vec![arg(0)]),
        (Std::String, "as_str", 0) => text(),
        (Std::String | Str, "as_bytes", 0) => shared(of(Slice, vec![prim()])),
        (Str, "trim" | "trim_start" | "trim_end", 0) => text(),
        (Str, "to_lowercase" | "to_uppercase", 0) => of(Std::String, vec![]),
        (Str, "to_ascii_lowercase" | "to_ascii_uppercase", 0) => of(Std::String, vec![]),
        (Str, "starts_with" | "ends_with" | "contains", 1) => prim(),
        (Str, "strip_prefix" | "strip_suffix", 1) => some(text()),
        (Map, "get", 1) => some(shared(arg(1))),
        (Map, "get_mut", 1) => some(unique(arg(1))),
        (Map, "remove", 1) => some(arg(1)),
        (Map, "insert", 2) => some(arg(1)),
        (Map, "contains_key", 1) | (Set, "contains", 1) => prim(),
        (PathBuf, "as_path", 0) => shared(of(Path, vec![])),
        (Path, "parent", 0) => some(shared(of(Path, vec![]))),
        (Path, "join", 1) | (Path, "to_path_buf", 0) => of(PathBuf, vec![]),
        (Path, "exists" | "is_dir" | "is_file" | "is_absolute" | "is_relative", 0) => prim(),
        (Path, "starts_with" | "ends_with", 1) => prim(),
        (Path, "file_name" | "extension" | "file_stem", 0) => some(shared(of(OsStr, vec![]))),
        (Path | OsStr, "to_str", 0) => some(text()),
        (Slice | Set | Deque | Std::Option, "iter", 0) => of(Iter, vec![shared(arg(0))]),
        (Slice | Deque | Std::Option, "iter_mut", 0) => of(Iter, vec![unique(arg(0))]),
        (Map, "keys", 0) => of(Iter, vec![shared(arg(0))]),
        (Map, "values", 0) => of(Iter, vec![shared(arg(1))]),
        (Map, "values_mut", 0) => of(Iter, vec![unique(arg(1))]),
        (Std::Option, "filter", 1) => some(arg(0)),
        (Iter, "filter" | "take_while" | "skip_while", 1) => of(Iter, args.to_vec()),
        (Iter, "find" | "max_by_key" | "min_by_key" | "nth", 1) => some(arg(0)),
        (Iter, "next" | "last", 0) => some(arg(0)),
        (Iter, "any" | "all", 1) | (Iter, "count", 0) => prim(),
        (Iter, "position", 1) => some(prim()),
        _ => return None,
    })
}
