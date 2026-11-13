// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Lexical visitation is separate from compiler name ownership.

use super::*;
use ruff_python_ast::{ExceptHandler, Pattern};

impl<'a> Index<'a> {
    pub(super) fn visit(
        &mut self,
        scan: &mut Scan,
        node: Node<'a>,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<()> {
        scan.tick(1)?;
        if depth > 100 {
            return Err("lexical depth limit exceeded (100 levels)".into());
        }
        self.touched.insert(scope);
        self.record_node(scan, &node, scope)?;
        if self.scope_node(scan, &node, scope, conditional, compiled, depth)? {
            return Ok(());
        }
        if let Node::Expr(Expr::Named(n)) = &node {
            return self.named(scan, n, scope, conditional, compiled, depth);
        }
        self.binding_node(scan, &node, scope, conditional, compiled)?;
        self.visit_children(scan, &node, scope, conditional, compiled, depth)
    }

    fn record_node(&mut self, scan: &mut Scan, node: &Node<'a>, scope: usize) -> Result<()> {
        if let Node::Expr(expr @ Expr::Generator(_)) = node {
            self.generator_range(scan, expr)?;
        }
        if let Some(site) = self.located_site(node) {
            self.nodes.push((site, scope));
            self.by_site.insert((site.0, site.1, site.3), scope);
        }
        Ok(())
    }

    fn scope_node(
        &mut self,
        scan: &mut Scan,
        node: &Node<'a>,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<bool> {
        match node {
            Node::Stmt(stmt @ Stmt::FunctionDef(n)) => {
                self.definition(scan, stmt, Def::Function(n), scope, conditional, depth)?
            }
            Node::Stmt(stmt @ Stmt::ClassDef(n)) => {
                self.definition(scan, stmt, Def::Class(n), scope, conditional, depth)?
            }
            Node::Stmt(stmt @ Stmt::TypeAlias(_)) => {
                self.type_alias(scan, stmt, scope, conditional, compiled, depth)?
            }
            Node::Expr(expr @ Expr::Lambda(_)) => {
                self.lambda(scan, expr, scope, conditional, compiled, depth)?
            }
            Node::Expr(Expr::ListComp(n)) => self.comprehension(
                scan,
                node.clone(),
                &n.generators,
                &[&n.elt],
                scope,
                conditional,
                depth,
                "listcomp",
            )?,
            Node::Expr(Expr::SetComp(n)) => self.comprehension(
                scan,
                node.clone(),
                &n.generators,
                &[&n.elt],
                scope,
                conditional,
                depth,
                "setcomp",
            )?,
            Node::Expr(Expr::Generator(n)) => self.comprehension(
                scan,
                node.clone(),
                &n.generators,
                &[&n.elt],
                scope,
                conditional,
                depth,
                "genexpr",
            )?,
            Node::Expr(Expr::DictComp(n)) => {
                let key = n.key.as_deref().ok_or("dict comprehension key unseen")?;
                self.comprehension(
                    scan,
                    node.clone(),
                    &n.generators,
                    &[key, &n.value],
                    scope,
                    conditional,
                    depth,
                    "dictcomp",
                )?;
            }
            _ => return Ok(false),
        }
        Ok(true)
    }

    fn lambda(
        &mut self,
        scan: &mut Scan,
        expr: &'a Expr,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<()> {
        let Expr::Lambda(n) = expr else {
            return Err("lambda expression unseen".into());
        };
        self.visit(
            scan,
            Node::Arguments(n.parameters.as_deref()),
            scope,
            conditional,
            compiled,
            depth + 1,
        )?;
        let child = self.enter(
            scan,
            Node::Expr(expr),
            scope,
            Kind::Function,
            "lambda",
            n.range,
        )?;
        let loc = self.module.location(n);
        self.scope_mut(child)?.qualified = scan.owner(
            &self.scope(scope)?.qualified,
            &format!("<lambda:{}:{}>", loc.line, loc.column),
        )?;
        self.scope_mut(child)?.identity = None;
        self.parameters(scan, n.parameters.as_deref(), child, conditional)?;
        self.visit(
            scan,
            Node::Expr(&n.body),
            child,
            conditional,
            compiled,
            depth + 1,
        )
    }

    fn type_alias(
        &mut self,
        scan: &mut Scan,
        stmt: &'a Stmt,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<()> {
        let Stmt::TypeAlias(n) = stmt else {
            return Err("type alias statement unseen".into());
        };
        let node = Node::Stmt(stmt);
        self.visit(
            scan,
            Node::Expr(&n.name),
            scope,
            conditional,
            compiled,
            depth + 1,
        )?;
        let Some(params) = n.type_params.as_deref() else {
            self.hidden_tables += 1;
            let found = self.visit(
                scan,
                Node::Expr(&n.value),
                scope,
                conditional,
                compiled,
                depth + 1,
            );
            self.hidden_tables -= 1;
            return found;
        };
        let Expr::Name(name) = &*n.name else {
            return Err("type alias name unseen".into());
        };
        let param = self.type_parameters(
            scan,
            node.clone(),
            Some(params),
            name.id.as_str(),
            scope,
            n.range,
        )?;
        for p in &params.type_params {
            scan.tick(1)?;
            self.visit(
                scan,
                Node::TypeParam(p),
                param,
                conditional,
                false,
                depth + 1,
            )?;
        }
        let alias = self.enter(scan, node, scope, Kind::Alias, name.id.as_str(), n.range)?;
        let loc = self.module.location(n);
        self.scope_mut(alias)?.qualified = scan.owner(
            &self.scope(scope)?.qualified,
            &format!("<type-alias:{}:{}:{}>", name.id, loc.line, loc.column),
        )?;
        self.scope_mut(alias)?.blocked = self.scope(param)?.blocked.clone();
        if self.scope(scope)?.kind == Kind::Class {
            self.scope_mut(alias)?.table = false;
        }
        self.visit(
            scan,
            Node::Expr(&n.value),
            alias,
            conditional,
            true,
            depth + 1,
        )
    }

    fn named(
        &mut self,
        scan: &mut Scan,
        n: &'a ruff_python_ast::ExprNamed,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<()> {
        let mut owner = scope;
        while self.scope(owner)?.kind == Kind::Comprehension {
            scan.tick(1)?;
            owner = self
                .scope(owner)?
                .parent
                .ok_or("comprehension parent unseen")?;
        }
        if let Expr::Name(n) = &*n.target {
            scan.tick(n.id.len())?;
            self.scope_mut(owner)?.locals.insert(n.id.to_string());
            self.scope_mut(owner)?.seen.insert(n.id.to_string());
        }
        self.visit(
            scan,
            Node::Expr(&n.target),
            scope,
            conditional,
            compiled,
            depth + 1,
        )?;
        if let Expr::Name(target) = &*n.target {
            if owner != scope {
                self.scope_mut(scope)?.locals.remove(target.id.as_str());
            }
        }
        self.visit(
            scan,
            Node::Expr(&n.value),
            scope,
            conditional,
            compiled,
            depth + 1,
        )
    }

    fn binding_node(
        &mut self,
        scan: &mut Scan,
        node: &Node<'a>,
        scope: usize,
        conditional: bool,
        compiled: bool,
    ) -> Result<()> {
        match node {
            Node::Expr(expr @ Expr::Name(n)) => {
                self.queries.push(Query { node: expr, scope });
                if compiled {
                    self.scope_mut(scope)?.seen.insert(n.id.to_string());
                }
                if n.ctx != ExprContext::Load {
                    self.add(scan, scope, n.id.as_str(), node.clone(), conditional)?;
                }
            }
            Node::Stmt(Stmt::Global(n)) => {
                for name in &n.names {
                    scan.tick(1)?;
                    self.scope_mut(scope)?.globals.insert(name.to_string());
                }
            }
            Node::Stmt(Stmt::Nonlocal(n)) => {
                for name in &n.names {
                    scan.tick(1)?;
                    self.scope_mut(scope)?.nonlocals.insert(name.to_string());
                }
            }
            Node::Stmt(Stmt::Import(n)) => {
                for alias in &n.names {
                    scan.tick(1)?;
                    let name = alias.asname.as_ref().map_or_else(
                        || crate::module::first_part(alias.name.as_str()),
                        |n| n.as_str(),
                    );
                    self.add(scan, scope, name, node.clone(), conditional)?;
                }
            }
            Node::Stmt(Stmt::ImportFrom(n)) => {
                for alias in &n.names {
                    scan.tick(1)?;
                    self.add(
                        scan,
                        scope,
                        alias.asname.as_ref().unwrap_or(&alias.name).as_str(),
                        node.clone(),
                        conditional,
                    )?;
                }
            }
            Node::Handler(ExceptHandler::ExceptHandler(n)) => {
                if let Some(name) = &n.name {
                    self.add(scan, scope, name.as_str(), node.clone(), conditional)?;
                }
            }
            Node::Pattern(p) => {
                let name = match p {
                    Pattern::MatchAs(n) => n.name.as_ref(),
                    Pattern::MatchStar(n) => n.name.as_ref(),
                    Pattern::MatchMapping(n) => n.rest.as_ref(),
                    _ => None,
                };
                if let Some(name) = name {
                    self.add(scan, scope, name.as_str(), node.clone(), conditional)?;
                }
            }
            _ => {}
        }
        Ok(())
    }

    fn visit_children(
        &mut self,
        scan: &mut Scan,
        node: &Node<'a>,
        scope: usize,
        conditional: bool,
        compiled: bool,
        depth: usize,
    ) -> Result<()> {
        if matches!(node, Node::Stmt(Stmt::Import(_) | Stmt::ImportFrom(_))) {
            return Ok(());
        }
        for child in scan.children(node)? {
            scan.tick(1)?;
            let branch = matches!(
                node,
                Node::Stmt(
                    Stmt::If(_)
                        | Stmt::For(_)
                        | Stmt::While(_)
                        | Stmt::With(_)
                        | Stmt::Try(_)
                        | Stmt::Match(_)
                ) | Node::Elif(_)
            ) && matches!(
                child,
                Node::Stmt(_) | Node::Elif(_) | Node::Handler(_) | Node::MatchCase(_)
            );
            let local_annotation = matches!((node,&child),(Node::Stmt(Stmt::AnnAssign(n)),Node::Expr(e)) if std::ptr::eq(&*n.annotation,*e));
            let skipped = (local_annotation || matches!(node, Node::Arg(_))) && self.future
                || local_annotation && self.scope(scope)?.kind == Kind::Function;
            let hidden = (local_annotation || matches!(node, Node::Arg(_)))
                && (skipped || scan.minor == PyMinor::Py314);
            self.hidden_tables += usize::from(hidden);
            let found = self.visit(
                scan,
                child,
                scope,
                conditional || branch,
                compiled && !skipped,
                depth + 1,
            );
            self.hidden_tables -= usize::from(hidden);
            found?;
        }
        Ok(())
    }
}
