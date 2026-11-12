// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The token scan before the parse (AD-334, AD-334).
//!
//! It copies the checks of CPython that `ruff_python_parser` does not have: the tokenizer limits
//! (200 nested brackets, 100 indentation levels, the tab rule, the unindent rule, 150 nested
//! f-strings, a second byte order mark, the identifier characters of each Unicode version), the
//! f-string limits of Python 3.11, the integer digit limit and `barry_as_FLUFL`. It also sums the
//! bound of the CPython parser stack of `stack.rs` for each token.

use archkeel_facts::pyminor::PyMinor;
use archkeel_facts::vocab::ExceptionName;
use ruff_python_ast::token::TokenKind as T;
use ruff_python_parser::lexer::lex;
use ruff_python_parser::Mode;

use super::identifier::refused;
use super::stack::{Frame, STACK_BASE, STACK_BLOCK, STACK_BRACKET};
use crate::source::Lines;

/// `MAXLEVEL` of the CPython tokenizer.
const MAX_BRACKETS: usize = 200;
/// `MAXINDENT` of the CPython tokenizer: the indentation stack holds at most 100 levels.
const MAX_INDENT: usize = 100;
/// `MAXFSTRINGLEVEL` of the CPython tokenizer (3.12 and later).
const MAX_STRINGS: usize = 150;
/// `sys.get_int_max_str_digits()` of an interpreter that `-I` starts.
const MAX_DIGITS: usize = 4_300;
/// `MAX_AST_DEPTH` of the Python collector (`source.py`).
pub const MAX_AST_DEPTH: usize = 5_000;

/// One error of CPython: its exception, its line and its message.
#[derive(Clone, Debug, PartialEq)]
pub struct Problem {
    pub exception: ExceptionName,
    pub line: usize,
    pub message: String,
    /// The byte offset: the start of the line for an indentation error, else the token.
    pub offset: usize,
}

/// What the scan found: the first tokenizer error, the first error that the CPython parser gives
/// and ruff does not, the stack bound, and the innermost bracket that is open at the end of the
/// file (its character and its line).
pub struct Scan {
    pub problem: Option<Problem>,
    pub parser: Option<Problem>,
    pub stack: usize,
    pub unclosed: Option<(char, usize)>,
}

/// An open f-string, replacement field or bracket, for the f-string rules.
enum Context {
    String,
    /// A replacement field: its format spec level, whether its spec started, and the offset of a
    /// leading `*` until a comma of the field makes a tuple.
    Field {
        level: usize,
        spec: bool,
        star: Option<usize>,
    },
    /// A bracket and its depth inside the innermost replacement field (0 outside a field).
    Bracket(usize),
}

/// Scan `text` for the minor version `minor` of Python 3.
pub fn scan(text: &str, lines: &Lines, minor: PyMinor) -> Scan {
    let mut work = super::work::Work::new();
    // Charge the byte scans once and then each token. Stack pops are bounded by token pushes.
    if !work.charge(text.len()) {
        return Scan {
            problem: Some(Problem {
                exception: ExceptionName::SyntaxError,
                line: 1,
                message: "CPython token scan work limit exceeded".to_owned(),
                offset: 0,
            }),
            parser: None,
            stack: 0,
            unclosed: None,
        };
    }
    let mut state = State {
        text,
        lines,
        minor,
        problem: None,
        parser: None,
        indents: vec![(0, 0)],
        brackets: Vec::new(),
        strings: 0,
        contexts: Vec::new(),
        field_start: false,
        future: 0,
        barry: false,
        frames: Vec::new(),
        frame: Frame::default(),
        base: 0,
        stack: 0,
        previous: T::Newline,
    };
    if text.starts_with('\u{feff}') {
        // `decode` drops one mark; ruff drops the next one, CPython refuses it.
        let message = "invalid non-printable character U+FEFF";
        state.fail(ExceptionName::SyntaxError, 0, message);
    }
    let mut lexer = lex(text, Mode::Module);
    let mut line_start = true;
    loop {
        if !work.charge(1) {
            state.fail(
                ExceptionName::SyntaxError,
                0,
                "CPython token scan work limit exceeded",
            );
            break;
        }
        let kind = lexer.next_token();
        if kind == T::EndOfFile {
            break;
        }
        let range = lexer.current_range();
        let (start, end) = (usize::from(range.start()), usize::from(range.end()));
        if line_start && !kind.is_trivia() && !matches!(kind, T::Indent | T::Dedent | T::Newline) {
            state.indentation(start);
            line_start = false;
        }
        state.token(kind, start, &text[start..end]);
        if kind == T::Newline {
            line_start = true;
        }
    }
    Scan {
        unclosed: state.brackets.last().copied(),
        problem: state.problem,
        parser: state.parser,
        stack: state.stack,
    }
}

struct State<'a> {
    text: &'a str,
    lines: &'a Lines,
    minor: PyMinor,
    problem: Option<Problem>,
    parser: Option<Problem>,
    /// The CPython indentation stack: the column with tab size 8 and with tab size 1.
    indents: Vec<(usize, usize)>,
    /// The open brackets that count for `MAXLEVEL`: the character and the line of each.
    brackets: Vec<(char, usize)>,
    /// The open f-strings and t-strings; Python 3.11 reads one as a single token.
    strings: usize,
    contexts: Vec<Context>,
    /// The last token opened a replacement field.
    field_start: bool,
    /// How much of `from __future__ import` the statement has, and whether it named
    /// `barry_as_FLUFL`: the CPython parser then refuses each later `!=` (3.12 and later).
    future: u8,
    barry: bool,
    /// The frame and the stack of each enclosing bracket level.
    frames: Vec<(Frame, usize)>,
    frame: Frame,
    /// The stack of the enclosing bracket levels.
    base: usize,
    stack: usize,
    previous: T,
}

impl State<'_> {
    fn problem(&self, exception: ExceptionName, offset: usize, message: &str) -> Problem {
        Problem {
            exception,
            line: self.lines.line(offset),
            message: message.to_owned(),
            offset,
        }
    }

    fn fail(&mut self, exception: ExceptionName, start: usize, message: &str) {
        if self.problem.is_none() {
            // CPython reads the indentation of a line before any token of it.
            let offset = match exception {
                ExceptionName::SyntaxError => start,
                _ => self.lines.start_of(start),
            };
            let mut problem = self.problem(exception, offset, message);
            problem.line = self.lines.line(start);
            self.problem = Some(problem);
        }
    }

    /// An error of the CPython parser at `offset`; the first by offset wins.
    fn parser_error(&mut self, offset: usize, message: &str) {
        if self
            .parser
            .as_ref()
            .is_none_or(|found| offset < found.offset)
        {
            self.parser = Some(self.problem(ExceptionName::SyntaxError, offset, message));
        }
    }

    /// The indentation check of `tok_get` for the first token of a logical line.
    fn indentation(&mut self, start: usize) {
        let (mut col, mut alt) = (0, 0);
        // The whitespace at the start of the physical line: a lexer error can start before it.
        for byte in self.text.as_bytes()[self.lines.start_of(start)..].iter() {
            match byte {
                b' ' => (col, alt) = (col + 1, alt + 1),
                b'\t' => (col, alt) = ((col / 8 + 1) * 8, alt + 1),
                0x0c => (col, alt) = (0, 0),
                _ => break,
            }
        }
        let (top, top_alt) = self.indents.last().copied().unwrap_or((0, 0));
        if col == top {
            if alt != top_alt {
                self.fail(ExceptionName::TabError, start, TAB_MESSAGE);
            }
        } else if col > top {
            if self.indents.len() >= MAX_INDENT {
                self.fail(
                    ExceptionName::IndentationError,
                    start,
                    "too many levels of indentation",
                );
            } else if alt <= top_alt {
                self.fail(ExceptionName::TabError, start, TAB_MESSAGE);
            }
            self.indents.push((col, alt));
        } else {
            while self.indents.len() > 1 && self.indents.last().is_some_and(|top| col < top.0) {
                self.indents.pop();
            }
            match self.indents.last() {
                Some((top, _)) if *top != col => self.fail(
                    ExceptionName::IndentationError,
                    start,
                    "unindent does not match any outer indentation level",
                ),
                Some((_, top_alt)) if *top_alt != alt => {
                    self.fail(ExceptionName::TabError, start, TAB_MESSAGE);
                }
                _ => {}
            }
        }
    }

    fn token(&mut self, kind: T, start: usize, text: &str) {
        if std::mem::take(&mut self.field_start) && kind == T::Star {
            if let Some(Context::Field { star, .. }) = self.contexts.last_mut() {
                *star = Some(start);
            }
        }
        self.words(kind, start, text);
        match kind {
            T::FStringStart | T::TStringStart => self.open_string(start),
            T::FStringEnd | T::TStringEnd => self.close_string(),
            T::Lpar => self.open(start, '('),
            T::Lsqb => self.open(start, '['),
            T::Lbrace => self.open(start, '{'),
            T::Rpar => self.close(start, ')'),
            T::Rsqb => self.close(start, ']'),
            T::Rbrace => self.close(start, '}'),
            _ => {
                if self.frame.token(kind, self.previous) {
                    self.field_part(kind);
                    self.frame = Frame::default();
                }
            }
        }
        let blocks = self.indents.len() - 1;
        let stack = STACK_BASE + blocks * STACK_BLOCK + self.base + self.frame.stack();
        self.stack = self.stack.max(stack);
        if !kind.is_trivia() {
            self.previous = kind;
        }
    }

    /// The checks of a name and a number: the identifier characters, the digit limit and
    /// `from __future__ import barry_as_FLUFL`.
    fn words(&mut self, kind: T, start: usize, text: &str) {
        match kind {
            T::Identifier if !text.is_ascii() => {
                let mut chars = text.chars();
                let first = chars.next().filter(|c| refused(self.minor, true, *c));
                if let Some(c) = first.or_else(|| chars.find(|c| refused(self.minor, false, *c))) {
                    let message = format!("invalid character '{c}' (U+{:04X})", u32::from(c));
                    self.fail(ExceptionName::SyntaxError, start, &message);
                }
            }
            T::Int => {
                let bytes = text.as_bytes();
                let prefixed = bytes.len() > 1
                    && bytes[0] == b'0'
                    && matches!(bytes[1], b'x' | b'X' | b'o' | b'O' | b'b' | b'B');
                let digits = bytes.iter().filter(|byte| byte.is_ascii_digit()).count();
                // A literal of zeros only has no limit: CPython converts it without the check.
                let zero = bytes.iter().all(|byte| matches!(byte, b'0' | b'_'));
                if !prefixed && !zero && digits > MAX_DIGITS {
                    let message = format!(
                        "Exceeds the limit ({MAX_DIGITS} digits) for integer string conversion: \
                         value has {digits} digits; use sys.set_int_max_str_digits() to increase \
                         the limit - Consider hexadecimal for huge integer literals to avoid \
                         decimal conversion limits."
                    );
                    self.parser_error(start, &message);
                }
            }
            T::NotEqual if self.barry && modern(self.minor) => {
                let message = "with Barry as BDFL, use '<>' instead of '!='";
                self.parser_error(start, message);
            }
            _ => {}
        }
        self.future = match (self.future, kind) {
            (_, T::From) => 1,
            (1, T::Identifier) if text == "__future__" => 2,
            (2, T::Import) => 3,
            (3, T::Identifier) if matches!(self.previous, T::Import | T::Comma | T::Lpar) => {
                self.barry |= text == "barry_as_FLUFL";
                3
            }
            (3, _) if !kind.is_any_newline() && kind != T::Semi => 3,
            _ => 0,
        };
    }

    fn open_string(&mut self, start: usize) {
        self.strings += 1;
        self.contexts.push(Context::String);
        if modern(self.minor) && self.strings >= MAX_STRINGS {
            let message = match self.minor {
                PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py313 => "too many nested f-strings",
                PyMinor::Py314 => "too many nested f-strings or t-strings",
            };
            self.fail(ExceptionName::SyntaxError, start, message);
        }
    }

    fn close_string(&mut self) {
        self.strings = self.strings.saturating_sub(1);
        while let Some(context) = self.contexts.pop() {
            if matches!(context, Context::String) {
                break;
            }
        }
    }

    /// A `,` makes a starred field a tuple, and a `:` starts the format spec of a field.
    fn field_part(&mut self, kind: T) {
        if let Some(Context::Field { spec, star, .. }) = self.contexts.last_mut() {
            match kind {
                T::Comma if !*spec => *star = None,
                T::Colon => *spec = true,
                _ => {}
            }
        }
    }

    fn open(&mut self, start: usize, bracket: char) {
        // Python 3.11 reads an f-string as one token, so its braces are no brackets there.
        if modern(self.minor) || self.strings == 0 {
            if self.brackets.len() >= MAX_BRACKETS {
                self.fail(
                    ExceptionName::SyntaxError,
                    start,
                    "too many nested parentheses",
                );
            }
            self.brackets.push((bracket, self.lines.line(start)));
        }
        self.open_context(start, bracket);
        self.frames.push((self.frame, self.base));
        self.base += self.frame.stack() + STACK_BRACKET;
        self.frame = Frame::default();
    }

    /// The f-string rules of Python 3.11: it parses each field alone, with at most 199 brackets
    /// inside, no field in the format spec of a field in a format spec, and no lone `*a`.
    fn open_context(&mut self, start: usize, bracket: char) {
        let context = match self.contexts.last() {
            Some(Context::String) if bracket == '{' => Some(0),
            Some(Context::Field {
                level, spec: true, ..
            }) if bracket == '{' => Some(level + 1),
            _ => None,
        };
        if let Some(level) = context {
            let max_level = match self.minor {
                PyMinor::Py311 => 2,
                PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => 3,
            };
            if level >= max_level {
                self.parser_error(start, "f-string: expressions nested too deeply");
            }
            self.field_start = true;
            self.contexts.push(Context::Field {
                level,
                spec: false,
                star: None,
            });
            return;
        }
        let inner = match self.contexts.last() {
            Some(Context::Field { .. }) => 1,
            Some(Context::Bracket(inner)) if *inner > 0 => inner + 1,
            _ => 0,
        };
        if !modern(self.minor) && inner >= MAX_BRACKETS {
            self.parser_error(start, "f-string: too many nested parenthesis");
        }
        self.contexts.push(Context::Bracket(inner));
    }

    /// The closing check of `tok_get`: a closing bracket must match the innermost open one.
    fn close(&mut self, start: usize, bracket: char) {
        if modern(self.minor) || self.strings == 0 {
            let line = self.lines.line(start);
            let message = match self.brackets.pop() {
                None => Some(format!("unmatched '{bracket}'")),
                Some((open, _))
                    if matches!((open, bracket), ('(', ')') | ('[', ']') | ('{', '}')) =>
                {
                    None
                }
                Some((open, at)) if at == line => Some(format!(
                    "closing parenthesis '{bracket}' does not match opening parenthesis '{open}'"
                )),
                Some((open, at)) => Some(format!(
                    "closing parenthesis '{bracket}' does not match opening parenthesis '{open}' \
                     on line {at}"
                )),
            };
            if let Some(message) = message {
                self.fail(ExceptionName::SyntaxError, start, &message);
            }
        }
        match self.contexts.last() {
            Some(Context::String) | None => {}
            Some(Context::Field { star, .. }) => {
                if let (Some(star), false) = (*star, modern(self.minor)) {
                    self.parser_error(star, "f-string: cannot use starred expression here");
                }
                self.contexts.pop();
            }
            Some(Context::Bracket(_)) => {
                self.contexts.pop();
            }
        }
        if let Some((frame, base)) = self.frames.pop() {
            self.frame = frame;
            self.base = base;
        }
    }
}

const TAB_MESSAGE: &str = "inconsistent use of tabs and spaces in indentation";

fn modern(minor: PyMinor) -> bool {
    match minor {
        PyMinor::Py311 => false,
        PyMinor::Py312 | PyMinor::Py313 | PyMinor::Py314 => true,
    }
}

#[cfg(test)]
#[path = "limits_tests.rs"]
mod tests;
