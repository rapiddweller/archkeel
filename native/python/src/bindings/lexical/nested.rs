// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Synthetic type-parameter and comprehension scopes have their own visitation boundary.

use super::*;
use ruff_python_ast::{Comprehension, TypeParam, TypeParams};

impl<'a> Index<'a> {
    pub(super) fn type_parameters(
        &mut self,
        scan: &mut Scan,
        node: Node<'a>,
        params: Option<&TypeParams>,
        name: &str,
        parent: usize,
        range: TextRange,
    ) -> Result<usize> {
        let id = self.enter(scan, node, parent, Kind::Parameters, name, range)?;
        let loc = self.module.location(&range);
        self.scope_mut(id)?.qualified = scan.owner(
            &self.scope(parent)?.qualified,
            &format!("<type-parameters:{name}:{}:{}>", loc.line, loc.column),
        )?;
        self.scope_mut(id)?.table = false;
        if let Some(params) = params {
            for p in &params.type_params {
                scan.tick(1)?;
                let name = match p {
                    TypeParam::TypeVar(n) => &n.name,
                    TypeParam::ParamSpec(n) => &n.name,
                    TypeParam::TypeVarTuple(n) => &n.name,
                };
                self.scope_mut(id)?.blocked.insert(name.to_string());
            }
        }
        Ok(id)
    }

    #[allow(clippy::too_many_arguments)]
    pub(super) fn comprehension(
        &mut self,
        scan: &mut Scan,
        node: Node<'a>,
        generators: &'a [Comprehension],
        expressions: &[&'a Expr],
        scope: usize,
        conditional: bool,
        depth: usize,
        name: &str,
    ) -> Result<()> {
        let first = generators.first().ok_or("comprehension generator unseen")?;
        self.visit(
            scan,
            Node::Expr(&first.iter),
            scope,
            conditional,
            true,
            depth + 1,
        )?;
        let expr = node.expr().ok_or("comprehension expression unseen")?;
        let range = self.generator_range(scan, expr)?;
        let child = self.enter(scan, node.clone(), scope, Kind::Comprehension, name, range)?;
        for (i, g) in generators.iter().enumerate() {
            scan.tick(1)?;
            self.visit(
                scan,
                Node::Expr(&g.target),
                child,
                conditional,
                true,
                depth + 1,
            )?;
            if i > 0 {
                self.visit(
                    scan,
                    Node::Expr(&g.iter),
                    child,
                    conditional,
                    true,
                    depth + 1,
                )?;
            }
            for test in &g.ifs {
                scan.tick(1)?;
                self.visit(scan, Node::Expr(test), child, conditional, true, depth + 1)?;
            }
        }
        for expr in expressions {
            scan.tick(1)?;
            self.visit(scan, Node::Expr(expr), child, conditional, true, depth + 1)?;
        }
        Ok(())
    }
}
