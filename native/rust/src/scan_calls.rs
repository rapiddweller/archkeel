// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Call syntax and the lexical bindings that can hide a module function.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::visit::{self, Visit};
use syn::{Expr, Item, PathArguments};

use super::receivers::{inert, module_inert};
use super::state::Walker;
use crate::attrs::{is_test_attributes, item_attributes, statement_attributes};
use crate::definitions::{Call, Calls};
use crate::tokens::plain;

pub(super) fn read(walker: &Walker<'_>, file: &syn::File) -> Calls {
    let mut reader = Reader {
        walker,
        scope: Vec::new(),
        gated: !module_inert(&file.attrs),
        out: Calls::default(),
    };
    reader.items(&file.items);
    reader.out
}

struct Reader<'a, 'text> {
    walker: &'a Walker<'text>,
    scope: Vec<String>,
    gated: bool,
    out: Calls,
}

impl Reader<'_, '_> {
    fn items(&mut self, items: &[Item]) {
        for item in items {
            self.item(item);
        }
    }

    fn item(&mut self, item: &Item) {
        let attrs = item_attributes(item);
        if self.walker.exclude_tests && is_test_attributes(attrs) {
            return;
        }
        if let Item::Mod(module) = item {
            return self.module(module);
        }
        let mut body = Body {
            exclude_tests: self.walker.exclude_tests,
            gated: self.gated || !inert(attrs),
            ..Body::default()
        };
        let owner = match item {
            Item::Fn(function) => {
                let name = plain(&function.sig.ident);
                if !body.gated {
                    self.out
                        .functions
                        .insert((self.scope.clone(), name.clone()));
                }
                body.visit_item_fn(function);
                Some(name)
            }
            _ => {
                body.visit_item(item);
                None
            }
        };
        for (span, expression, path, reason) in &body.sites {
            self.out.sites.push(Call {
                scope: self.scope.clone(),
                owner: owner.clone(),
                path: path.clone(),
                expression: expression.clone(),
                site: self.walker.site(*span),
                end_column: i64::try_from(span.end().column).unwrap_or(i64::MAX),
                reason: reason.or_else(|| body.limit(owner.is_some(), path)),
            });
        }
    }

    fn module(&mut self, module: &syn::ItemMod) {
        let Some((_, items)) = &module.content else {
            return;
        };
        let outer = self.gated;
        self.gated |= !module_inert(&module.attrs);
        self.scope.push(plain(&module.ident));
        self.items(items);
        self.scope.pop();
        self.gated = outer;
    }
}

type Written = (Span, String, Vec<String>, Option<&'static str>);

#[derive(Default)]
struct Body {
    sites: Vec<Written>,
    names: BTreeSet<String>,
    local_items: bool,
    gated: bool,
    deferred: bool,
    exclude_tests: bool,
}

impl Body {
    fn limit(&self, has_owner: bool, path: &[String]) -> Option<&'static str> {
        if self.gated {
            return Some("An attribute can remove or change the call");
        }
        if !has_owner {
            return Some("The call is outside a module function");
        }
        if matches!(path, [name] if self.local_items || self.names.contains(name)) {
            return Some("A lexical binding can hide the function");
        }
        None
    }

    fn site(
        &mut self,
        span: Span,
        expression: String,
        path: Vec<String>,
        reason: Option<&'static str>,
    ) {
        let deferred = self
            .deferred
            .then_some("The call is in a nested callable or item");
        self.sites
            .push((span, expression, path, reason.or(deferred)));
    }
}

impl<'ast> Visit<'ast> for Body {
    fn visit_attribute(&mut self, attr: &'ast syn::Attribute) {
        self.gated |= !inert(std::slice::from_ref(attr));
    }

    fn visit_pat_ident(&mut self, pat: &'ast syn::PatIdent) {
        self.names.insert(plain(&pat.ident));
        visit::visit_pat_ident(self, pat);
    }

    fn visit_const_param(&mut self, param: &'ast syn::ConstParam) {
        self.names.insert(plain(&param.ident));
        visit::visit_const_param(self, param);
    }

    fn visit_item(&mut self, item: &'ast Item) {
        if self.exclude_tests && is_test_attributes(item_attributes(item)) {
            return;
        }
        self.local_items = true;
        let prior = std::mem::replace(&mut self.deferred, true);
        visit::visit_item(self, item);
        self.deferred = prior;
    }

    fn visit_stmt(&mut self, stmt: &'ast syn::Stmt) {
        if self.exclude_tests && is_test_attributes(statement_attributes(stmt)) {
            return;
        }
        self.local_items |= matches!(stmt, syn::Stmt::Macro(_));
        visit::visit_stmt(self, stmt);
    }

    fn visit_expr_closure(&mut self, expr: &'ast syn::ExprClosure) {
        let prior = std::mem::replace(&mut self.deferred, true);
        visit::visit_expr_closure(self, expr);
        self.deferred = prior;
    }

    fn visit_expr_async(&mut self, expr: &'ast syn::ExprAsync) {
        let prior = std::mem::replace(&mut self.deferred, true);
        visit::visit_expr_async(self, expr);
        self.deferred = prior;
    }

    fn visit_expr_call(&mut self, call: &'ast syn::ExprCall) {
        let callee = match call.func.as_ref() {
            Expr::Path(path)
                if path.qself.is_none()
                    && path.path.leading_colon.is_none()
                    && path
                        .path
                        .segments
                        .iter()
                        .all(|s| matches!(s.arguments, PathArguments::None)) =>
            {
                let names: Vec<_> = path.path.segments.iter().map(|s| plain(&s.ident)).collect();
                (names.join("::"), names, None)
            }
            _ => (
                "<call>".to_owned(),
                Vec::new(),
                Some("The callee is not a simple function path"),
            ),
        };
        self.site(call.paren_token.span.join(), callee.0, callee.1, callee.2);
        visit::visit_expr_call(self, call);
    }

    fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
        self.site(
            call.method.span(),
            plain(&call.method),
            Vec::new(),
            Some("Method dispatch is outside local function resolution"),
        );
        visit::visit_expr_method_call(self, call);
    }

    fn visit_item_macro(&mut self, item: &'ast syn::ItemMacro) {
        if item.ident.is_none() {
            visit::visit_item_macro(self, item);
        }
    }

    fn visit_macro(&mut self, call: &'ast syn::Macro) {
        let path: Vec<_> = call.path.segments.iter().map(|s| plain(&s.ident)).collect();
        self.site(
            call.delimiter.span().join(),
            format!("{}!", path.join("::")),
            Vec::new(),
            Some("Macro expansion can contain calls that are not read"),
        );
    }
}
