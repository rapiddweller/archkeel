// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The directives of `analyzer/dart/parse.py`: library, part, part of, import and export, with
//! the concern of each URI that is not a plain string.

use tree_sitter::Node;

use crate::dartstr::{decode_dart_string, directive_uri, string_sequence};
use crate::pytext::{is_space, is_word, strip};
use crate::syntax::{Combinator, Concern, ConcernKind, Directive, DirectiveKind};
use crate::tree::{
    children, first_identifier, first_in_walk, named, named_all, named_children, named_in,
    text_children, walk, Source,
};

/// The directives of the top level, sorted by their start byte. Each concern is appended to
/// `concerns` in the order of the Python parse.
pub(crate) fn directives(
    root: Node<'_>,
    source: &Source<'_>,
    concerns: &mut Vec<Concern>,
) -> Vec<Directive> {
    let mut result = Vec::new();
    for node in named_children(root) {
        match node.kind() {
            "library_name" => result.push(Directive::new(
                DirectiveKind::Library,
                source.span(node),
                Some(text_children(node, source)),
            )),
            "part_directive" => {
                let target = literal_uri(named(node, "uri"), source);
                if target.is_none() {
                    concerns.push(unsupported(source, node, "Part URI is not a plain string."));
                }
                result.push(Directive::new(
                    DirectiveKind::Part,
                    source.span(node),
                    target,
                ));
            }
            "part_of_directive" => {
                let target = match named(node, "uri") {
                    Some(uri) => literal_uri(Some(uri), source),
                    None => Some(text_children(node, source)),
                };
                if target.is_none() {
                    let message = "Part owner is not a literal or library name.";
                    concerns.push(unsupported(source, node, message));
                }
                result.push(Directive::new(
                    DirectiveKind::PartOf,
                    source.span(node),
                    target,
                ));
            }
            "import_or_export" => {
                let kinds = ["library_import", "library_export"];
                if let Some(item) = named_children(node)
                    .into_iter()
                    .find(|item| kinds.contains(&item.kind()))
                {
                    result.push(library_directive(item, source, concerns));
                }
            }
            _ => {}
        }
    }
    result.sort_by_key(|item| item.span.start_byte);
    result
}

fn unsupported(source: &Source<'_>, node: Node<'_>, message: &str) -> Concern {
    Concern {
        kind: ConcernKind::UnsupportedDirective,
        message: message.to_owned(),
        span: source.span(node),
    }
}

/// `_library_directive`: an import or an export with its URIs, prefix and combinators.
fn library_directive(
    node: Node<'_>,
    source: &Source<'_>,
    concerns: &mut Vec<Concern>,
) -> Directive {
    let kind = if node.kind() == "library_import" {
        DirectiveKind::Import
    } else {
        DirectiveKind::Export
    };
    let spec = named(node, "import_specification")
        .or_else(|| named(node, "export_specification"))
        .unwrap_or(node);
    let uri = named(spec, "configurable_uri")
        .or_else(|| named(spec, "uri"))
        .or_else(|| first_in_walk(spec, &["configurable_uri"]));
    let primary_node = named_in(uri, "uri").or(uri);
    // Python `a or b`: an empty URI of the keyword scan falls back to the tree.
    let primary = directive_uri(source.data, node.start_byte(), node.end_byte())
        .filter(|text| !text.is_empty())
        .or_else(|| literal_uri(primary_node, source));
    let mut directive = Directive::new(kind, source.span(node), primary);
    directive.alternatives = conditional_uris(uri, source, concerns);
    if directive.target.is_none() {
        let message = "Import/export URI is not a plain string.";
        concerns.push(unsupported(source, node, message));
    }
    for item in named_all(Some(spec), "combinator") {
        let mode = match children(item)
            .first()
            .map(|first| source.text(*first))
            .as_deref()
        {
            Some("show") => Combinator::Show,
            Some("hide") => Combinator::Hide,
            // Python raises here (`Combinator(...)` or an empty `children`) and stops the scan;
            // the file gets a syntax concern (AD-369).
            _ => {
                concerns.push(Concern {
                    kind: ConcernKind::SyntaxError,
                    message: "Dart combinator is not show or hide.".to_owned(),
                    span: source.span(item),
                });
                continue;
            }
        };
        let names: Vec<String> = named_children(item)
            .into_iter()
            .filter(|child| child.kind() == "identifier")
            .map(|child| source.text(child))
            .collect();
        match mode {
            Combinator::Show => directive.show.extend(names.iter().cloned()),
            Combinator::Hide => directive.hide.extend(names.iter().cloned()),
        }
        directive.combinators.push((mode, names));
    }
    directive.deferred = deferred_as(&source.text(spec));
    directive.prefix = match named(spec, "import_prefix") {
        Some(prefix) => first_identifier(Some(prefix), source),
        None => named_all(Some(spec), "identifier")
            .first()
            .map(|item| source.text(*item)),
    };
    directive
}

/// `re.search(r"\bdeferred\s+as\b", text)`.
fn deferred_as(text: &str) -> bool {
    text.match_indices("deferred").any(|(at, word)| {
        let before = text.get(..at).and_then(|head| head.chars().next_back());
        let tail = text.get(at.saturating_add(word.len())..).unwrap_or("");
        let after = tail.trim_start_matches(is_space);
        let next = after.get(2..).and_then(|rest| rest.chars().next());
        !before.is_some_and(is_word)
            && after.len() < tail.len()
            && after.starts_with("as")
            && !next.is_some_and(is_word)
    })
}

/// `_conditional_uris`: the `if (condition) 'uri'` alternatives of a configurable URI.
fn conditional_uris(
    uri: Option<Node<'_>>,
    source: &Source<'_>,
    concerns: &mut Vec<Concern>,
) -> Vec<(String, String)> {
    let configurable = uri.filter(|item| item.kind() == "configurable_uri");
    let mut alternatives = Vec::new();
    for choice in named_all(configurable, "configuration_uri") {
        let condition = named(choice, "configuration_uri_condition");
        let alternative = literal_uri(named(choice, "uri"), source);
        let (Some(condition), Some(alternative)) = (condition, alternative) else {
            concerns.push(unsupported(
                source,
                choice,
                "Conditional URI is not literal.",
            ));
            continue;
        };
        let text = source.text(condition);
        let stripped = strip(&text);
        let count = stripped.chars().count();
        let inner: String = stripped
            .chars()
            .skip(1)
            .take(count.saturating_sub(2))
            .collect();
        alternatives.push((strip(&inner).to_owned(), alternative));
    }
    alternatives
}

/// `_literal_uri`: the string of a URI node, by the byte scan or by its string literals.
pub(crate) fn literal_uri(node: Option<Node<'_>>, source: &Source<'_>) -> Option<String> {
    let node = node?;
    if let Some(scanned) = string_sequence(source.data, node.start_byte(), node.end_byte()) {
        return Some(scanned);
    }
    let strings = ["string_literal", "raw_string_literal"];
    let literals: Vec<Node<'_>> = walk(node)
        .filter(|item| strings.contains(&item.kind()))
        .filter(|item| {
            !named_children(*item)
                .iter()
                .any(|child| strings.contains(&child.kind()))
        })
        .collect();
    if literals.is_empty() {
        return None;
    }
    let pieces: Option<Vec<String>> = literals
        .iter()
        .map(|item| decode_dart_string(&source.text(*item)))
        .collect();
    pieces.map(|pieces| pieces.concat())
}

#[cfg(test)]
mod tests {
    use super::deferred_as;

    // The expected values come from `re.search(r"\bdeferred\s+as\b", text)`.
    #[test]
    fn deferred_as_needs_two_whole_words() {
        assert!(deferred_as("'a.dart' deferred as a"));
        assert!(deferred_as("'a.dart' deferred\n  as a"));
        assert!(!deferred_as("'a.dart' deferredas a"));
        assert!(!deferred_as("'a.dart' xdeferred as a"));
        assert!(!deferred_as("'a.dart' deferred asx"));
        assert!(deferred_as("'a' xdeferred as y deferred as z"));
    }
}
