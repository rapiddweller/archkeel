// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The line of each dependency in the text of its manifest, found in one pass over the text.
//! The line is evidence only: a key that the pass cannot match gives the first line.

use std::collections::BTreeMap;

use crate::manifest::{Kind, DEPENDENCY_SECTIONS};

/// A line number (from 1) and the trimmed text of the line.
type Cited = (i64, String);

pub(crate) struct LineIndex {
    first: Cited,
    /// The line of the key in its section.
    keys: BTreeMap<(Kind, String), Cited>,
    /// The line of the header `[<section>.<key>]`; it wins over the key line.
    headers: BTreeMap<(Kind, String), Cited>,
}

impl LineIndex {
    pub(crate) fn new(text: &str) -> Self {
        let first = (1, text.lines().next().unwrap_or("").trim().to_owned());
        let mut index = Self {
            first,
            keys: BTreeMap::new(),
            headers: BTreeMap::new(),
        };
        let mut inside = None;
        for (number, line) in text.lines().enumerate() {
            let line = line.trim();
            let cited = (
                i64::try_from(number + 1).unwrap_or(i64::MAX),
                line.to_owned(),
            );
            if line.starts_with('[') {
                let header = line.trim_matches(|c| c == '[' || c == ']');
                inside = section_of(header);
                index.header(header, cited);
            } else if let (Some(kind), Some(key)) = (inside, key_of(line)) {
                index.keys.entry((kind, key)).or_insert(cited);
            }
        }
        index
    }

    fn header(&mut self, header: &str, cited: Cited) {
        if let Some(entry) = table_of(header) {
            self.headers.entry(entry).or_insert(cited);
        }
    }

    /// The line of a dependency: its table header, else its key, else the first line.
    pub(crate) fn find(&self, kind: Kind, key: &str) -> Cited {
        let entry = (kind, key.to_owned());
        let found = self.headers.get(&entry).or_else(|| self.keys.get(&entry));
        found.unwrap_or(&self.first).clone()
    }
}

/// The kind of the section that a header names, as `[dependencies]` or `[target.x.dev-dependencies]`.
fn section_of(header: &str) -> Option<Kind> {
    DEPENDENCY_SECTIONS
        .iter()
        .find(|(section, _)| header == *section || header.ends_with(&format!(".{section}")))
        .map(|(_, kind)| *kind)
}

/// The kind and the key of a header `[<section>.<key>]`.
fn table_of(header: &str) -> Option<(Kind, String)> {
    DEPENDENCY_SECTIONS.iter().find_map(|(section, kind)| {
        let pattern = format!("{section}.");
        let at = header.match_indices(&pattern).find_map(|(at, _)| {
            (at == 0 || header[..at].ends_with('.')).then_some(at + pattern.len())
        })?;
        Some((*kind, unquote(&header[at..]).to_owned()))
    })
}

/// The first key of a line `key = ...` or `key.workspace = ...`.
fn key_of(line: &str) -> Option<String> {
    let (key, rest) = match line.chars().next()? {
        quote @ ('"' | '\'') => {
            let close = line[1..].find(quote)? + 1;
            (&line[1..close], &line[close + 1..])
        }
        _ => {
            let end = line
                .find(|c: char| !(c.is_ascii_alphanumeric() || c == '_' || c == '-'))
                .unwrap_or(line.len());
            (&line[..end], &line[end..])
        }
    };
    rest.trim_start()
        .starts_with(['=', '.'])
        .then(|| key.to_owned())
}

fn unquote(key: &str) -> &str {
    key.trim_matches(|c| c == '"' || c == '\'')
}

#[cfg(test)]
#[path = "manifest_lines_tests.rs"]
mod tests;
