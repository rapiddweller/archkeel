// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Why an expression has no text, and `_Precedence` of the unparser.

/// Why an expression has no text.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Failure {
    /// CPython raises `ValueError`: `annotation_text` is `None`.
    Invalid,
    /// Over `MAX_DEPTH` levels: CPython can stop with `RecursionError`.
    Deep,
    /// Ruff changed the value of a string (a lone surrogate escape is U+FFFD), so the text of
    /// CPython is unknown.
    Unseen,
    /// CPython 3.12 reads a format spec in its own way: `\N{...}`, or a raw spec with a
    /// backslash (L-37a).
    Spec312,
    /// A format spec nests deeper than CPython keeps it.
    SpecDepth,
    /// The interpreter of the request is outside 3.11 to 3.14: no text rules (L-37b).
    Version,
}

/// `_Precedence`: `BOR` is `EXPR`.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord)]
pub enum Prec {
    NamedExpr = 1,
    Tuple,
    Yield,
    Test,
    Or,
    And,
    Not,
    Cmp,
    Expr,
    BXor,
    BAnd,
    Shift,
    Arith,
    Term,
    Factor,
    Power,
    Await,
    Atom,
}

impl Prec {
    /// `next()`: one level higher, at most `ATOM`.
    pub fn next(self) -> Prec {
        use Prec::*;
        match self {
            NamedExpr => Tuple,
            Tuple => Yield,
            Yield => Test,
            Test => Or,
            Or => And,
            And => Not,
            Not => Cmp,
            Cmp => Expr,
            Expr => BXor,
            BXor => BAnd,
            BAnd => Shift,
            Shift => Arith,
            Arith => Term,
            Term => Factor,
            Factor => Power,
            Power => Await,
            Await | Atom => Atom,
        }
    }
}
