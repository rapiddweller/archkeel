// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `parse` of `analyzer/dart/parse.py` (slices 3a and 3b of #880): the definitions, the
//! directives, the sites, the concerns, the first error and the language version of one source.

use tree_sitter::{Node, Parser};

use crate::dartstr::unclosed_block_comment;
use crate::definitions::definitions;
use crate::directives::directives;
use crate::nesting::brackets_overflow;
use crate::pytext::{is_assigned, is_space_byte};
use crate::sites::{sites, work_limit};
use crate::syntax::{Concern, ConcernKind, Definition, Directive, Site, Syntax};
use crate::tree::{children, walk, Source, Work};

/// The deepest node that the parse reads. Python stops the whole scan with `RecursionError`
/// near a depth of 987; native gives a syntax concern and so a gap for the file (AD-369).
pub(crate) const MAX_DEPTH: usize = 900;

const INCOMPLETE: &str = "Tree-sitter could not parse this Dart syntax completely.";

/// One Tree-sitter parser with the Dart grammar, used for each source of a run.
pub(crate) struct DartParser {
    parser: Parser,
    /// The share of the work limit that the sites of the last source used, in thousandths.
    pub(crate) work_permille: u64,
}

impl DartParser {
    pub(crate) fn new() -> Result<Self, String> {
        let mut parser = Parser::new();
        parser
            .set_language(&archkeel_dart_grammar::LANGUAGE.into())
            .map_err(|error| format!("cannot load the Dart grammar: {error}"))?;
        Ok(Self {
            parser,
            work_permille: 0,
        })
    }

    /// `parse(content)`: the syntax of one source.
    pub(crate) fn parse(&mut self, content: &[u8]) -> Syntax {
        let source = Source::new(content);
        self.work_permille = 0;
        // Tree-sitter keeps about a kilobyte for each open bracket: a source of 2.5 million `(`
        // takes 3 GB before one rule runs, so a source this deep is not parsed (AD-376).
        if let Some(at) = brackets_overflow(content) {
            let message = format!("Dart source nests deeper than {MAX_DEPTH} levels.");
            let concern = syntax_concern(&source, at, at.saturating_add(1), &message);
            return finish(Vec::new(), Vec::new(), Vec::new(), vec![concern], None);
        }
        let Some(tree) = self.parser.parse(content, None) else {
            // Tree-sitter returns no tree only after a cancel or a timeout, and this parser sets
            // neither. The concern keeps the file out of the facts if that changes.
            let concern = syntax_concern(&source, 0, content.len(), INCOMPLETE);
            return finish(Vec::new(), Vec::new(), Vec::new(), vec![concern], None);
        };
        let root = tree.root_node();
        let (mut concerns, deep) = tree_concerns(root, &source);
        if let Some(start) = unclosed_block_comment(content) {
            let message = "Dart source ends inside a nested block comment.";
            concerns.push(syntax_concern(&source, start, content.len(), message));
        }
        concerns.extend(encoding_concern(content, &source));
        let language_version = language_version(&source, &mut concerns);
        let directives = directives(root, &source, &mut concerns);
        concerns.extend(unsupported_concerns(root, &source));
        // One work counter and one limit for the definitions and the sites of a source (AD-376).
        let work = Work::new(work_limit(content.len()));
        let definitions = match definitions(root, &source, &work) {
            Ok(items) => items,
            Err(gap) => {
                let message = format!(
                    "The definition analysis of this Dart source stops: {}.",
                    gap.0
                );
                concerns.push(syntax_concern(&source, 0, content.len(), &message));
                self.work_permille = work.permille();
                return finish(
                    Vec::new(),
                    directives,
                    Vec::new(),
                    concerns,
                    language_version,
                );
            }
        };
        // Python stops with `RecursionError` on a deep tree, so its sites are not known. The
        // depth concern already gives the file a gap; native gives it no sites (AD-376).
        let mut found = Vec::new();
        if !deep {
            let result = sites(root, &source, &definitions, &directives, &work);
            match result {
                Ok(items) => found = items,
                Err(gap) => {
                    let message =
                        format!("The site analysis of this Dart source stops: {}.", gap.0);
                    concerns.push(syntax_concern(&source, 0, content.len(), &message));
                }
            }
        }
        self.work_permille = work.permille();
        finish(definitions, directives, found, concerns, language_version)
    }
}

fn finish(
    definitions: Vec<Definition>,
    directives: Vec<Directive>,
    sites: Vec<Site>,
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
        sites,
        complete: concerns.is_empty(),
        concerns,
        first_error,
        language_version,
    }
}

/// The UTF-8 error of Python, or else the first code point that Unicode 14 does not assign.
/// Python 3.12 and later read such a code point with newer Unicode data than the oracle Python
/// 3.11, so `\w` can differ: native names the file (L-27, AD-369).
fn encoding_concern(content: &[u8], source: &Source<'_>) -> Option<Concern> {
    let (start, end, message) = match std::str::from_utf8(content) {
        Err(error) => {
            let start = error.valid_up_to();
            let end = error
                .error_len()
                .map_or(content.len(), |length| start.saturating_add(length));
            (start, end, "Dart source is not valid UTF-8.")
        }
        Ok(text) => {
            let (start, c) = text.char_indices().find(|(_, c)| !is_assigned(*c))?;
            let message = "Dart source holds a code point that Unicode 14 does not assign.";
            (start, start.saturating_add(c.len_utf8()), message)
        }
    };
    Some(Concern {
        kind: ConcernKind::InvalidEncoding,
        message: message.to_owned(),
        span: source.span_bytes(start, end),
    })
}

fn syntax_concern(source: &Source<'_>, start: usize, end: usize, message: &str) -> Concern {
    Concern {
        kind: ConcernKind::SyntaxError,
        message: message.to_owned(),
        span: source.span_bytes(start, end),
    }
}

/// Each error and missing node, and the first node below `MAX_DEPTH`, in document order, and
/// whether the tree reaches `MAX_DEPTH`.
fn tree_concerns(root: Node<'_>, source: &Source<'_>) -> (Vec<Concern>, bool) {
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
    (concerns, deep)
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
            if out_of_range(major, minor) {
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
    /// The digits as written, with the leading zeros, which Python `int` also counts.
    digits: usize,
}

/// Python `int` refuses a text of more than 4 300 digits (`sys.int_info.default_max_str_digits`).
const MAX_DIGITS: usize = 4300;

impl<'a> Number<'a> {
    fn of(digits: &'a str) -> Self {
        let text = digits.trim_start_matches('0');
        Self {
            text: if text.is_empty() { "0" } else { text },
            digits: digits.len(),
        }
    }

    /// Python stops with `ValueError`; native gives the version concern (AD-369).
    fn too_long(self) -> bool {
        self.digits > MAX_DIGITS
    }

    /// The value, or `u64::MAX` for a number with more than 19 significant digits.
    fn value(self) -> u64 {
        self.text.parse().unwrap_or(u64::MAX)
    }
}

/// `version < (2, 12) or version > (3, 12)`, or a number that Python `int` refuses.
fn out_of_range(major: Number<'_>, minor: Number<'_>) -> bool {
    let version = (major.value(), minor.value());
    major.too_long() || minor.too_long() || !((2, 12)..=(3, 12)).contains(&version)
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
