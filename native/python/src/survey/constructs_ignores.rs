// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The comment forms whose exact type-ignore statement is known.

use std::{collections::BTreeMap, ops::Range};

use archkeel_facts::data::SignalData;
use archkeel_facts::vocab::Signal;
use ruff_python_ast::{Expr, Stmt};

pub(super) fn member_call(expr: &Expr) -> bool {
    matches!(expr, Expr::Call(call) if matches!(&*call.func, Expr::Attribute(attr) if matches!(&*attr.value, Expr::Name(_))))
}

pub(super) fn data(owner: &str, line: i64, tag: String, statement: String) -> SignalData {
    SignalData {
        annotation: None,
        expression: None,
        line: Some(line),
        owner: owner.to_owned(),
        positions: None,
        qualified_name: Some(owner.to_owned()),
        signal: Signal::TypeIgnore,
        statement: Some(statement),
        tag: Some(tag),
    }
}

pub(super) struct Comments {
    pending: BTreeMap<usize, Option<String>>,
}

impl Comments {
    pub(super) fn new(text: &str, ranges: Vec<Range<usize>>) -> Self {
        let pending = ranges
            .into_iter()
            .filter_map(|range| {
                let comment = &text[range.clone()];
                if !comment.contains("type") {
                    return None;
                }
                let tag = comment
                    .strip_prefix('#')
                    .map(str::trim_start)
                    .and_then(|s| s.strip_prefix("type:"))
                    .map(str::trim_start)
                    .and_then(|s| s.strip_prefix("ignore"))
                    .filter(|s| {
                        str::is_empty(s)
                            || (s.starts_with('[')
                                && s.ends_with(']')
                                && s[1..str::len(s) - 1]
                                    .bytes()
                                    .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b','))
                    })
                    .map(str::to_owned);
                Some((range.start, tag))
            })
            .collect();
        Self { pending }
    }

    pub(super) fn take(
        &mut self,
        text: &str,
        line: usize,
        start: usize,
        end: usize,
        stmt: &Stmt,
    ) -> Option<(String, String)> {
        let statement = text.get(start..end)?;
        if statement.contains(['\n', '\r']) {
            return None;
        }
        match stmt {
            Stmt::Assign(node) if matches!(node.targets.as_slice(), [Expr::Name(_)]) => {}
            Stmt::Expr(_) => {
                let (base, member) = statement
                    .strip_suffix(')')?
                    .split_once('(')?
                    .0
                    .split_once('.')?;
                if !identifier(base) || !identifier(member) {
                    return None;
                }
            }
            _ => return None,
        }
        if !str::is_empty(text[line..start].trim()) {
            return None;
        }
        let (&at, tag) = self.pending.range(end..).next()?;
        if tag.is_none()
            || !str::is_empty(text[end..at].trim())
            || text[end..at].contains(['\n', '\r'])
        {
            return None;
        }
        Some((self.pending.remove(&at).flatten()?, statement.to_owned()))
    }

    pub(super) fn complete(&self) -> bool {
        BTreeMap::is_empty(&self.pending)
    }
}

fn identifier(name: &str) -> bool {
    let mut bytes = name.bytes();
    bytes
        .next()
        .is_some_and(|b| b.is_ascii_alphabetic() || b == b'_')
        && bytes.all(|b| b.is_ascii_alphanumeric() || b == b'_')
}
