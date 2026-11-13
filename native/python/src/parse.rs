// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Parse one module as `source._parse_bounded` does, with the grammar of one Python version.
//!
//! The order is the order of CPython: the first error by line wins, and a tokenizer error wins
//! over a parser error on the same line, because CPython reads the indentation of a line before
//! its tokens. The message of a parser error is the text of `ruff_python_parser`; the message of
//! a tokenizer limit and of the depth rule is the text of CPython (AD-334).

use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::vocab::ExceptionName;
use ruff_python_ast::{ModModule, PythonVersion, Stmt};
use ruff_python_parser::{parse_unchecked, Mode, ParseErrorType, ParseOptions};
use ruff_text_size::Ranged;

use self::depth::depth;
use self::limits::{scan, Problem, MAX_AST_DEPTH};
use self::stack::MAX_STACK;
use crate::source::Lines;

#[path = "compilercheck.rs"]
mod compilercheck;
#[path = "depth.rs"]
mod depth;
#[path = "expressioncheck.rs"]
mod expressioncheck;
#[path = "identifier.rs"]
mod identifier;
#[path = "limits.rs"]
pub(crate) mod limits;
#[path = "patterncheck.rs"]
mod patterncheck;
#[path = "postparse.rs"]
mod postparse;
#[path = "scopecheck.rs"]
mod scopecheck;
#[path = "stack.rs"]
mod stack;
#[path = "stringcheck.rs"]
mod stringcheck;
#[path = "work.rs"]
pub(crate) mod work;
/// Reuse the bounded module preflight before parsing a syntax-only quoted expression.
#[cfg(any(test, feature = "dump"))]
pub(crate) fn quoted_expression(text: &str, minor: PyMinor) -> Option<ruff_python_ast::Expr> {
    parse(text, minor).ok()?;
    ruff_python_parser::parse_expression(text)
        .ok()
        .map(|n| *n.into_syntax().body)
}

/// Why a file has no tree: the class name of the Python exception, its line and its message.
#[derive(Clone, Debug, PartialEq)]
pub struct ParseFailure {
    pub exception: ExceptionName,
    pub line: usize,
    pub message: String,
}

impl From<Problem> for ParseFailure {
    fn from(problem: Problem) -> Self {
        Self {
            exception: problem.exception,
            line: problem.line,
            message: problem.message,
        }
    }
}

const NULL_BYTES: &str = "source code string cannot contain null bytes";

/// The tree of `text` for Python 3.`minor`, or the failure that the Python collector reports.
pub fn parse(text: &str, minor: PyMinor) -> Result<ModModule, ParseFailure> {
    if text.contains('\0') {
        return Err(failure(ExceptionName::SyntaxError, 1, NULL_BYTES));
    }
    let lines = Lines::new(text);
    let scan = scan(text, &lines, minor);
    if text.len() > work::MAX_WORK {
        return Err(failure(
            ExceptionName::SyntaxError,
            1,
            "CPython token scan work limit exceeded",
        ));
    }
    if scan.stack > MAX_STACK {
        // An upper bound of the CPython parser stack: CPython can stop here, so the file has no
        // tree (AD-323 point 6, AD-334). The bound also keeps ruff inside its own stack. The
        // bound is above the real stack, so an error that the scan found is the likelier error.
        let found = scan.problem.into_iter().chain(scan.parser);
        if let Some(problem) = found.min_by_key(|problem| problem.offset) {
            return Err(problem.into());
        }
        let message = "expression nesting exceeds the parser stack";
        return Err(failure(ExceptionName::TooDeepError, 1, message));
    }
    let version = PythonVersion {
        major: 3,
        minor: minor.number(),
    };
    let options = ParseOptions::from(Mode::Module).with_target_version(version);
    let parsed = parse_unchecked(text, options);
    let parser = first_parser_error(&parsed, &lines, scan.parser);
    match (scan.problem, parser) {
        // CPython then reads the rest of the file, and its first tokenizer error replaces a
        // parser error inside an open bracket: the problem, or else the bracket at the end.
        (Some(problem), Some((_, error))) if in_open_bracket(&error, scan.unclosed) => {
            return Err(problem.into())
        }
        (Some(problem), Some((offset, error))) if offset < problem.offset => return Err(error),
        (Some(problem), _) => return Err(problem.into()),
        (None, Some((_, error))) => return Err(unclosed(error, scan.unclosed)),
        (None, None) => {}
    }
    let Some(parsed) = parsed.try_into_module() else {
        return Err(failure(ExceptionName::SyntaxError, 1, "invalid syntax"));
    };
    let module = parsed.into_syntax();
    if let Some(failure) = future(&module, &lines, minor) {
        return Err(failure);
    }
    let levels = depth(&module);
    if levels > MAX_AST_DEPTH {
        // A deep tree drops by recursion; the process ends soon, so it keeps the memory.
        std::mem::forget(module);
        let message = format!("expression nesting of {levels} levels exceeds {MAX_AST_DEPTH}");
        return Err(failure(ExceptionName::TooDeepError, 1, &message));
    }
    if let Some((offset, reason)) = identifier::constant_names(&module, minor)
        .or_else(|| compilercheck::check(&module, text, minor))
        .or_else(|| postparse::check(&module, text, minor))
    {
        let exception = if reason.starts_with("CPython 3.12 cannot decode") {
            ExceptionName::UnicodeDecodeError
        } else {
            ExceptionName::SyntaxError
        };
        return Err(failure(exception, lines.line(offset), reason));
    }
    Ok(module)
}

/// Whether a parser error is at the end of the file or after a bracket that stays open there.
fn in_open_bracket(error: &ParseFailure, open: Option<(char, usize)>) -> bool {
    open.is_some_and(|(_, line)| error.message == EOF_MESSAGE || error.line >= line)
}

/// CPython names the innermost open bracket when the file ends inside it: the parser error at
/// the end, or an error inside the bracket, which a scan of the rest of the file replaces.
fn unclosed(error: ParseFailure, open: Option<(char, usize)>) -> ParseFailure {
    match open {
        Some((bracket, line)) if in_open_bracket(&error, open) => ParseFailure {
            exception: ExceptionName::SyntaxError,
            line,
            message: format!("'{bracket}' was never closed"),
        },
        _ => error,
    }
}

/// The text of `LexicalErrorType::Eof`.
const EOF_MESSAGE: &str = "unexpected EOF while parsing";

fn failure(exception: ExceptionName, line: usize, message: &str) -> ParseFailure {
    ParseFailure {
        exception,
        line,
        message: message.to_owned(),
    }
}

/// The features of `__future__` in CPython 3.14.
const FEATURES: [&str; 10] = [
    "nested_scopes",
    "generators",
    "division",
    "absolute_import",
    "with_statement",
    "print_function",
    "unicode_literals",
    "barry_as_FLUFL",
    "generator_stop",
    "annotations",
];

/// `future_parse` of CPython 3.14, which `ast.parse` runs: each name of a `from __future__`
/// import at the start of the module (after the docstring) must be a known feature.
fn future(module: &ModModule, lines: &Lines, minor: PyMinor) -> Option<ParseFailure> {
    let mut body = module.body.as_slice();
    if let [Stmt::Expr(docstring), rest @ ..] = body {
        if docstring.value.is_string_literal_expr() {
            body = rest;
        }
    }
    let mut permitted = true;
    for statement in body {
        let Stmt::ImportFrom(import) = statement else {
            permitted = false;
            continue;
        };
        if !scopecheck::is_future(import, minor) {
            permitted = false;
            continue;
        }
        if !permitted {
            return Some(failure(
                ExceptionName::SyntaxError,
                lines.line(import.start().to_usize()),
                "future import is not at the start of the module",
            ));
        }
        for alias in &import.names {
            let name = alias.name.as_str();
            if FEATURES.contains(&name) {
                continue;
            }
            let message = match name {
                "braces" => "not a chance".to_owned(),
                _ => format!("future feature {name} is not defined"),
            };
            let line = lines.line(usize::from(alias.range.start()));
            return Some(failure(ExceptionName::SyntaxError, line, &message));
        }
    }
    None
}

/// The first syntax error by position, and its byte offset: a parse error, a construct that is
/// newer than the target version, or an error of the CPython parser that the scan found.
fn first_parser_error<T>(
    parsed: &ruff_python_parser::Parsed<T>,
    lines: &Lines,
    scanned: Option<Problem>,
) -> Option<(usize, ParseFailure)> {
    let errors = parsed.errors().iter().map(|error| {
        (
            usize::from(error.location.start()),
            exception(&error.error),
            error.error.to_string(),
        )
    });
    let unsupported = parsed.unsupported_syntax_errors().iter().map(|error| {
        let at = usize::from(error.range.start());
        (at, ExceptionName::SyntaxError, error.to_string())
    });
    let scanned = scanned
        .into_iter()
        .map(|problem| (problem.offset, problem.exception, problem.message));
    errors
        .chain(unsupported)
        .chain(scanned)
        .min_by_key(|(at, _, _)| *at)
        .map(|(at, exception, message)| {
            let line = lines.line(at);
            (
                at,
                ParseFailure {
                    exception,
                    line,
                    message,
                },
            )
        })
}

/// The class of the Python exception for a parse error: an indentation error is an
/// `IndentationError`, as in CPython.
fn exception(error: &ParseErrorType) -> ExceptionName {
    use ruff_python_ast::token::TokenKind;
    use ruff_python_parser::LexicalErrorType;
    match error {
        ParseErrorType::UnexpectedIndentation
        | ParseErrorType::Lexical(LexicalErrorType::IndentationError)
        | ParseErrorType::ExpectedToken {
            expected: TokenKind::Indent,
            ..
        } => ExceptionName::IndentationError,
        // The parser gives this error as text only (`statement.rs`); CPython raises it as an
        // `IndentationError`. The parse tests pin the text of the pinned release.
        ParseErrorType::OtherError(text) if text.starts_with("Expected an indented block") => {
            ExceptionName::IndentationError
        }
        _ => ExceptionName::SyntaxError,
    }
}

#[cfg(test)]
#[path = "parse_tests.rs"]
mod tests;
