// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The marked Mermaid graphs of the provenance documents of the root contract (AD-458).
//!
//! Reference engine: `check/validation/graphs.py` `graph_diagnostics`. The documents must hold
//! exactly one block after the component marker, and at most one after the target marker
//! (`graph.count`). The edges of the component block must be the observed component edges, and
//! the edges of the target block the permitted component pairs (`graph.drift`). A block with a
//! line that is not an edge, a node, a declaration or a comment, or with an ambiguous node label,
//! is a drift too. The text is read with universal newlines, as the reference engine reads it.

use std::collections::{BTreeMap, BTreeSet};

/// A component pair: the source label and the target label.
pub(crate) type Pair = (String, String);

const COMPONENT_MARKER: &str = "<!-- archkeel-component-graph -->";
const TARGET_MARKER: &str = "<!-- archkeel-target-graph -->";
const FENCE: &str = "```mermaid\n";
const CLOSE: &str = "```";

/// One graph finding: the code, the subject and the claim.
pub(crate) type Finding = (&'static str, String, String);

/// The findings of both markers over the documents, in path order. `observed` are the component
/// edges of the code; `permitted` are the pairs that the contract permits.
pub(crate) fn findings(
    documents: &[(String, String)],
    observed: &BTreeSet<Pair>,
    permitted: &BTreeSet<Pair>,
) -> Vec<Finding> {
    let mut found = Vec::new();
    let markers = [
        (
            COMPONENT_MARKER,
            "component",
            true,
            observed,
            "observed imports",
        ),
        (
            TARGET_MARKER,
            "target",
            false,
            permitted,
            "the edges the contract permits",
        ),
    ];
    for (marker, noun, required, edges, source) in markers {
        let graphs: Vec<(&str, &str)> = documents
            .iter()
            .flat_map(|(path, text)| {
                marked_bodies(text, marker)
                    .into_iter()
                    .map(move |body| (path.as_str(), body))
            })
            .collect();
        if graphs.is_empty() && !required {
            continue;
        }
        let [(path, body)] = graphs.as_slice() else {
            let claim = format!(
                "Expected one marked Mermaid {noun} graph, found {}.",
                graphs.len()
            );
            found.push(("graph.count", format!("architecture {noun} graph"), claim));
            continue;
        };
        let declared = declared_edges(body);
        let unwritable = unwritable_line(body);
        if declared == *edges && unwritable.is_none() {
            continue;
        }
        let list = |pairs: Vec<&Pair>| {
            let text: Vec<String> = pairs.iter().map(|(a, b)| format!("{a}->{b}")).collect();
            if text.is_empty() {
                "none".to_owned()
            } else {
                text.join(", ")
            }
        };
        let claim = format!(
            "The marked {noun} graph differs from {source}; drawn and not found: {}; found and \
             not drawn: {}{}.",
            list(declared.difference(edges).collect()),
            list(edges.difference(&declared).collect()),
            unwritable.map_or_else(String::new, |line| format!("; the block holds `{line}`")),
        );
        found.push(("graph.drift", format!("{path} ({noun} graph)"), claim));
    }
    found
}

/// The text of a document with universal newlines, as the reference engine reads it, or `None`
/// when it is not UTF-8.
pub(crate) fn text(bytes: &[u8]) -> Option<String> {
    let text = std::str::from_utf8(bytes).ok()?;
    Some(text.replace("\r\n", "\n").replace('\r', "\n"))
}

/// Each Mermaid body that follows `marker`, before the next marker (`_marked_bodies`).
fn marked_bodies<'t>(content: &'t str, marker: &str) -> Vec<&'t str> {
    let mut bodies = Vec::new();
    let mut position = content.find(marker);
    while let Some(at) = position {
        let after = at.saturating_add(marker.len());
        let following = content
            .get(after..)
            .and_then(|rest| rest.find(marker))
            .map(|found| found.saturating_add(after));
        let limit = following.unwrap_or(content.len());
        let window = content.get(at..limit).unwrap_or_default();
        if let Some(fence) = window.find(FENCE) {
            let start = at.saturating_add(fence).saturating_add(FENCE.len());
            let inner = content.get(start..limit).unwrap_or_default();
            let end = inner
                .find(CLOSE)
                .map_or(limit, |end| start.saturating_add(end));
            bodies.push(content.get(start..end).unwrap_or_default());
        }
        position = following;
    }
    bodies
}

/// The white space of the reference engine (`str.isspace`).
pub(crate) fn space(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}

/// The lines of a body as the reference engine splits them (`splitlines`).
fn lines(body: &str) -> impl Iterator<Item = &str> {
    body.split([
        '\n', '\u{b}', '\u{c}', '\u{1c}', '\u{1d}', '\u{1e}', '\u{85}', '\u{2028}', '\u{2029}',
    ])
}

fn strip(line: &str) -> &str {
    line.trim_matches(space)
}

/// The identifier `[a-z_][a-z0-9_]*` at the start of `text`, and the rest.
fn identifier(text: &str) -> Option<(&str, &str)> {
    let first = text.chars().next()?;
    if !(first.is_ascii_lowercase() || first == '_') {
        return None;
    }
    let end = text
        .find(|c: char| !(c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_'))
        .unwrap_or(text.len());
    Some((text.get(..end)?, text.get(end..)?))
}

/// `\s*ID\s*-->\s*ID\s*` as a full match.
fn edge(line: &str) -> Option<(&str, &str)> {
    let (source, rest) = identifier(strip(line))?;
    let rest = rest.trim_start_matches(space).strip_prefix("-->")?;
    let (target, rest) = identifier(rest.trim_start_matches(space))?;
    rest.is_empty().then_some((source, target))
}

/// `\s*ID\s*\["([^"\r\n]*)"\]\s*` as a full match: the alias and the encoded label.
fn node(line: &str) -> Option<(&str, &str)> {
    let (alias, rest) = identifier(strip(line))?;
    let rest = rest.trim_start_matches(space).strip_prefix("[\"")?;
    let end = rest.find('"')?;
    let (label, rest) = (rest.get(..end)?, rest.get(end..)?);
    (rest == "\"]" && !label.contains(['\r', '\n'])).then_some((alias, label))
}

fn bare_identifier(stripped: &str) -> bool {
    identifier(stripped).is_some_and(|(_, rest)| rest.is_empty())
}

/// `\s*(?:graph|flowchart)\b.*` as a full match of a stripped line.
fn declaration(stripped: &str) -> bool {
    ["graph", "flowchart"].iter().any(|word| {
        stripped.strip_prefix(word).is_some_and(|rest| {
            rest.chars()
                .next()
                .is_none_or(|next| !(next.is_alphanumeric() || next == '_'))
        })
    })
}

/// The label of `#<digits>;` entities decoded once, or `None` when an entity is not a character.
fn unescape(value: &str) -> Option<String> {
    let mut out = String::new();
    let mut rest = value;
    while let Some(at) = rest.find('#') {
        out.push_str(rest.get(..at)?);
        let after = rest.get(at.saturating_add(1)..)?;
        let digits = after
            .find(|c: char| !c.is_ascii_digit())
            .unwrap_or(after.len());
        if digits > 0 && after.get(digits..)?.starts_with(';') {
            let code: u32 = after.get(..digits)?.parse().ok()?;
            out.push(char::from_u32(code)?);
            rest = after.get(digits.saturating_add(1)..)?;
        } else {
            out.push('#');
            rest = after;
        }
    }
    out.push_str(rest);
    Some(out)
}

/// The label of each node alias, and the first line that makes the labels ambiguous.
fn node_labels(body: &str) -> (BTreeMap<String, String>, Option<String>) {
    let mut labels: BTreeMap<String, String> = BTreeMap::new();
    let mut aliases: BTreeMap<String, String> = BTreeMap::new();
    for line in lines(body) {
        let Some((alias, encoded)) = node(line) else {
            continue;
        };
        let conflict = Some(strip(line).to_owned());
        let Some(label) = unescape(encoded) else {
            return (labels, conflict);
        };
        let other_label = labels.get(alias).is_some_and(|previous| *previous != label);
        let other_alias = aliases
            .get(&label)
            .is_some_and(|previous| previous != alias);
        if other_label || other_alias {
            return (labels, conflict);
        }
        labels.insert(alias.to_owned(), label.clone());
        aliases.insert(label, alias.to_owned());
    }
    (labels, None)
}

/// The edges that a block draws, with each alias replaced by its label.
fn declared_edges(body: &str) -> BTreeSet<Pair> {
    let (labels, _) = node_labels(body);
    let name = |alias: &str| {
        labels
            .get(alias)
            .cloned()
            .unwrap_or_else(|| alias.to_owned())
    };
    lines(body)
        .filter_map(edge)
        .map(|(source, target)| (name(source), name(target)))
        .collect()
}

/// The first line that a block cannot hold: an ambiguous label, or a line that is not an edge, a
/// node, an identifier, a declaration or a comment (`_unwritable_line` with isolated nodes).
fn unwritable_line(body: &str) -> Option<String> {
    if let (_, Some(conflict)) = node_labels(body) {
        return Some(conflict);
    }
    lines(body).map(strip).find_map(|stripped| {
        let held = stripped.is_empty()
            || edge(stripped).is_some()
            || node(stripped).is_some()
            || bare_identifier(stripped)
            || declaration(stripped)
            || stripped.starts_with("%%");
        (!held).then(|| stripped.to_owned())
    })
}

#[cfg(test)]
#[path = "hygiene_graph_tests.rs"]
mod tests;
