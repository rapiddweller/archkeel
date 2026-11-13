// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Definition headers run in a different scope from their bodies.

use super::*;

fn return_annotation(def: Def<'_>, child: &Node<'_>) -> bool {
    match (def, child) {
        (Def::Function(n), Node::Expr(e)) => {
            n.returns.as_ref().is_some_and(|r| std::ptr::eq(&**r, *e))
        }
        _ => false,
    }
}

impl<'a> Index<'a> {
    pub(super) fn definition(
        &mut self,
        scan: &mut Scan,
        stmt: &'a Stmt,
        def: Def<'a>,
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        let node = Node::Stmt(stmt);
        let params = match def {
            Def::Function(n) => n.type_params.as_deref(),
            Def::Class(n) => n.type_params.as_deref(),
        };
        self.add(scan, scope, def.name(), node.clone(), conditional)?;
        if let Some(params) = params {
            let header = self.type_parameters(
                scan,
                node.clone(),
                Some(params),
                def.name(),
                scope,
                def.range(self.module.text()),
            )?;
            self.decorators(scan, def, scope, conditional, depth)?;
            match def {
                Def::Function(n) => {
                    self.function_header(scan, n, scope, header, conditional, depth)?
                }
                Def::Class(n) => self.class_header(scan, n, header, conditional, depth)?,
            }
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
        } else {
            self.ordinary_header(scan, &node, def, scope, conditional, depth)?;
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
        if params.is_some() {
            self.scope_mut(child)?.table = false;
        }
        if let Def::Function(n) = def {
            self.parameters(scan, Some(&n.parameters), child, conditional)?;
        }
        self.body(scan, def.body(), child, conditional, depth + 1)
    }

    fn decorators(
        &mut self,
        scan: &mut Scan,
        def: Def<'a>,
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        let decorators = match def {
            Def::Function(n) => &n.decorator_list,
            Def::Class(n) => &n.decorator_list,
        };
        for d in decorators {
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
        Ok(())
    }

    fn function_header(
        &mut self,
        scan: &mut Scan,
        n: &'a ruff_python_ast::StmtFunctionDef,
        scope: usize,
        header: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        for p in n.parameters.iter() {
            scan.tick(1)?;
            if let Some(default) = p.default() {
                self.generic_default(scan, default, scope, conditional, depth)?;
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
        Ok(())
    }

    fn generic_default(
        &mut self,
        scan: &mut Scan,
        default: &'a Expr,
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        for item in scan.walk(Node::Expr(default))? {
            scan.tick(1)?;
            match item {
                Node::Expr(Expr::BinOp(n)) if n.op == ruff_python_ast::Operator::Mod => {
                    self.numeric.insert(self.module.location(n).line);
                }
                _ => {}
            }
        }
        self.visit(
            scan,
            Node::Expr(default),
            scope,
            conditional,
            true,
            depth + 1,
        )
    }

    fn class_header(
        &mut self,
        scan: &mut Scan,
        n: &'a ruff_python_ast::StmtClassDef,
        header: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        let Some(args) = &n.arguments else {
            return Ok(());
        };
        for arg in &args.args {
            scan.tick(1)?;
            self.visit(scan, Node::Expr(arg), header, conditional, false, depth + 1)?;
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
        Ok(())
    }

    fn ordinary_header(
        &mut self,
        scan: &mut Scan,
        node: &Node<'a>,
        def: Def<'a>,
        scope: usize,
        conditional: bool,
        depth: usize,
    ) -> Result<()> {
        for child in scan.children(node)? {
            scan.tick(1)?;
            if matches!(child, Node::Stmt(_)) {
                continue;
            }
            let annotation = return_annotation(def, &child);
            let hidden = annotation && (self.future || scan.minor == PyMinor::Py314);
            self.hidden_tables += usize::from(hidden);
            let found = self.visit(
                scan,
                child,
                scope,
                conditional,
                !(annotation && self.future),
                depth + 1,
            );
            self.hidden_tables -= usize::from(hidden);
            found?;
        }
        Ok(())
    }
}
