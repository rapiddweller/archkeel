// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The symbol table of a collection: every definition of every file with its `TSDEF` id.
//!
//! This is the API that the records of calls and references (PR 4.3a-3c) read. It holds what
//! `collect._inner_facts` builds before it makes any record: the id of each definition
//! (`ids`), the definitions that share a qualified name (`by_qualified`), the id of a definition by
//! its qualified name and position (`scope_ids`), the top-level definitions of a module
//! (`top_by_module`) and all definitions of a module (`definitions_by_module`). The entries are in
//! the order of the Python lists: files in the order that the walk parsed them, then the definitions
//! of a file by line and column. An index is an entry number, so a lookup costs one hash.

use std::collections::HashMap;

use archkeel_wire::identity::{package_of, stable_id, Part};

use crate::definitions::{Definition, DefinitionKind};
use crate::records::Pending;

/// One definition with its file, module, qualified name and `TSDEF` id.
pub struct Entry<'a> {
    pub rel: &'a str,
    pub module: &'a str,
    pub definition: &'a Definition,
    /// The qualified name of the parent definition inside the module, if it has one.
    pub parent: Option<&'a str>,
    /// `module.parent.name`, or `module.name` for a definition without a parent.
    pub qualified: String,
    pub id: String,
}

impl Entry<'_> {
    /// The qualified name of the parent definition with its module (`parent_name` of Python).
    pub fn parent_qualified(&self) -> Option<String> {
        self.parent
            .map(|parent| format!("{}.{parent}", self.module))
    }

    /// The package of the module.
    pub fn package(&self) -> &str {
        package_of(self.module)
    }
}

/// `kind.value` of `DefinitionKind`.
pub fn kind_value(kind: DefinitionKind) -> &'static str {
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

/// The definitions of all files, with the lookups of `_inner_facts`.
pub struct SymbolTable<'a> {
    /// All definitions, in the order of the Python list.
    pub entries: Vec<Entry<'a>>,
    ids: HashMap<(&'a str, i64, i64), usize>,
    by_qualified: HashMap<String, Vec<usize>>,
    /// How many of the definitions of a qualified name are a class or an interface.
    classifiers: HashMap<String, usize>,
    scope_ids: HashMap<(String, i64, i64), usize>,
    top_by_module: HashMap<&'a str, Vec<usize>>,
    by_module: HashMap<&'a str, Vec<usize>>,
}

impl<'a> SymbolTable<'a> {
    /// Build the table from the syntax that the walk kept (`records::Pending`).
    pub fn build(pending: &'a Pending) -> Self {
        let mut table = Self {
            entries: Vec::new(),
            ids: HashMap::new(),
            by_qualified: HashMap::new(),
            classifiers: HashMap::new(),
            scope_ids: HashMap::new(),
            top_by_module: HashMap::new(),
            by_module: HashMap::new(),
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
        let qualified = match parent {
            Some(parent) => format!("{module}.{parent}.{}", definition.name),
            None => format!("{module}.{}", definition.name),
        };
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
        self.ids.insert((rel, line, column), at);
        self.by_qualified
            .entry(qualified.clone())
            .or_default()
            .push(at);
        self.scope_ids.insert((qualified.clone(), line, column), at);
        let classifier = matches!(
            definition.kind,
            DefinitionKind::Class | DefinitionKind::Interface
        );
        if classifier {
            *self.classifiers.entry(qualified.clone()).or_default() += 1;
        }
        self.by_module.entry(module).or_default().push(at);
        if definition.top_level {
            self.top_by_module.entry(module).or_default().push(at);
        }
        self.entries.push(Entry {
            rel,
            module,
            definition,
            parent,
            qualified,
            id,
        });
    }

    /// `ids[(rel, line, column)]`: the entry of the definition that starts there.
    #[allow(dead_code)] // read by the records of calls and references (PR 4.3a-3c)
    pub fn at(&self, rel: &str, line: i64, column: i64) -> Option<&Entry<'a>> {
        self.ids
            .get(&(rel, line, column))
            .map(|&at| &self.entries[at])
    }

    /// `by_qualified[qualified]`: the definitions that share a qualified name, in order.
    #[allow(dead_code)] // read by the records of calls and references (PR 4.3a-3c)
    pub fn with_qualified(&self, qualified: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = self.by_qualified.get(qualified).map_or(&[], Vec::as_slice);
        found.iter().map(|&at| &self.entries[at])
    }

    /// `len(by_qualified[qualified])`, in constant time: a name with k definitions costs k, not k
    /// squared, when each of them asks.
    pub fn count(&self, qualified: &str) -> usize {
        self.by_qualified.get(qualified).map_or(0, Vec::len)
    }

    /// The definitions of a qualified name that are a class or an interface (`classifier_targets`).
    pub fn classifier_count(&self, qualified: &str) -> usize {
        self.classifiers.get(qualified).copied().unwrap_or(0)
    }

    /// `scope_ids[(qualified, line, column)]`: the definition with that name and position.
    pub fn scope(&self, qualified: &str, line: i64, column: i64) -> Option<&Entry<'a>> {
        let key = (qualified.to_owned(), line, column);
        self.scope_ids.get(&key).map(|&at| &self.entries[at])
    }

    /// `top_by_module[module]`: the top-level definitions of a module, in order.
    #[allow(dead_code)] // read by the records of calls and references (PR 4.3a-3c)
    pub fn top_level(&self, module: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = self.top_by_module.get(module).map_or(&[], Vec::as_slice);
        found.iter().map(|&at| &self.entries[at])
    }

    /// `definitions_by_module[module]`: all definitions of a module, in order.
    #[allow(dead_code)] // read by the records of calls and references (PR 4.3a-3c)
    pub fn in_module(&self, module: &str) -> impl Iterator<Item = &Entry<'a>> {
        let found: &[usize] = self.by_module.get(module).map_or(&[], Vec::as_slice);
        found.iter().map(|&at| &self.entries[at])
    }
}
