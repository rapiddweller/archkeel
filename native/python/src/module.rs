// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! One parsed module and the evidence of its source locations (`source.ParsedModule`).
//!
//! A location is `source.location` of a statement: the line, the end line and the column in
//! UTF-8 bytes, as CPython counts them. The excerpt is `_excerpt`, and the evidence of the file
//! itself is `source_records.file_evidence`.

use std::collections::BTreeMap;

use archkeel_facts::envelope::Evidence;
use archkeel_facts::identity::evidence_id;
use ruff_python_ast::{Alias, ModModule, Stmt};
use ruff_text_size::Ranged;

#[path = "definition.rs"]
#[cfg(any(test, feature = "dump"))]
pub(crate) mod definition;

use crate::names::package_for;
use crate::source::Lines;

#[path = "namespace_tables.rs"]
pub(crate) mod namespace_tables;

pub(crate) struct Module {
    pub rel: String,
    pub name: String,
    pub package: String,
    text: String,
    lines: Lines,
    pub tree: ModModule,
}

/// The evidence of a scan by its id, sorted as the Python collector sorts it.
pub(crate) type EvidenceMap = BTreeMap<String, Evidence>;

#[cfg(any(test, feature = "dump"))]
pub(crate) fn direct(module: &Module, node: &impl Ranged) -> bool {
    module
        .tree
        .body
        .binary_search_by_key(&node.start(), Ranged::start)
        .is_ok()
}

/// `source._import_bindings`: the names that one import statement binds.
pub(crate) fn import_bindings(statement: &Stmt) -> Vec<String> {
    let (names, dotted) = match statement {
        Stmt::Import(node) => (&node.names, true),
        Stmt::ImportFrom(node) => (&node.names, false),
        _ => return Vec::new(),
    };
    names
        .iter()
        .filter(|alias| alias.name.as_str() != "*")
        .map(|alias| alias_binding(alias, dotted))
        .collect()
}

fn alias_binding(alias: &Alias, dotted: bool) -> String {
    match &alias.asname {
        Some(asname) => asname.id.to_string(),
        None if dotted => first_part(alias.name.as_str()).to_owned(),
        None => alias.name.id.to_string(),
    }
}

pub(crate) fn first_part(dotted: &str) -> &str {
    dotted.split('.').next().unwrap_or(dotted)
}

pub(crate) struct Location {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
}

impl Module {
    pub(crate) fn new(rel: String, name: String, text: String, tree: ModModule) -> Self {
        let lines = Lines::new(&text);
        let package = package_for(&name);
        Self {
            rel,
            name,
            package,
            text,
            lines,
            tree,
        }
    }

    /// The source text of the module.
    #[cfg(any(test, feature = "dump"))]
    pub(crate) fn text(&self) -> &str {
        &self.text
    }

    /// `"\n".join(module.lines[line - 1 : end_line])`, or `None` outside the file.
    #[cfg(any(test, feature = "dump"))]
    pub(crate) fn excerpt(&self, line: i64, end_line: i64) -> Option<String> {
        let first = usize::try_from(line).ok().filter(|line| *line >= 1)?;
        let last = usize::try_from(end_line).ok()?;
        let mut parts = Vec::new();
        for number in first..=last {
            parts.push(self.lines.text(&self.text, number)?);
        }
        Some(parts.join("\n"))
    }

    /// `module.path.name == "__init__.py"`.
    pub(crate) fn is_init(&self) -> bool {
        self.rel.rsplit('/').next() == Some("__init__.py")
    }

    /// The line, the end line and the column of a statement.
    pub(crate) fn location(&self, node: &impl Ranged) -> Location {
        let start = node.start().to_usize();
        let line = self.lines.line(start).max(1);
        let end_line = self.lines.line(node.end().to_usize());
        let column = start - self.lines.start_of(start);
        Location {
            line: to_i64(line),
            end_line: to_i64(end_line),
            column: to_i64(column),
        }
    }

    /// `add_evidence`: file the location of a statement and return its id.
    pub(crate) fn evidence(&self, evidence: &mut EvidenceMap, node: &impl Ranged) -> String {
        let Location {
            line,
            end_line,
            column,
        } = self.location(node);
        let excerpt = usize::try_from(line)
            .ok()
            .and_then(|line| self.lines.text(&self.text, line))
            .map_or("", rstrip);
        file(
            evidence,
            Evidence::at(&self.rel, line, end_line, column, excerpt),
        )
    }

    /// `file_evidence`: line 1 when it holds text, else line 0 for the file itself.
    pub(crate) fn file_evidence(&self, evidence: &mut EvidenceMap) -> String {
        let first = rstrip(self.lines.text(&self.text, 1).unwrap_or(""));
        let item = if first.is_empty() {
            Evidence::at(&self.rel, 0, 0, 0, "")
        } else {
            Evidence::at(&self.rel, 1, 1, 0, first)
        };
        file(evidence, item)
    }
}

fn file(evidence: &mut EvidenceMap, item: Evidence) -> String {
    let id = item.id.as_str().to_owned();
    debug_assert_eq!(
        id,
        evidence_id(&item.file, item.line, item.end_line, item.column)
    );
    evidence.insert(id.clone(), item);
    id
}

fn to_i64(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

/// `str.rstrip()`: Python strips its `isspace` characters, which are the Unicode white space and
/// the four separators U+001C to U+001F.
pub(crate) use archkeel_pytext::rstrip;

#[cfg(test)]
#[path = "survey/module_tests.rs"]
mod tests;
