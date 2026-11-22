// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The uses of one dict in the body of one function (AD-530): which of them are a lookup of a
//! literal key, and which hand the dict to a callee that the proof can follow.

use std::collections::HashSet;

use ruff_python_ast::visitor::{self, Visitor};
use ruff_python_ast::{CmpOp, Expr, ExprContext, Stmt, StmtFunctionDef};
use ruff_text_size::{Ranged, TextRange};

use super::globals_locals::Locals;
use super::globals_project::{Callee, Project, DEPTH};
use super::hazards_names::TROJAN_HORSE_STRINGS;

impl Project<'_> {
    /// True when the parameter `param` of the scan function `def` is used in inert forms only.
    pub(super) fn parameter_inert(
        &self,
        owner: &str,
        def: &StmtFunctionDef,
        param: &str,
        path: &mut Vec<(String, String, String)>,
    ) -> bool {
        let key = (owner.to_owned(), def.name.to_string(), param.to_owned());
        if path.len() >= DEPTH || path.contains(&key) {
            return false;
        }
        let local = Locals::of(def);
        if local.written(param) || local.declared.contains(param) {
            return false;
        }
        path.push(key);
        let inert = self.uses_inert(owner, &def.body, Target::Name(param), &local, path);
        path.pop();
        inert
    }

    /// True when each use of the target in `body` is inert.
    pub(super) fn uses_inert(
        &self,
        module: &str,
        body: &[Stmt],
        target: Target,
        local: &Locals,
        path: &mut Vec<(String, String, String)>,
    ) -> bool {
        let mut uses = Uses {
            project: self,
            module,
            target,
            local,
            path,
            seen: HashSet::new(),
            allowed: HashSet::new(),
        };
        uses.visit_body(body);
        !uses.seen.is_empty() && uses.seen == uses.allowed
    }
}

/// The names of the one dict that a proof follows.
#[derive(Clone, Copy)]
pub(super) enum Target<'t> {
    /// Each load of a name.
    Name(&'t str),
    /// One source expression, by its range.
    Source(TextRange),
}

impl Target<'_> {
    fn is(&self, expr: &Expr) -> bool {
        match self {
            Target::Name(name) => {
                matches!(expr, Expr::Name(node) if node.id.as_str() == *name && node.ctx == ExprContext::Load)
            }
            Target::Source(range) => expr.range() == *range,
        }
    }
}

/// The uses of one target in the body of one function.
struct Uses<'p, 'm, 'f> {
    project: &'p Project<'m>,
    module: &'p str,
    target: Target<'p>,
    local: &'p Locals<'f>,
    path: &'p mut Vec<(String, String, String)>,
    /// The ranges of each load of the target, and of each load in an inert form.
    seen: HashSet<TextRange>,
    allowed: HashSet<TextRange>,
}

impl Uses<'_, '_, '_> {
    /// True for a string literal that is no trojan horse.
    fn plain_key(expr: &Expr) -> bool {
        matches!(expr, Expr::StringLiteral(text) if !TROJAN_HORSE_STRINGS.contains(&text.value.to_str()))
    }

    /// The loads of the target that the expression `expr` uses in an inert form.
    fn consume(&mut self, expr: &Expr) {
        match expr {
            Expr::Call(call) => {
                self.lookup(call);
                self.arguments(call);
            }
            Expr::Subscript(node)
                if node.ctx == ExprContext::Load
                    && self.target.is(&node.value)
                    && Self::plain_key(&node.slice) =>
            {
                self.allowed.insert(node.value.range());
            }
            Expr::Compare(node) => self.membership(node),
            _ => {}
        }
    }

    /// `d.get("key")` with one literal key that is no trojan horse.
    fn lookup(&mut self, call: &ruff_python_ast::ExprCall) {
        let args = &call.arguments;
        let Expr::Attribute(method) = &*call.func else {
            return;
        };
        let get = method.attr.as_str() == "get"
            && self.target.is(&method.value)
            && matches!(args.args.first(), Some(key) if Self::plain_key(key))
            && args.args.len() <= 2
            && args.keywords.is_empty();
        if get {
            self.allowed.insert(method.value.range());
        }
    }

    /// `"key" in d` with a literal key that is no trojan horse.
    fn membership(&mut self, node: &ruff_python_ast::ExprCompare) {
        let ([CmpOp::In | CmpOp::NotIn], [left, right]) = (&*node.ops, &*node.operands) else {
            return;
        };
        if Self::plain_key(left) && self.target.is(right) {
            self.allowed.insert(right.range());
        }
    }

    /// Each argument of a call that is the target: inert when the callee is.
    fn arguments(&mut self, call: &ruff_python_ast::ExprCall) {
        let callee = self.project.callee(self.module, &call.func, self.local);
        for (index, arg) in call.arguments.args.iter().enumerate() {
            if self.target.is(arg) && self.passes(&callee, Some(index), None) {
                self.allowed.insert(arg.range());
            }
        }
        for keyword in &call.arguments.keywords {
            let name = keyword.arg.as_ref().map(|n| n.as_str());
            if name.is_some() && self.target.is(&keyword.value) && self.passes(&callee, None, name)
            {
                self.allowed.insert(keyword.value.range());
            }
        }
    }

    fn passes(&mut self, callee: &Callee, index: Option<usize>, name: Option<&str>) -> bool {
        match callee {
            Callee::External => true,
            Callee::Unknown => false,
            Callee::Scan(owner, def) => {
                let parameters = &def.parameters;
                let positional: Vec<&str> = parameters
                    .posonlyargs
                    .iter()
                    .chain(&parameters.args)
                    .map(|p| p.parameter.name.as_str())
                    .collect();
                let keyword = parameters
                    .kwonlyargs
                    .iter()
                    .map(|p| p.parameter.name.as_str());
                let param = match (index, name) {
                    (Some(at), _) => positional.get(at).copied(),
                    (None, Some(given)) => positional
                        .iter()
                        .copied()
                        .chain(keyword)
                        .find(|candidate| *candidate == given),
                    (None, None) => None,
                };
                param
                    .is_some_and(|param| self.project.parameter_inert(owner, def, param, self.path))
            }
        }
    }
}

impl<'a> Visitor<'a> for Uses<'_, '_, '_> {
    fn visit_expr(&mut self, expr: &'a Expr) {
        if self.target.is(expr) {
            self.seen.insert(expr.range());
        }
        self.consume(expr);
        visitor::walk_expr(self, expr);
    }
}
