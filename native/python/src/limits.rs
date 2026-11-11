// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The token scan before the parse (AD-334).
//!
//! It copies the limits of the CPython tokenizer that `ruff_python_parser` does not have: 200
//! nested brackets, 100 indentation levels, the tab rule and the unindent rule. It also bounds
//! the depth of the parse: a chain of `not`, unary signs, `await`, `lambda`, a conditional `else`
//! or `**` makes the parser recurse once for each link, and 30 000 links overflow its stack.

use archkeel_facts::vocab::ExceptionName;
use ruff_python_ast::token::TokenKind as T;
use ruff_python_parser::lexer::lex;
use ruff_python_parser::Mode;

use crate::source::Lines;

/// `MAXLEVEL` of the CPython tokenizer.
pub const MAX_BRACKETS: usize = 200;
/// `MAXINDENT` of the CPython tokenizer: the indentation stack holds at most 100 levels.
const MAX_INDENT: usize = 100;
/// `MAX_AST_DEPTH` of the Python collector (`source.py`).
pub const MAX_AST_DEPTH: usize = 5_000;
/// A parse deeper than this cannot give a tree of at most `MAX_AST_DEPTH` levels: each counted
/// link is one level of the tree, and only a bracket that groups adds a count without a level.
pub const MAX_PARSE_DEPTH: usize = MAX_AST_DEPTH + MAX_BRACKETS + 1;

/// The first tokenizer error of CPython: its exception, its line and its message.
#[derive(Clone, Debug, PartialEq)]
pub struct Problem {
    pub exception: ExceptionName,
    pub line: usize,
    pub message: String,
    /// The byte offset: the start of the line for an indentation error, else the token.
    pub offset: usize,
}

/// What the scan found: the first tokenizer error, the deepest parse that the file needs, and the
/// innermost bracket that is open at the end of the file (its character and its line).
pub struct Scan {
    pub problem: Option<Problem>,
    pub depth: usize,
    pub unclosed: Option<(char, usize)>,
}

/// The links of one bracket level that the parser has not closed yet.
#[derive(Clone, Copy, Default)]
struct Frame {
    /// `lambda` and a conditional `else`: they last to the end of the expression.
    open: usize,
    /// Unary signs, `not` and `await`: a binary operator ends them.
    unary: usize,
    /// `**`: a binary operator of a lower rank ends them.
    power: usize,
    /// The `lambda` whose `:` has not come yet.
    lambdas: usize,
}

impl Frame {
    fn depth(&self) -> usize {
        1 + self.open + self.unary + self.power
    }

    fn end_expression(&mut self) {
        *self = Frame::default();
    }
}

/// Scan `text` for the minor version `minor` of Python 3.
pub fn scan(text: &str, lines: &Lines, minor: u32) -> Scan {
    let mut state = State {
        text,
        lines,
        minor,
        problem: None,
        indents: vec![(0, 0)],
        brackets: Vec::new(),
        strings: 0,
        frames: Vec::new(),
        frame: Frame::default(),
        base: 0,
        depth: 0,
        previous: T::Newline,
    };
    let mut lexer = lex(text, Mode::Module);
    let mut line_start = true;
    loop {
        let kind = lexer.next_token();
        if kind == T::EndOfFile {
            break;
        }
        let start = usize::from(lexer.current_range().start());
        if line_start && !kind.is_trivia() && !matches!(kind, T::Indent | T::Dedent | T::Newline) {
            state.indentation(start);
            line_start = false;
        }
        state.token(kind, start);
        if kind == T::Newline {
            line_start = true;
        }
    }
    Scan {
        unclosed: state.brackets.last().copied(),
        problem: state.problem,
        depth: state.depth,
    }
}

struct State<'a> {
    text: &'a str,
    lines: &'a Lines,
    minor: u32,
    problem: Option<Problem>,
    /// The CPython indentation stack: the column with tab size 8 and with tab size 1.
    indents: Vec<(usize, usize)>,
    /// The open brackets that count for `MAXLEVEL`: the character and the line of each.
    brackets: Vec<(char, usize)>,
    /// The open f-strings and t-strings; Python 3.11 reads one as a single token.
    strings: usize,
    frames: Vec<(Frame, usize)>,
    frame: Frame,
    /// The depth of the enclosing bracket levels.
    base: usize,
    depth: usize,
    previous: T,
}

impl State<'_> {
    fn fail(&mut self, exception: ExceptionName, start: usize, message: &str) {
        if self.problem.is_none() {
            let line = self.lines.line(start);
            // CPython reads the indentation of a line before any token of it.
            let offset = match exception {
                ExceptionName::SyntaxError => start,
                _ => self.lines.start_of(start),
            };
            self.problem = Some(Problem {
                exception,
                line,
                message: message.to_owned(),
                offset,
            });
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

    fn token(&mut self, kind: T, start: usize) {
        let prefix = !ends_operand(self.previous);
        match kind {
            T::FStringStart | T::TStringStart => self.strings += 1,
            T::FStringEnd | T::TStringEnd => self.strings = self.strings.saturating_sub(1),
            T::Lpar => self.open(start, '('),
            T::Lsqb => self.open(start, '['),
            T::Lbrace => self.open(start, '{'),
            T::Rpar => self.close(start, ')'),
            T::Rsqb => self.close(start, ']'),
            T::Rbrace => self.close(start, '}'),
            T::Colon if self.frame.lambdas > 0 => self.frame.lambdas -= 1,
            T::Lambda => {
                self.frame.open += 1;
                self.frame.lambdas += 1;
            }
            T::Else => self.frame.open += 1,
            T::Not if prefix && self.previous != T::Is => self.frame.unary += 1,
            T::Minus | T::Plus | T::Tilde | T::Await if prefix || kind == T::Await => {
                self.frame.unary += 1;
            }
            T::DoubleStar if !prefix => self.frame.power += 1,
            _ if ends_expression(kind) => self.frame.end_expression(),
            _ if !prefix && is_binary(kind) => {
                self.frame.unary = 0;
                self.frame.power = 0;
            }
            _ => {}
        }
        self.depth = self.depth.max(self.base + self.frame.depth());
        if !kind.is_trivia() {
            self.previous = kind;
        }
    }

    fn open(&mut self, start: usize, bracket: char) {
        // Python 3.11 reads an f-string as one token, so its braces are no brackets there.
        if self.minor >= 12 || self.strings == 0 {
            if self.brackets.len() >= MAX_BRACKETS {
                self.fail(
                    ExceptionName::SyntaxError,
                    start,
                    "too many nested parentheses",
                );
            }
            self.brackets.push((bracket, self.lines.line(start)));
        }
        self.base += self.frame.depth();
        self.frames.push((self.frame, self.base));
        self.frame = Frame::default();
    }

    /// The closing check of `tok_get`: a closing bracket must match the innermost open one.
    fn close(&mut self, start: usize, bracket: char) {
        if self.minor >= 12 || self.strings == 0 {
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
        if let Some((frame, base)) = self.frames.pop() {
            self.frame = frame;
            self.base = base - frame.depth();
        }
    }
}

const TAB_MESSAGE: &str = "inconsistent use of tabs and spaces in indentation";

/// Whether a token can end an operand, so that a sign after it is a binary operator. A soft
/// keyword can be a name.
fn ends_operand(kind: T) -> bool {
    kind.is_singleton()
        || kind.is_soft_keyword()
        || matches!(
            kind,
            T::Identifier
                | T::Int
                | T::Float
                | T::Complex
                | T::String
                | T::FStringEnd
                | T::TStringEnd
                | T::Rpar
                | T::Rsqb
                | T::Rbrace
                | T::Ellipsis
        )
}

/// A token after which the next expression starts at the depth of its bracket level.
fn ends_expression(kind: T) -> bool {
    kind.is_any_newline()
        || is_augmented_assign(kind)
        || matches!(
            kind,
            T::Comma | T::Semi | T::Colon | T::Equal | T::ColonEqual | T::Rarrow | T::Indent
        )
}

fn is_augmented_assign(kind: T) -> bool {
    kind.as_augmented_assign_operator().is_some()
}

/// A binary operator, or a keyword after which an operand ends a chain of unary signs.
fn is_binary(kind: T) -> bool {
    kind.as_binary_operator().is_some()
        || kind.as_bool_operator().is_some()
        || matches!(
            kind,
            T::Less
                | T::Greater
                | T::EqEqual
                | T::NotEqual
                | T::LessEqual
                | T::GreaterEqual
                | T::In
                | T::Is
                | T::Not
                | T::If
                | T::For
        )
}

#[cfg(test)]
#[path = "limits_tests.rs"]
mod tests;
