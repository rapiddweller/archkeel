// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `parse` of `analyzer/dart/parse.py` without the sites (slice 3a of #880): the definitions,
//! the directives, the concerns, the first error and the language version of one source.

use tree_sitter::{Node, Parser};

use crate::dartstr::unclosed_block_comment;
use crate::definitions::definitions;
use crate::directives::directives;
use crate::syntax::{Concern, ConcernKind, Syntax};
use crate::tree::{children, walk, Source};

/// The deepest node that the parse reads. Python stops the whole scan with `RecursionError`
/// near a depth of 987; native gives a syntax concern and so a gap for the file (AD-369).
pub(crate) const MAX_DEPTH: usize = 900;

const INCOMPLETE: &str = "Tree-sitter could not parse this Dart syntax completely.";

/// One Tree-sitter parser with the Dart grammar, used for each source of a run.
pub(crate) struct DartParser {
    parser: Parser,
}

impl DartParser {
    pub(crate) fn new() -> Result<Self, String> {
        let mut parser = Parser::new();
        parser
            .set_language(&archkeel_dart_grammar::LANGUAGE.into())
            .map_err(|error| format!("cannot load the Dart grammar: {error}"))?;
        Ok(Self { parser })
    }

    /// `parse(content)`: the syntax of one source.
    pub(crate) fn parse(&mut self, content: &[u8]) -> Syntax {
        let source = Source::new(content);
        let Some(tree) = self.parser.parse(content, None) else {
            // Tree-sitter returns no tree only after a cancel or a timeout, and this parser sets
            // neither. The concern keeps the file out of the facts if that changes.
            let concern = syntax_concern(&source, 0, content.len(), INCOMPLETE);
            return finish(Vec::new(), Vec::new(), vec![concern], None);
        };
        let root = tree.root_node();
        let mut concerns = tree_concerns(root, &source);
        if let Some(start) = unclosed_block_comment(content) {
            let message = "Dart source ends inside a nested block comment.";
            concerns.push(syntax_concern(&source, start, content.len(), message));
        }
        if let Err(error) = std::str::from_utf8(content) {
            let start = error.valid_up_to();
            let end = error
                .error_len()
                .map_or(content.len(), |length| start.saturating_add(length));
            concerns.push(Concern {
                kind: ConcernKind::InvalidEncoding,
                message: "Dart source is not valid UTF-8.".to_owned(),
                span: source.span_bytes(start, end),
            });
        }
        let language_version = language_version(&source, &mut concerns);
        let directives = directives(root, &source, &mut concerns);
        concerns.extend(unsupported_concerns(root, &source));
        let definitions = definitions(root, &source);
        finish(definitions, directives, concerns, language_version)
    }
}

fn finish(
    definitions: Vec<crate::syntax::Definition>,
    directives: Vec<crate::syntax::Directive>,
    mut concerns: Vec<Concern>,
    language_version: Option<String>,
) -> Syntax {
    concerns.sort_by(|a, b| {
        (a.span.start_byte, a.kind.as_str()).cmp(&(b.span.start_byte, b.kind.as_str()))
    });
    let first_error = concerns
        .iter()
        .find(|item| item.kind.is_error())
        .map(|item| item.span.clone());
    Syntax {
        definitions,
        directives,
        complete: concerns.is_empty(),
        concerns,
        first_error,
        language_version,
    }
}

fn syntax_concern(source: &Source<'_>, start: usize, end: usize, message: &str) -> Concern {
    Concern {
        kind: ConcernKind::SyntaxError,
        message: message.to_owned(),
        span: source.span_bytes(start, end),
    }
}

/// Each error and missing node, and the first node below `MAX_DEPTH`, in document order.
fn tree_concerns(root: Node<'_>, source: &Source<'_>) -> Vec<Concern> {
    let mut concerns = Vec::new();
    let mut deep = false;
    let mut nodes = walk(root);
    while let Some(node) = nodes.next() {
        if node.is_error() || node.is_missing() {
            concerns.push(Concern {
                kind: ConcernKind::SyntaxError,
                message: INCOMPLETE.to_owned(),
                span: source.span(node),
            });
        }
        if !deep && nodes.depth >= MAX_DEPTH {
            deep = true;
            let message = format!("Dart source nests deeper than {MAX_DEPTH} levels.");
            concerns.push(syntax_concern(
                source,
                node.start_byte(),
                node.end_byte(),
                &message,
            ));
        }
    }
    concerns
}

/// `_unsupported_concerns`: a mixin with an `on` clause.
fn unsupported_concerns(root: Node<'_>, source: &Source<'_>) -> Vec<Concern> {
    walk(root)
        .filter(|node| node.kind() == "mixin_declaration")
        .filter(|node| children(*node).iter().any(|child| child.kind() == "on"))
        .map(|node| Concern {
            kind: ConcernKind::UnsupportedDeclaration,
            message: "Mixin on-constraints are not modeled by this parser.".to_owned(),
            span: source.span(node),
        })
        .collect()
}

/// `_language_version`: the first `// @dart=<major>.<minor>` line, as
/// `re.search(rb"(?m)^\s*//\s*@dart=(\d+)\.(\d+)(?:\.\d+)?\s*$", content)` finds it.
fn language_version(source: &Source<'_>, concerns: &mut Vec<Concern>) -> Option<String> {
    let data = source.data;
    let mut start = 0usize;
    loop {
        let landing = skip_space(data, start);
        if let Some((major, minor, end)) = version_at(data, landing) {
            let value = format!("{}.{}", major.text, minor.text);
            if major.below(2, minor, 12) || major.above(3, minor, 12) {
                concerns.push(Concern {
                    kind: ConcernKind::LanguageVersionError,
                    message: "Dart language override is outside supported range 2.12 through 3.12."
                        .to_owned(),
                    span: source.span_bytes(start, end),
                });
            }
            return Some(value);
        }
        // Each line start up to `landing` lands on the same byte and fails the same way.
        let after = landing.max(start);
        let newline = data.get(after..)?.iter().position(|b| *b == b'\n')?;
        start = after.saturating_add(newline).saturating_add(1);
    }
}

/// The bytes of `\s` in a `bytes` pattern.
fn is_space_byte(value: u8) -> bool {
    matches!(value, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c)
}

fn skip_space(data: &[u8], from: usize) -> usize {
    let run = data.get(from..).map_or(0, |rest| {
        rest.iter().take_while(|b| is_space_byte(**b)).count()
    });
    from.saturating_add(run)
}

/// A decimal number as Python `int` writes it: no leading zeros.
#[derive(Clone, Copy)]
struct Number<'a> {
    text: &'a str,
}

impl<'a> Number<'a> {
    fn of(digits: &'a str) -> Self {
        let text = digits.trim_start_matches('0');
        Self {
            text: if text.is_empty() { "0" } else { text },
        }
    }

    /// The value, or `u64::MAX` for a number with more than 19 digits. Python stops on more
    /// than 4 300 digits; such a version is out of range here (AD-369).
    fn value(self) -> u64 {
        self.text.parse().unwrap_or(u64::MAX)
    }

    fn below(self, major: u64, minor: Self, limit: u64) -> bool {
        (self.value(), minor.value()) < (major, limit)
    }

    fn above(self, major: u64, minor: Self, limit: u64) -> bool {
        (self.value(), minor.value()) > (major, limit)
    }
}

/// The match after `^\s*` at `at`: the major and the minor version and the end of the match.
fn version_at(data: &[u8], at: usize) -> Option<(Number<'_>, Number<'_>, usize)> {
    let rest = data.get(at..)?.strip_prefix(b"//")?;
    let at = skip_space(data, data.len().saturating_sub(rest.len()));
    let rest = data.get(at..)?.strip_prefix(b"@dart=")?;
    let digits = |from: &[u8]| from.iter().take_while(|b| b.is_ascii_digit()).count();
    let major_len = digits(rest);
    let after_major = rest.get(major_len..)?;
    if major_len == 0 {
        return None;
    }
    let minor_part = after_major.strip_prefix(b".")?;
    let minor_len = digits(minor_part);
    if minor_len == 0 {
        return None;
    }
    let mut tail = minor_part.get(minor_len..)?;
    if let Some(patch) = tail.strip_prefix(b".") {
        let patch_len = digits(patch);
        if patch_len > 0 {
            tail = patch.get(patch_len..)?;
        }
    }
    let tail_at = data.len().saturating_sub(tail.len());
    let end = line_end(data, tail_at)?;
    let major = Number::of(std::str::from_utf8(rest.get(..major_len)?).ok()?);
    let minor = Number::of(std::str::from_utf8(minor_part.get(..minor_len)?).ok()?);
    Some((major, minor, end))
}

/// `\s*$` with `(?m)`: the longest white space run that ends at the end or before a `\n`.
fn line_end(data: &[u8], from: usize) -> Option<usize> {
    let run_end = skip_space(data, from);
    if run_end == data.len() {
        return Some(run_end);
    }
    let run = data.get(from..run_end)?;
    run.iter()
        .rposition(|b| *b == b'\n')
        .map(|at| from.saturating_add(at))
}

#[cfg(test)]
#[path = "parse_tests.rs"]
mod tests;
