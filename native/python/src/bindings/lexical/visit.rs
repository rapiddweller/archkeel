// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Lexical visitor order, distinct from the compiler's binding ownership.

use ruff_python_ast::{ExceptHandler, Pattern};

use super::*;

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
        match &node {
            Node::Stmt(stmt @ Stmt::FunctionDef(n)) => {
                return self.definition(scan, stmt, Def::Function(n), scope, conditional, depth)
            }
            Node::Stmt(stmt @ Stmt::ClassDef(n)) => {
                return self.definition(scan, stmt, Def::Class(n), scope, conditional, depth)
            }
            Node::Expr(Expr::Lambda(n)) => {
                self.visit(
                    scan,
                    Node::Arguments(n.parameters.as_deref()),
                    scope,
                    conditional,
                    compiled,
                    depth + 1,
                )?;
                let child =
                    self.enter(scan, node.clone(), scope, Kind::Function, "lambda", n.range)?;
                // Lambda has no symbol identity and uses a location-qualified scope name.
                let loc = self.module.location(n);
                self.scope_mut(child)?.qualified = scan.owner(
                    &self.scope(scope)?.qualified,
                    &format!("<lambda:{}:{}>", loc.line, loc.column),
                )?;
                self.scope_mut(child)?.identity = None;
                self.parameters(scan, n.parameters.as_deref(), child, conditional)?;
                return self.visit(
                    scan,
                    Node::Expr(&n.body),
                    child,
                    conditional,
                    compiled,
                    depth + 1,
                );
            }
            Node::Expr(Expr::ListComp(n)) => {
                return self.comprehension(
                    scan,
                    node.clone(),
                    &n.generators,
                    &[&n.elt],
                    scope,
                    conditional,
                    depth,
                    "listcomp",
                )
            }
            Node::Expr(Expr::SetComp(n)) => {
                return self.comprehension(
                    scan,
                    node.clone(),
                    &n.generators,
                    &[&n.elt],
                    scope,
                    conditional,
                    depth,
                    "setcomp",
                )
            }
            Node::Expr(Expr::Generator(n)) => {
                return self.comprehension(
                    scan,
                    node.clone(),
                    &n.generators,
                    &[&n.elt],
                    scope,
                    conditional,
                    depth,
                    "genexpr",
                )
            }
            Node::Expr(Expr::DictComp(n)) => {
                let key = n.key.as_deref().ok_or("dict comprehension key unseen")?;
                return self.comprehension(
                    scan,
                    node.clone(),
                    &n.generators,
                    &[key, &n.value],
                    scope,
                    conditional,
                    depth,
                    "dictcomp",
                );
            }
            Node::Stmt(Stmt::TypeAlias(n)) => {
                self.visit(
                    scan,
                    Node::Expr(&n.name),
                    scope,
                    conditional,
                    compiled,
                    depth + 1,
                )?;
                if n.type_params.is_none() {
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
                }
                let Expr::Name(name) = &*n.name else {
                    return Err("type alias name unseen".into());
                };
                let param = self.type_parameters(
                    scan,
                    node.clone(),
                    n.type_params.as_deref(),
                    name.id.as_str(),
                    scope,
                    n.range,
                )?;
                if let Some(params) = &n.type_params {
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
                }
                let alias = self.enter(
                    scan,
                    node.clone(),
                    scope,
                    Kind::Alias,
                    name.id.as_str(),
                    n.range,
                )?;
                let loc = self.module.location(n);
                self.scope_mut(alias)?.qualified = scan.owner(
                    &self.scope(scope)?.qualified,
                    &format!("<type-alias:{}:{}:{}>", name.id, loc.line, loc.column),
                )?;
                self.scope_mut(alias)?.blocked = self.scope(param)?.blocked.clone();
                if self.scope(scope)?.kind == Kind::Class {
                    self.scope_mut(alias)?.table = false;
                }
                return self.visit(
                    scan,
                    Node::Expr(&n.value),
                    alias,
                    conditional,
                    true,
                    depth + 1,
                );
            }
            Node::Expr(expr @ Expr::Name(n)) => {
                self.queries.push(Query { node: expr, scope });
                if compiled {
                    self.scope_mut(scope)?.seen.insert(n.id.to_string());
                }
                if n.ctx != ExprContext::Load {
                    self.add(scan, scope, n.id.as_str(), node.clone(), conditional)?;
                }
            }
            Node::Expr(Expr::Named(n)) => {
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
                // A walrus binds outside every comprehension, not to a synthetic local.
                if owner != scope {
                    if let Expr::Name(n) = &*n.target {
                        self.scope_mut(scope)?.locals.remove(n.id.as_str());
                    }
                }
                return self.visit(
                    scan,
                    Node::Expr(&n.value),
                    scope,
                    conditional,
                    compiled,
                    depth + 1,
                );
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
                return Ok(());
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
                return Ok(());
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
        for child in scan.children(&node)? {
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
            let local_annotation = matches!((&node, &child), (Node::Stmt(Stmt::AnnAssign(n)), Node::Expr(e)) if std::ptr::eq(&*n.annotation, *e));
            let skipped = (local_annotation || matches!(node, Node::Arg(_))) && self.future
                || local_annotation && self.scope(scope)?.kind == Kind::Function;
            let compiled = compiled && !skipped;
            let hidden = (local_annotation || matches!(node, Node::Arg(_)))
                && (skipped || scan.minor == PyMinor::Py314);
            self.hidden_tables += usize::from(hidden);
            let found = self.visit(
                scan,
                child,
                scope,
                conditional || branch,
                compiled,
                depth + 1,
            );
            self.hidden_tables -= usize::from(hidden);
            found?;
        }
        Ok(())
    }

    fn definition(
        &mut self,
        scan: &mut Scan,
        stmt: &'a Stmt,
        def: Def<'a>,
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        let (node, params) = match def {
            Def::Function(n) => (Node::Stmt(stmt), n.type_params.as_deref()),
            Def::Class(n) => (Node::Stmt(stmt), n.type_params.as_deref()),
        };
        self.add(scan, scope, def.name(), node.clone(), conditional)?;
        let generic = params.is_some();
        if generic {
            let header = self.type_parameters(
                scan,
                node.clone(),
                params,
                def.name(),
                scope,
                def.range(self.module.text()),
            )?;
            match def {
                Def::Function(n) => {
                    for d in &n.decorator_list {
                        scan.tick(1)?;
                        self.visit(
                            scan,
                            Node::Expr(&d.expression),
                            scope,
                            conditional,
                            true,
                            depth + 1,
                        )?;
                    }
                    for p in n.parameters.iter() {
                        scan.tick(1)?;
                        if let Some(default) = p.default() {
                            for item in scan.walk(Node::Expr(default))? {
                                scan.tick(1)?;
                                if let Node::Expr(Expr::BinOp(n)) = item {
                                    if n.op == ruff_python_ast::Operator::Mod {
                                        self.numeric.insert(self.module.location(n).line);
                                    }
                                }
                            }
                            self.visit(
                                scan,
                                Node::Expr(default),
                                scope,
                                conditional,
                                true,
                                depth + 1,
                            )?;
                        }
                        if let Some(annotation) = p.annotation() {
                            self.visit(
                                scan,
                                Node::Expr(annotation),
                                header,
                                conditional,
                                false,
                                depth + 1,
                            )?;
                        }
                    }
                    if let Some(r) = &n.returns {
                        self.visit(scan, Node::Expr(r), header, conditional, false, depth + 1)?;
                    }
                }
                Def::Class(n) => {
                    for d in &n.decorator_list {
                        scan.tick(1)?;
                        self.visit(
                            scan,
                            Node::Expr(&d.expression),
                            scope,
                            conditional,
                            true,
                            depth + 1,
                        )?;
                    }
                    if let Some(args) = &n.arguments {
                        for arg in &args.args {
                            scan.tick(1)?;
                            self.visit(
                                scan,
                                Node::Expr(arg),
                                header,
                                conditional,
                                false,
                                depth + 1,
                            )?;
                        }
                        for k in &args.keywords {
                            scan.tick(1)?;
                            self.visit(
                                scan,
                                Node::Expr(&k.value),
                                header,
                                conditional,
                                false,
                                depth + 1,
                            )?;
                        }
                    }
                }
            }
            if let Some(params) = params {
                for p in &params.type_params {
                    scan.tick(1)?;
                    self.visit(
                        scan,
                        Node::TypeParam(p),
                        header,
                        conditional,
                        false,
                        depth + 1,
                    )?;
                }
            }
        } else {
            for child in scan.children(&node)? {
                scan.tick(1)?;
                if matches!(child, Node::Stmt(_)) {
                    continue;
                }
                let compiled = !(matches!(child, Node::Expr(_))
                    && match def {
                        Def::Function(n) => {
                            n.returns.as_ref().is_some_and(
                                |r| matches!(&child, Node::Expr(e) if std::ptr::eq(&**r, *e)),
                            ) && self.future
                        }
                        Def::Class(_) => false,
                    });
                let annotation = matches!(child, Node::Expr(_))
                    && match def {
                        Def::Function(n) => n.returns.as_ref().is_some_and(
                            |r| matches!(&child, Node::Expr(e) if std::ptr::eq(&**r, *e)),
                        ),
                        Def::Class(_) => false,
                    };
                let hidden = annotation && (self.future || scan.minor == PyMinor::Py314);
                self.hidden_tables += usize::from(hidden);
                let found = self.visit(scan, child, scope, conditional, compiled, depth + 1);
                self.hidden_tables -= usize::from(hidden);
                found?;
            }
        }
        let kind = match def {
            Def::Function(_) => Kind::Function,
            Def::Class(_) => Kind::Class,
        };
        let child = self.enter(
            scan,
            node,
            scope,
            kind,
            def.name(),
            def.range(self.module.text()),
        )?;
        if generic {
            self.scope_mut(child)?.table = false;
        }
        if let Def::Function(n) = def {
            self.parameters(scan, Some(&n.parameters), child, conditional)?;
        }
        self.body(scan, def.body(), child, conditional, depth + 1)
    }
}
