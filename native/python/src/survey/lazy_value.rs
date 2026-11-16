// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The values of the run of a lazy `__getattr__` (AD-654, `lazy_return.rs`) and the strings that
//! literals, f-strings and `+` build from them; the tests that the values decide and the join of
//! paths.

use std::collections::{BTreeSet, HashMap};

use ruff_python_ast::{
    CmpOp, ConversionFlag, Expr, FStringPartRef, InterpolatedStringElement, Operator,
};

use super::lazy_cover::Source;

/// The value of each local name in one path of a run.
pub(super) type Env = HashMap<String, Val>;

/// What one name or expression holds in one run.
#[derive(Clone, Debug, PartialEq, Eq)]
pub(super) enum Val {
    Str(String),
    /// An integer literal, as the index of an entry.
    Index(usize),
    /// The tuple of one entry of the table.
    Entry(Vec<String>),
    /// One `(key, entry)` item of `table.items()`.
    Pair(String, Vec<String>),
    NoneValue,
    /// The requested name of the run for a name that is no key.
    NonKey,
    Table,
    Globals,
    Value(Source),
    Unknown,
}

/// The string of a literal, an f-string of plain fields, or a `+` of strings.
pub(super) fn text(expr: &Expr, eval: &dyn Fn(&Expr) -> Val) -> Option<String> {
    match expr {
        Expr::StringLiteral(node) => Some(node.value.to_str().to_owned()),
        Expr::BinOp(node) if node.op == Operator::Add => {
            let left = string(&node.left, eval)?;
            Some(left + &string(&node.right, eval)?)
        }
        Expr::FString(node) => node.value.iter().map(|part| fpart(part, eval)).collect(),
        _ => None,
    }
}

/// The text of one part of an f-string.
fn fpart(part: FStringPartRef, eval: &dyn Fn(&Expr) -> Val) -> Option<String> {
    match part {
        FStringPartRef::Literal(literal) => Some(literal.value.to_string()),
        FStringPartRef::FString(fstring) => fstring
            .elements
            .iter()
            .map(|element| field(element, eval))
            .collect(),
    }
}

fn string(expr: &Expr, eval: &dyn Fn(&Expr) -> Val) -> Option<String> {
    match eval(expr) {
        Val::Str(value) => Some(value),
        _ => None,
    }
}

fn field(element: &InterpolatedStringElement, eval: &dyn Fn(&Expr) -> Val) -> Option<String> {
    match element {
        InterpolatedStringElement::Literal(literal) => Some(literal.value.to_string()),
        InterpolatedStringElement::Interpolation(field) => {
            let plain = field.debug_text.is_none()
                && field.conversion == ConversionFlag::None
                && field.format_spec.is_none();
            plain.then(|| string(&field.expression, eval)).flatten()
        }
    }
}

/// The truth of `left op right`, when the values decide it.
pub(super) fn compare(op: CmpOp, left: &Val, right: &Val, keys: &BTreeSet<String>) -> Option<bool> {
    let decided = match (op, left, right) {
        (CmpOp::Eq | CmpOp::NotEq, Val::Str(a), Val::Str(b)) => a == b,
        (CmpOp::Is | CmpOp::IsNot, value, Val::NoneValue) => match value {
            Val::NoneValue => true,
            Val::Unknown | Val::NonKey => return None,
            _ => false,
        },
        (CmpOp::In | CmpOp::NotIn, Val::Str(key), Val::Table) => keys.contains(key),
        (CmpOp::In | CmpOp::NotIn, Val::NonKey, Val::Table) => false,
        _ => return None,
    };
    let negated = matches!(op, CmpOp::NotEq | CmpOp::IsNot | CmpOp::NotIn);
    Some(decided != negated)
}

/// The environment after paths that meet: a name keeps its value only when each path has it.
pub(super) fn join(ends: Vec<Option<Env>>) -> Option<Env> {
    let mut alive = ends.into_iter().flatten();
    let mut out = alive.next()?;
    for other in alive {
        for (name, value) in &mut out {
            if other.get(name) != Some(value) {
                *value = Val::Unknown;
            }
        }
        for name in other.keys() {
            out.entry(name.clone()).or_insert(Val::Unknown);
        }
    }
    Some(out)
}
