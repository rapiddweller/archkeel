// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Call syntax and the lexical bindings that can hide a module function.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::visit::{self, Visit};
use syn::{Expr, ImplItem, Item, PathArguments};

use super::receivers::{exact_path, inert, kind_of, module_inert};
use super::state::Walker;
use crate::attrs::{is_test_attributes, item_attributes, statement_attributes};
use crate::definitions::{Call, Calls, SelfKind, SelfMethod};
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
        if matches!(item, Item::Impl(item) if self.inherent(item)) {
            return;
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
        self.emit(&body, owner, None);
    }

    fn inherent(&mut self, item: &syn::ItemImpl) -> bool {
        if self.gated
            || item.trait_.is_some()
            || item.generics.where_clause.is_some()
            || !item.generics.params.is_empty()
            || item
                .items
                .iter()
                .any(|member| !matches!(member, ImplItem::Fn(_) | ImplItem::Const(_)))
        {
            return false;
        }
        let Some(path) = exact_path(item) else {
            return false;
        };
        let [ty] = path.as_slice() else {
            return false;
        };
        for member in &item.items {
            let mut body = Body {
                exclude_tests: self.walker.exclude_tests,
                impl_member: true,
                ..Body::default()
            };
            body.visit_impl_item(member);
            let context = match member {
                ImplItem::Fn(method) if !body.gated && !body.local_items => {
                    method_kind(method).map(|kind| (ty.as_str(), method, kind, item))
                }
                _ => None,
            };
            self.emit(&body, None, context);
        }
        true
    }

    fn emit(
        &mut self,
        body: &Body,
        owner: Option<String>,
        inherent: Option<(&str, &syn::ImplItemFn, SelfKind, &syn::ItemImpl)>,
    ) {
        let impl_reason = body
            .impl_member
            .then_some("The call is in a nested callable or item");
        for site in &body.sites {
            let self_method = inherent.and_then(|(ty, source, kind, item)| {
                let arity = site.self_arity?;
                let target = same_receiver(item, &site.expression, kind, arity)?;
                Some(SelfMethod {
                    type_name: ty.to_owned(),
                    source: self.walker.site(source.sig.ident.span()),
                    target: self.walker.site(target.sig.ident.span()),
                })
            });
            let reason = if self_method.is_some() {
                None
            } else {
                site.reason
                    .or(impl_reason)
                    .or_else(|| body.limit(owner.is_some(), &site.path))
            };
            self.out.sites.push(Call {
                scope: self.scope.clone(),
                owner: owner.clone(),
                path: site.path.clone(),
                expression: site.expression.clone(),
                site: self.walker.site(site.span),
                end_column: i64::try_from(site.span.end().column).unwrap_or(i64::MAX),
                reason,
                self_method,
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

fn method_kind(method: &syn::ImplItemFn) -> Option<SelfKind> {
    if !inert(&method.attrs)
        || !method.sig.generics.params.is_empty()
        || method.sig.generics.where_clause.is_some()
    {
        return None;
    }
    kind_of(&method.sig)
}

fn same_receiver<'a>(
    item: &'a syn::ItemImpl,
    name: &str,
    kind: SelfKind,
    arity: usize,
) -> Option<&'a syn::ImplItemFn> {
    let mut candidates = item.items.iter().filter_map(|member| match member {
        ImplItem::Fn(method) if method.sig.ident == name => Some(method),
        _ => None,
    });
    let method = candidates.next()?;
    // A match at the exact receiver step wins before further borrowing or dereferencing.
    (candidates.next().is_none()
        && method_kind(method) == Some(kind)
        && method.sig.inputs.len().saturating_sub(1) == arity)
        .then_some(method)
}

fn plain_self(expr: &Expr) -> bool {
    matches!(expr, Expr::Path(path) if path.attrs.is_empty()
        && path.qself.is_none() && path.path.is_ident("self"))
}

struct Written {
    span: Span,
    expression: String,
    path: Vec<String>,
    reason: Option<&'static str>,
    self_arity: Option<usize>,
}

#[derive(Default)]
struct Body {
    sites: Vec<Written>,
    names: BTreeSet<String>,
    local_items: bool,
    impl_member: bool,
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
        if path.first().is_some_and(|name| {
            !matches!(name.as_str(), "crate" | "self" | "super")
                && (self.local_items || self.names.contains(name))
        }) {
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
        self_arity: Option<usize>,
    ) {
        let deferred = self
            .deferred
            .then_some("The call is in a nested callable or item");
        self.sites.push(Written {
            span,
            expression,
            path,
            reason: reason.or(deferred),
            self_arity: self_arity.filter(|_| !self.deferred),
        });
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

    fn visit_type_param(&mut self, param: &'ast syn::TypeParam) {
        self.names.insert(plain(&param.ident));
        visit::visit_type_param(self, param);
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
        self.site(
            call.paren_token.span.join(),
            callee.0,
            callee.1,
            callee.2,
            None,
        );
        visit::visit_expr_call(self, call);
    }

    fn visit_expr_method_call(&mut self, call: &'ast syn::ExprMethodCall) {
        self.site(
            call.method.span(),
            plain(&call.method),
            Vec::new(),
            Some("Method dispatch is outside local function resolution"),
            (call.turbofish.is_none() && plain_self(&call.receiver)).then_some(call.args.len()),
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
            None,
        );
    }
}
