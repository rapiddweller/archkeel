// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the driver gathers while rustc builds the MIR of each body (AD-1047).
//!
//! Everything is added to sets of ids of the string table. The driver keeps one entry for each
//! module, not one for each function: the sets are what the model reads, and this keeps the file small.

use crate::names::Names;
use rustc_hir::def_id::DefId;
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};
use std::sync::{LazyLock, Mutex, MutexGuard};

/// The type reach of the bodies of one module.
pub(crate) struct Module {
    pub(crate) file: u32,
    /// ADTs in the types of locals, calls, signatures, casts and constants.
    pub(crate) mentions: BTreeSet<u32>,
    /// `dyn` principal traits in those types.
    pub(crate) dyns: BTreeSet<u32>,
    pub(crate) opaques: BTreeSet<u32>,
    /// `dyn` principal traits in the arguments and results of calls.
    pub(crate) dyn_in: BTreeSet<u32>,
    /// A type of the bodies holds a raw pointer to `()` or `c_void`.
    pub(crate) erased: bool,
}

/// A function whose generics make its instantiation matter. The reader folds the call edges over it.
/// The bodies of its closures are part of it.
pub(crate) struct GenericFn {
    pub(crate) module: u32,
    /// The trait item that this function implements.
    pub(crate) implements: Option<u32>,
}

/// Source types of the unsize casts to one `dyn` trait.
pub(crate) struct Coerced {
    pub(crate) adts: BTreeSet<u32>,
    /// `dyn` traits of the source of the cast: trait upcasting keeps what was coerced to them.
    pub(crate) dyns: BTreeSet<u32>,
    /// Generic bodies that cast a value of a type parameter (hole H1): the reader uses their instances.
    pub(crate) param_in: BTreeSet<u32>,
    /// Opaque types (coroutines) of the source: the hidden types of a `dyn Future` made from an async block.
    pub(crate) opaques: BTreeSet<u32>,
}

/// One call of `PartialEq::eq` that the compiler resolved to the `eq` of a workspace impl (AD-1136).
#[derive(PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Selected {
    /// The module of the body that makes the call.
    pub(crate) from: u32,
    /// The module of the selected impl.
    pub(crate) to: u32,
    /// The selected `eq` of the impl.
    pub(crate) imp: u32,
    /// The file of the call, relative to the root.
    pub(crate) file: u32,
    /// The file that holds the selected `eq`: the reader maps modules by name, and this file proves the mapping.
    pub(crate) impl_file: u32,
    /// The line of the call (1-based) and its column (0-based).
    pub(crate) line: u32,
    pub(crate) column: u32,
}

/// The types that flow into a generic function: ADTs, and the `dyn` traits of its type arguments
/// (`show::<Box<dyn Debug>>`): the instance can call a method of any implementer.
#[derive(Default)]
pub(crate) struct Flow {
    pub(crate) adts: BTreeSet<u32>,
    pub(crate) dyns: BTreeSet<u32>,
    /// A type argument holds a type parameter of the calling function: its instances flow too.
    pub(crate) param: bool,
}

/// What the body of a coroutine holds: it stands in for the witness types of its future.
pub(crate) struct Hidden {
    pub(crate) adts: BTreeSet<u32>,
    pub(crate) dyns: BTreeSet<u32>,
    pub(crate) opaques: BTreeSet<u32>,
}

pub(crate) struct State {
    pub(crate) coroutines: BTreeMap<u32, Hidden>,
    pub(crate) names: Names,
    pub(crate) modules: BTreeMap<u32, Module>,
    pub(crate) fns: BTreeMap<u32, GenericFn>,
    /// Type arguments that a non-generic body passes to a generic callee.
    pub(crate) seeds: BTreeMap<u32, Flow>,
    /// Type arguments that a generic body passes to a generic callee.
    pub(crate) edges: BTreeMap<(u32, u32), Flow>,
    pub(crate) coerce: BTreeMap<u32, Coerced>,
    /// What a cast erases: the ADTs and `dyn` traits behind a pointer that a cast gives another type.
    pub(crate) cast_lost: Flow,
    /// For each ADT in the signature of a call outside the workspace (and the key `<ptr>` for a signature with
    /// a raw pointer to `()`): the types that the call takes in its type arguments.
    pub(crate) via: BTreeMap<u32, Flow>,
    /// The ADTs that hold a raw pointer to `()` or `c_void` in a field, of any crate.
    pub(crate) erased_adts: BTreeSet<u32>,
    /// The ADTs in the fields of each ADT: an ADT that holds an erasing ADT erases too.
    pub(crate) adt_fields: BTreeMap<u32, BTreeSet<u32>>,
    pub(crate) opaque_defs: HashSet<DefId>,
    /// The calls of `PartialEq::eq` with a selected workspace impl.
    pub(crate) selected: BTreeSet<Selected>,
    pub(crate) workspace_defs: HashMap<DefId, bool>,
    /// The canonical workspace root, with a closing slash.
    pub(crate) root: String,
    /// The directory where each verified member run registers its crate id: a crate without an entry is foreign.
    pub(crate) registry: String,
}

static STATE: LazyLock<Mutex<State>> = LazyLock::new(|| {
    Mutex::new(State {
        coroutines: BTreeMap::new(),
        names: Names::new(),
        modules: BTreeMap::new(),
        fns: BTreeMap::new(),
        seeds: BTreeMap::new(),
        edges: BTreeMap::new(),
        coerce: BTreeMap::new(),
        cast_lost: Flow::default(),
        via: BTreeMap::new(),
        erased_adts: BTreeSet::new(),
        adt_fields: BTreeMap::new(),
        opaque_defs: HashSet::new(),
        selected: BTreeSet::new(),
        workspace_defs: HashMap::new(),
        root: String::new(),
        registry: String::new(),
    })
});

/// The one state of this compiler run. rustc calls the provider hook one body at a time.
pub(crate) fn lock() -> MutexGuard<'static, State> {
    STATE.lock().unwrap_or_else(|e| e.into_inner())
}
