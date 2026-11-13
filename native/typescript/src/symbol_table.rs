// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol table of a collection: every definition of every file with its `TSDEF` id.
//!
//! This is the API that the records of calls and references (PR 4.3a-3c) read. It holds what
//! `collect._inner_facts` builds before it makes any record: the id of each definition
//! (`ids`), the definitions that share a qualified name (`by_qualified`) and the id of a definition
//! by its qualified name and position (`scope_ids`). The entries are in
//! the order of the Python lists: files in the order that the walk parsed them, then the definitions
//! of a file by line and column. An index is an entry number, so a lookup costs one hash.

use std::collections::{HashMap, HashSet};
use std::rc::Rc;

use archkeel_facts::identity::{package_of, stable_id, Part};

use crate::definitions::{Definition, DefinitionKind};
use crate::kept::Pending;

/// One definition with its file, module, qualified name and `TSDEF` id.
pub(crate) struct Entry<'a> {
    /// The place of the entry in `SymbolTable::entries`.
    pub at: usize,
    pub rel: &'a str,
    pub module: &'a str,
    pub definition: &'a Definition,
    /// The qualified name of the parent definition inside the module, if it has one.
    pub parent: Option<&'a str>,
    /// `module.parent.name`, or `module.name` for a definition without a parent.
    pub qualified: Rc<str>,
    pub id: String,
}

impl Entry<'_> {
    /// The qualified name of the parent definition with its module (`parent_name` of Python).
    pub(crate) fn parent_qualified(&self) -> Option<String> {
        self.parent
            .map(|parent| format!("{}.{parent}", self.module))
    }

    /// The package of the module.
    pub(crate) fn package(&self) -> &str {
        package_of(self.module)
    }
}

/// `kind.value` of `DefinitionKind`.
pub(crate) fn kind_value(kind: DefinitionKind) -> &'static str {
    match kind {
        DefinitionKind::Class => "class",
        DefinitionKind::Interface => "interface",
        DefinitionKind::Enum => "enum",
        DefinitionKind::Method => "method",
        DefinitionKind::Function => "function",
        DefinitionKind::TypeAlias => "type_alias",
        DefinitionKind::Constant => "constant",
    }
}

type ByName = HashMap<String, HashMap<String, Vec<usize>>>;

fn push_named(index: &mut ByName, module: &str, name: &str, at: usize) {
    index
        .entry(module.to_owned())
        .or_default()
        .entry(name.to_owned())
        .or_default()
        .push(at);
}

/// A lookup by module and name without a new string: the maps are nested for that.
fn lookup<'m>(index: &'m ByName, module: &str, name: &str) -> &'m [usize] {
    index
        .get(module)
        .and_then(|names| names.get(name))
        .map_or(&[], Vec::as_slice)
}

/// The definitions of all files, with the lookups of `_inner_facts`.
pub(crate) struct SymbolTable<'a> {
    /// All definitions, in the order of the Python list.
    pub entries: Vec<Entry<'a>>,
    ids: HashMap<(&'a str, i64, i64), usize>,
    by_qualified: HashMap<Rc<str>, Vec<usize>>,
    /// How many of the definitions of a qualified name are a class or an interface.
    classifiers: HashMap<Rc<str>, usize>,
    classes: HashMap<Rc<str>, usize>,
    top_named: HashMap<String, HashMap<String, Vec<usize>>>,
    named: HashMap<String, HashMap<String, Vec<usize>>>,
    members: HashMap<usize, HashSet<&'a str>>,
    scope_ids: HashMap<Rc<str>, HashMap<(i64, i64), usize>>,
}

impl<'a> SymbolTable<'a> {
    /// Build the table from the syntax that the walk kept (`records::Pending`).
    pub(crate) fn build(pending: &'a Pending) -> Self {
        let mut table = Self {
            entries: Vec::new(),
            ids: HashMap::new(),
            by_qualified: HashMap::new(),
            classifiers: HashMap::new(),
            classes: HashMap::new(),
            top_named: HashMap::new(),
            named: HashMap::new(),
            members: HashMap::new(),
            scope_ids: HashMap::new(),
        };
        for rel in &pending.order {
            let Some(kept) = pending.kept.get(rel) else {
                continue;
            };
            for (definition, parent) in &kept.definitions {
                table.add(rel, &kept.module, definition, parent.as_deref());
            }
        }
        table
    }

    /// Add one definition: its qualified name, its id and its place in each index.
    fn add(
        &mut self,
        rel: &'a str,
        module: &'a str,
        definition: &'a Definition,
        parent: Option<&'a str>,
    ) {
        // One copy of the name: the indexes and the entry share it, and a deep nest has names as
        // long as its depth.
        let qualified: Rc<str> = match parent {
            Some(parent) => format!("{module}.{parent}.{}", definition.name),
            None => format!("{module}.{}", definition.name),
        }
        .into();
        let (line, column) = (definition.span.line, definition.span.column);
        let parts = [
            Part::Text(rel),
            Part::Number(line),
            Part::Number(column),
            Part::Text(&qualified),
            Part::Text(kind_value(definition.kind)),
        ];
        let id = stable_id("TSDEF", &parts);
        let at = self.entries.len();
        let previous = self.ids.insert((rel, line, column), at);
        // Python keeps the last definition of a position; two of them would hide one id.
        debug_assert!(
            previous.is_none(),
            "two definitions at {rel}:{line}:{column}"
        );
        self.by_qualified
            .entry(Rc::clone(&qualified))
            .or_default()
            .push(at);
        self.scope_ids
            .entry(Rc::clone(&qualified))
            .or_default()
            .insert((line, column), at);
        let classifier = matches!(
            definition.kind,
            DefinitionKind::Class | DefinitionKind::Interface
        );
        if classifier {
            *self.classifiers.entry(Rc::clone(&qualified)).or_default() += 1;
        }
        if definition.kind == DefinitionKind::Class {
            *self.classes.entry(Rc::clone(&qualified)).or_default() += 1;
        }
        if classifier {
            let names = definition.members.iter().map(|member| member.name.as_str());
            self.members.insert(at, names.collect());
        }
        let name = definition.name.as_str();
        push_named(&mut self.named, module, name, at);
        if definition.top_level {
            push_named(&mut self.top_named, module, name, at);
        }
        self.entries.push(Entry {
            at,
            rel,
            module,
            definition,
            parent,
            qualified,
            id,
        });
    }

    /// `by_qualified[qualified]`: the definitions that share a qualified name, in order.
    pub(crate) fn with_qualified(&self, qualified: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = self.by_qualified.get(qualified).map_or(&[], Vec::as_slice);
        found.iter().map(|&at| &self.entries[at])
    }

    /// `len(by_qualified[qualified])`, in constant time: a name with k definitions costs k, not k
    /// squared, when each of them asks.
    pub(crate) fn count(&self, qualified: &str) -> usize {
        self.by_qualified.get(qualified).map_or(0, Vec::len)
    }

    /// The definitions of a qualified name that are a class or an interface (`classifier_targets`).
    pub(crate) fn classifier_count(&self, qualified: &str) -> usize {
        self.classifiers.get(qualified).copied().unwrap_or(0)
    }

    /// The definitions of a qualified name that are a class (`DefinitionKind::Class`).
    pub(crate) fn class_count(&self, qualified: &str) -> usize {
        self.classes.get(qualified).copied().unwrap_or(0)
    }

    /// The top-level definitions of a module with this name, in order (index `top_named`).
    pub(crate) fn top_named(&self, module: &str, name: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = lookup(&self.top_named, module, name);
        found.iter().map(|&at| &self.entries[at])
    }

    /// The definitions of a module with this name, in order (index `named`).
    pub(crate) fn named_in(&self, module: &str, name: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = lookup(&self.named, module, name);
        found.iter().map(|&at| &self.entries[at])
    }

    /// Whether a class or an interface declares a member of this name.
    pub(crate) fn has_member(&self, entry: &Entry, name: &str) -> bool {
        self.members
            .get(&entry.at)
            .is_some_and(|names| names.contains(name))
    }

    /// `scope_ids[(qualified, line, column)]`: the definition with that name and position.
    pub(crate) fn scope(&self, qualified: &str, line: i64, column: i64) -> Option<&Entry<'a>> {
        let at = self.scope_ids.get(qualified)?.get(&(line, column))?;
        self.entries.get(*at)
    }
}
