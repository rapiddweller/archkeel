// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The types of the closed-binding rule (AD-1175): what a name stands for, and the project.

use std::cell::{Cell, OnceCell};
use std::collections::{HashMap, HashSet};

use super::facts::{Facts, ScopeId};
use super::scopes::build;
use super::stdlib::is_stdlib;
use crate::module::Module;

/// A module whose names are type forms or other values that are no string: the standard library
/// and `typing_extensions`. The scan can still write a string into one of its attributes.
pub(super) fn typing_style(module: &str) -> bool {
    is_stdlib(module) || module.split('.').next() == Some("typing_extensions")
}
pub(super) const BUILDERS: [&str; 3] = ["TypedDict", "NamedTuple", "make_dataclass"];
/// A name with more bindings than this is a site: each binding costs a read.
pub(super) const MAX_BINDINGS: usize = 8;
/// A string inside a string is read to this depth; so is a chain of names.
pub(super) const MAX_DEPTH: usize = 8;
/// The reads of one module; over it the rest of the module is a site.
pub(super) const BUDGET: usize = 200_000;

/// What a name or path stands for.
#[derive(Clone, PartialEq)]
pub(super) enum Entity {
    /// A type form that is no receiver: a class instance, an alias, a factory result.
    Clean,
    /// A name of a standard typing-style module (or a builtin).
    Standard(String),
    Module(String),
    Class(usize, ScopeId),
    Unknown,
}

pub(super) struct Project<'a> {
    pub(super) modules: &'a [Module],
    pub(super) by_name: HashMap<&'a str, usize>,
    pub(super) facts: Vec<OnceCell<Facts<'a>>>,
    pub(super) budget: Cell<usize>,
    /// `(module, name)` of each standard attribute that the scan writes; name `*` is any.
    pub(super) written: OnceCell<HashSet<(String, String)>>,
    /// The stores of each attribute name, in all modules: `(module, index in its list)`.
    pub(super) stores: OnceCell<HashMap<String, Vec<(usize, usize)>>>,
}

/// The names that a read is in the middle of: a cycle is not clean.
pub(super) type Active = Vec<(usize, ScopeId, String)>;

impl<'a> Project<'a> {
    pub(super) fn of(modules: &'a [Module]) -> Self {
        Self {
            modules,
            by_name: modules
                .iter()
                .enumerate()
                .map(|(at, m)| (m.name.as_str(), at))
                .collect(),
            facts: modules.iter().map(|_| OnceCell::new()).collect(),
            budget: Cell::new(0),
            written: OnceCell::new(),
            stores: OnceCell::new(),
        }
    }

    pub(super) fn facts(&self, at: usize) -> &Facts<'a> {
        self.facts[at].get_or_init(|| build(&self.modules[at]))
    }

    /// All entities agree: that one; all are clean but differ: a type form that is no receiver.
    pub(super) fn merge_all(&self, entities: impl Iterator<Item = Entity>) -> Entity {
        let all: Vec<Entity> = entities.collect();
        match all.first() {
            None => Entity::Standard(String::new()),
            Some(_) if all.contains(&Entity::Unknown) => Entity::Unknown,
            Some(first) if all.iter().all(|e| e == first) => first.clone(),
            Some(_) => Entity::Clean,
        }
    }

    /// `import m`: a module that the scan holds, or a standard one, or a prefix of one.
    pub(super) fn module(&self, name: &str) -> Entity {
        if typing_style(name) || self.by_name.contains_key(name) {
            return Entity::Module(name.to_owned());
        }
        Entity::Unknown
    }
}
