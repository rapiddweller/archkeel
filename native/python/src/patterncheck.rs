// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Pattern checks that the CPython compiler applies after the grammar.

use super::work::Work;
use ruff_python_ast::{Expr, MatchCase, Number, Pattern};
use ruff_text_size::Ranged;
use std::collections::HashSet;

pub fn capture(node: &Pattern) -> Option<&str> {
    match node {
        Pattern::MatchAs(node) => node.name.as_ref().map(|name| name.as_str()),
        Pattern::MatchStar(node) => node.name.as_ref().map(|name| name.as_str()),
        Pattern::MatchMapping(node) => node.rest.as_ref().map(|name| name.as_str()),
        _ => None,
    }
}

pub fn check(cases: &[MatchCase], work: &mut Work) -> Option<&'static str> {
    let mut terminal = false;
    for case in cases {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if terminal {
            return Some("irrefutable pattern makes remaining cases unreachable");
        }
        terminal = match irrefutable(&case.pattern, work) {
            Ok(terminal) => case.guard.is_none() && terminal,
            Err(reason) => return Some(reason),
        };
        let mut names = HashSet::new();
        if let Some(reason) = pattern(&case.pattern, &mut names, work, 0) {
            return Some(reason);
        }
    }
    None
}

fn pattern(
    node: &Pattern,
    names: &mut HashSet<String>,
    work: &mut Work,
    depth: usize,
) -> Option<&'static str> {
    if !work.charge(1) {
        return Some("CPython validation work limit exceeded");
    }
    if depth >= 100 {
        return Some("CPython pattern validation depth limit exceeded");
    }
    let mut bind = |name: &str| {
        if name == "__debug__" {
            Some("cannot bind __debug__")
        } else {
            (!names.insert(name.to_owned())).then_some("duplicate pattern capture")
        }
    };
    match node {
        Pattern::MatchAs(node) => {
            if let Some(name) = &node.name {
                if let Some(reason) = bind(name.as_str()) {
                    return Some(reason);
                }
            }
            node.pattern
                .as_ref()
                .and_then(|node| pattern(node, names, work, depth + 1))
        }
        Pattern::MatchStar(node) => node.name.as_ref().and_then(|name| bind(name.as_str())),
        Pattern::MatchSequence(node) => sequence(&node.patterns, names, work, depth),
        Pattern::MatchOr(node) => alternatives(&node.patterns, names, work, depth),
        Pattern::MatchMapping(node) => mapping(node, names, work, depth),
        Pattern::MatchClass(node) => {
            let mut keywords = HashSet::new();
            for keyword in &node.arguments.keywords {
                if keyword.attr.as_str() == "__debug__" {
                    return Some("cannot bind __debug__");
                }
                if !work.charge(1) {
                    return Some("CPython validation work limit exceeded");
                }
                if !keywords.insert(keyword.attr.as_str()) {
                    return Some("duplicate class pattern keyword");
                }
                if let Some(reason) = pattern(&keyword.pattern, names, work, depth + 1) {
                    return Some(reason);
                }
            }
            for item in &node.arguments.patterns {
                if !work.charge(1) {
                    return Some("CPython validation work limit exceeded");
                }
                if let Some(reason) = pattern(item, names, work, depth + 1) {
                    return Some(reason);
                }
            }
            None
        }
        Pattern::MatchValue(node)
            if matches!(&*node.value, Expr::FString(_) | Expr::TString(_)) =>
        {
            Some("patterns may only match literals and attribute lookups")
        }
        Pattern::MatchValue(_) | Pattern::MatchSingleton(_) => None,
    }
}

fn sequence(
    items: &[Pattern],
    names: &mut HashSet<String>,
    work: &mut Work,
    depth: usize,
) -> Option<&'static str> {
    let mut stars = 0;
    for (index, item) in items.iter().enumerate() {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        stars += usize::from(matches!(item, Pattern::MatchStar(_)));
        if matches!(item, Pattern::MatchStar(_)) && index >= 256 {
            return Some("too many expressions before a star pattern");
        }
        if let Some(reason) = pattern(item, names, work, depth + 1) {
            return Some(reason);
        }
    }
    (stars > 1).then_some("multiple star patterns")
}

fn alternatives(
    items: &[Pattern],
    names: &mut HashSet<String>,
    work: &mut Work,
    depth: usize,
) -> Option<&'static str> {
    let mut expected = None;
    let mut terminal = false;
    for item in items {
        if !work.charge(names.len().saturating_add(1)) {
            return Some("CPython validation work limit exceeded");
        }
        if terminal {
            return Some("irrefutable pattern makes remaining alternatives unreachable");
        }
        terminal = match irrefutable(item, work) {
            Ok(terminal) => terminal,
            Err(reason) => return Some(reason),
        };
        let mut branch = names.clone();
        if let Some(reason) = pattern(item, &mut branch, work, depth + 1) {
            return Some(reason);
        }
        if expected.as_ref().is_some_and(|other| *other != branch) {
            return Some("pattern alternatives bind different names");
        }
        expected = Some(branch);
    }
    if let Some(expected) = expected {
        *names = expected;
    }
    None
}

fn mapping(
    node: &ruff_python_ast::PatternMatchMapping,
    names: &mut HashSet<String>,
    work: &mut Work,
    depth: usize,
) -> Option<&'static str> {
    let mut keys = HashSet::new();
    for key in &node.keys {
        if !work.charge(key.range().len().to_usize().saturating_add(1)) {
            return Some("CPython validation work limit exceeded");
        }
        let Some(key_text) = literal_key(key) else {
            if node.keys.len() > 1 && matches!(key, Expr::UnaryOp(_) | Expr::BinOp(_)) {
                return Some("mapping literal key equality is not proved");
            }
            continue;
        };
        let key = key_text;
        if !work.charge(key.len()) {
            return Some("CPython validation work limit exceeded");
        }
        if !keys.insert(key) {
            return Some("duplicate mapping pattern key");
        }
    }
    if let Some(rest) = &node.rest {
        if rest.as_str() == "__debug__" {
            return Some("cannot bind __debug__");
        }
        if !names.insert(rest.to_string()) {
            return Some("duplicate pattern capture");
        }
    }
    for item in &node.patterns {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if let Some(reason) = pattern(item, names, work, depth + 1) {
            return Some(reason);
        }
    }
    None
}

fn irrefutable(node: &Pattern, work: &mut Work) -> Result<bool, &'static str> {
    // The pattern walk has already bounded the tree; keep this read iterative as well.
    let mut pending = vec![node];
    while let Some(node) = pending.pop() {
        if !work.charge(1) {
            return Err("CPython validation work limit exceeded");
        }
        match node {
            Pattern::MatchAs(node) if node.pattern.is_none() => return Ok(true),
            Pattern::MatchAs(node) => pending.extend(node.pattern.as_deref()),
            Pattern::MatchOr(node) => pending.extend(&node.patterns),
            _ => {}
        }
    }
    Ok(false)
}

fn literal_key(expr: &Expr) -> Option<String> {
    match expr {
        Expr::BooleanLiteral(node) => Some(format!("number:{}", u8::from(node.value))),
        Expr::NumberLiteral(node) => match &node.value {
            Number::Int(value) => Some(format!("number:{value}")),
            Number::Float(value) => Some(format!("number:{value}")),
            Number::Complex { real, imag } => Some(if *imag == 0.0 {
                format!("number:{real}")
            } else {
                format!("complex:{real}:{imag}")
            }),
        },
        Expr::StringLiteral(node) => Some(format!("string:{}", node.value.to_str())),
        Expr::BytesLiteral(node) => Some(format!(
            "bytes:{:?}",
            node.value.bytes().collect::<Vec<_>>()
        )),
        Expr::UnaryOp(node) => {
            let Expr::NumberLiteral(number) = &*node.operand else {
                return None;
            };
            let negative = node.op == ruff_python_ast::UnaryOp::USub;
            let value = match &number.value {
                Number::Int(value) => value.to_string(),
                Number::Float(value) => value.to_string(),
                Number::Complex { .. } => return None,
            };
            Some(format!(
                "number:{}{value}",
                if negative && value != "0" { "-" } else { "" }
            ))
        }
        Expr::BinOp(node) => {
            let (Expr::NumberLiteral(left), Expr::NumberLiteral(right)) =
                (&*node.left, &*node.right)
            else {
                return None;
            };
            let Number::Complex { imag: 0.0, .. } = right.value else {
                return None;
            };
            match &left.value {
                Number::Int(value) => Some(format!("number:{value}")),
                Number::Float(value) => Some(format!("number:{value}")),
                Number::Complex { .. } => None,
            }
        }
        Expr::NoneLiteral(_) => Some("none".to_owned()),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn sequence_work_is_exact() {
        let tree = crate::test_tree("match value:\n case [a, b, *rest]: pass", 14).unwrap();
        let ruff_python_ast::Stmt::Match(node) = &tree.body[0] else {
            return;
        };
        let mut work = super::Work::new();
        assert_eq!(super::check(&node.cases, &mut work), None);
        assert_eq!(work.used(), 9);
    }
}
