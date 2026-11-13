// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compiler checks for lambda parameters and comprehension expressions.

use super::work::Work;
use archkeel_facts::pyminor::PyMinor;
use ruff_python_ast::{
    visitor::{self, Visitor},
    Comprehension, Expr, ExprContext, Parameters,
};
use std::collections::HashSet;

pub fn parameters(parameters: Option<&Parameters>, work: &mut Work) -> Option<&'static str> {
    let parameters = parameters?;
    let mut seen = HashSet::new();
    for parameter in parameters.iter() {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if parameter.name().as_str() == "__debug__" {
            return Some("cannot bind __debug__");
        }
        if !seen.insert(parameter.name().as_str()) {
            return Some("duplicate parameter name");
        }
    }
    None
}

pub fn check(
    expr: &Expr,
    in_class: bool,
    debug_attribute: bool,
    minor: PyMinor,
    work: &mut Work,
) -> Option<&'static str> {
    let debug_attribute = match minor {
        PyMinor::Py311 | PyMinor::Py312 | PyMinor::Py313 => debug_attribute,
        PyMinor::Py314 => false,
    };
    if matches!(expr, Expr::Name(node) if node.id == "__debug__" && node.ctx != ExprContext::Load) {
        return Some("cannot bind __debug__");
    }
    if !debug_attribute
        && matches!(expr, Expr::Attribute(node) if node.attr.as_str() == "__debug__" && node.ctx != ExprContext::Load)
    {
        return Some("cannot bind __debug__");
    }
    if let Expr::Lambda(node) = expr {
        return parameters(node.parameters.as_deref(), work);
    }
    let (generators, values) = comprehension_parts(expr)?;
    comprehension(generators, &values, in_class, work)
}

pub fn comprehension_parts(expr: &Expr) -> Option<(&[Comprehension], Vec<&Expr>)> {
    Some(match expr {
        Expr::ListComp(node) => (&node.generators, vec![node.elt.as_ref()]),
        Expr::SetComp(node) => (&node.generators, vec![node.elt.as_ref()]),
        Expr::DictComp(node) => (
            &node.generators,
            node.key
                .as_deref()
                .into_iter()
                .chain(std::iter::once(node.value.as_ref()))
                .collect(),
        ),
        Expr::Generator(node) => (&node.generators, vec![node.elt.as_ref()]),
        _ => return None,
    })
}

pub fn target(expr: &Expr, sequence: bool, work: &mut Work, depth: usize) -> Option<&'static str> {
    if !work.charge(1) {
        return Some("CPython validation work limit exceeded");
    }
    if depth >= 1000 {
        return Some("CPython validation depth limit exceeded");
    }
    match expr {
        Expr::Starred(node) if sequence => target(&node.value, false, work, depth + 1),
        Expr::Starred(_) => Some("starred assignment target must be in a list or tuple"),
        Expr::Tuple(node) => targets(&node.elts, work, depth + 1),
        Expr::List(node) => targets(&node.elts, work, depth + 1),
        _ => None,
    }
}

pub fn assignment(items: &[Expr], work: &mut Work) -> Option<&'static str> {
    for item in items {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if let Some(reason) = target(item, false, work, 0) {
            return Some(reason);
        }
    }
    None
}

fn targets(items: &[Expr], work: &mut Work, depth: usize) -> Option<&'static str> {
    let mut stars = 0;
    for (index, item) in items.iter().enumerate() {
        if !work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        stars += usize::from(matches!(item, Expr::Starred(_)));
        if matches!(item, Expr::Starred(_)) && index >= 256 {
            return Some("too many expressions before a starred assignment target");
        }
        if let Some(reason) = target(item, true, work, depth) {
            return Some(reason);
        }
    }
    (stars > 1).then_some("multiple starred assignment targets")
}

fn comprehension(
    generators: &[Comprehension],
    values: &[&Expr],
    in_class: bool,
    work: &mut Work,
) -> Option<&'static str> {
    let mut check = ComprehensionCheck {
        work,
        targets: HashSet::new(),
        iteration: false,
        in_class,
        depth: 0,
        reason: None,
        allow_yield: false,
    };
    for generator in generators {
        if !check.work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        if let Some(reason) = target(&generator.target, false, check.work, 0) {
            return Some(reason);
        }
        let mut pending = vec![&generator.target];
        while let Some(target) = pending.pop() {
            if !check.work.charge(1) {
                return Some("CPython validation work limit exceeded");
            }
            match target {
                Expr::Name(node) => {
                    check.targets.insert(node.id.to_string());
                }
                Expr::Tuple(node) => pending.extend(&node.elts),
                Expr::List(node) => pending.extend(&node.elts),
                Expr::Starred(node) => pending.push(&node.value),
                _ => {}
            }
        }
    }
    for (index, generator) in generators.iter().enumerate() {
        if !check.work.charge(1) {
            return Some("CPython validation work limit exceeded");
        }
        check.iteration = true;
        check.allow_yield = index == 0;
        check.visit_expr(&generator.iter);
        check.iteration = false;
        check.allow_yield = false;
        for condition in &generator.ifs {
            if !check.work.charge(1) {
                return Some("CPython validation work limit exceeded");
            }
            check.visit_expr(condition);
        }
    }
    for value in values {
        check.visit_expr(value);
    }
    check.reason
}

struct ComprehensionCheck<'a> {
    work: &'a mut Work,
    targets: HashSet<String>,
    iteration: bool,
    in_class: bool,
    depth: usize,
    reason: Option<&'static str>,
    allow_yield: bool,
}

impl<'a> Visitor<'a> for ComprehensionCheck<'_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if self.reason.is_some() {
            return;
        }
        if !self.work.charge(1) {
            self.reason = Some("CPython validation work limit exceeded");
            return;
        }
        if self.depth >= 100 {
            self.reason = Some("CPython comprehension validation depth limit exceeded");
            return;
        }
        self.depth += 1;
        match expr {
            Expr::Yield(_) | Expr::YieldFrom(_) if !self.allow_yield => {
                self.reason = Some("yield inside a comprehension")
            }
            Expr::Named(node)
                if self.iteration
                    || self.in_class
                    || matches!(&*node.target, Expr::Name(node) if self.targets.contains(node.id.as_str())) =>
            {
                self.reason = Some("assignment expression conflicts with comprehension scope");
            }
            Expr::Name(node) if node.id == "__debug__" && node.ctx != ExprContext::Load => {
                self.reason = Some("cannot bind __debug__")
            }
            Expr::Lambda(_) if !self.iteration => {}
            _ => visitor::walk_expr(self, expr),
        }
        self.depth -= 1;
    }
}

pub fn grouped_star(source: &str, work: &mut Work) -> bool {
    use ruff_python_ast::token::TokenKind as T;
    let mut lexer = ruff_python_parser::lexer::lex(source, ruff_python_parser::Mode::Expression);
    let mut opened = false;
    let mut closed = false;
    let mut depth = 0usize;
    loop {
        if !work.charge(1) {
            return false;
        }
        let kind = lexer.next_token();
        if kind == T::EndOfFile {
            return opened && closed;
        }
        if kind.is_trivia() || kind.is_any_newline() {
            continue;
        }
        if closed {
            return false;
        }
        match kind {
            T::Star if !opened => {}
            T::Lpar => {
                opened = true;
                depth += 1;
            }
            T::Rpar => {
                depth = depth.saturating_sub(1);
                closed = depth == 0;
            }
            _ if !opened => return false,
            _ => {}
        }
    }
}

#[cfg(test)]
#[path = "expressioncheck_tests.rs"]
mod tests;
