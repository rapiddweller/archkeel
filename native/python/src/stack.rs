// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! An upper bound of the CPython parser stack (AD-334 point 5).
//!
//! The CPython parser stops with a `MemoryError` when its rule calls nest deeper than `MAXSTACK`.
//! The number of rule calls for one nesting depends on its grammar context, so the bound adds a
//! measured upper bound for each nesting: a chain of `not`, unary signs, `await`, `lambda`, a
//! conditional `else` or `**` makes the parser recurse once for each link.

use ruff_python_ast::token::TokenKind as T;

/// `MAXSTACK` of the CPython parser (3.11 to 3.14).
pub const MAX_STACK: usize = 6_000;

// The parser frames of each nesting, an upper bound of the measured maximum on CPython 3.11 to
// 3.14: the measured value of each is in the comment.
/// A statement and the rules above its first expression: at most 54.
pub const STACK_BASE: usize = 80;
/// An indented block: 6 to 8.
pub const STACK_BLOCK: usize = 10;
/// A bracket with the operators of its level (`or`, `and`, a comparison, a keyword argument, a
/// comprehension condition, an f-string field): at most 37.
pub const STACK_BRACKET: usize = 48;
/// A `lambda`: 2, and 8 through a parameter default.
const STACK_LAMBDA: usize = 10;
/// A conditional `else`: 1.
const STACK_ELSE: usize = 2;
/// A unary sign, `not` or `await`: 1.
const STACK_UNARY: usize = 2;
/// A `**`: 2.
const STACK_POWER: usize = 3;

/// The links of one bracket level that the parser has not closed yet.
#[derive(Clone, Copy, Default)]
pub struct Frame {
    /// `lambda` and a conditional `else`: they last to the end of the expression.
    lambdas: usize,
    elses: usize,
    /// Unary signs, `not` and `await`: a binary operator ends them.
    unary: usize,
    /// `**`: a binary operator of a lower rank ends them.
    power: usize,
    /// The `lambda` whose `:` has not come yet: a `,` or `=` there is in its parameters.
    parameters: usize,
}

impl Frame {
    /// The bound of the open links.
    pub fn stack(&self) -> usize {
        self.lambdas * STACK_LAMBDA
            + self.elses * STACK_ELSE
            + self.unary * STACK_UNARY
            + self.power * STACK_POWER
    }

    /// Count the link of a token that is no bracket; `true` when it ends the expression of the
    /// level, so that the next one starts at the depth of the bracket.
    pub fn token(&mut self, kind: T, previous: T) -> bool {
        let prefix = !ends_operand(previous);
        match kind {
            T::Colon if self.parameters > 0 => self.parameters -= 1,
            T::Comma | T::Equal if self.parameters > 0 => {
                self.unary = 0;
                self.power = 0;
            }
            T::Lambda => {
                self.lambdas += 1;
                self.parameters += 1;
            }
            T::Else => self.elses += 1,
            T::Not if prefix && previous != T::Is => self.unary += 1,
            T::Minus | T::Plus | T::Tilde | T::Await if prefix || kind == T::Await => {
                self.unary += 1;
            }
            T::DoubleStar if !prefix => self.power += 1,
            _ if ends_expression(kind) => return true,
            _ if !prefix && is_binary(kind) => {
                self.unary = 0;
                self.power = 0;
            }
            _ => {}
        }
        false
    }
}
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
