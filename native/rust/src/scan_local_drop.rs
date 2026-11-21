// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Block-local `Drop` guards that cannot escape their enclosing synchronous function.
//!
//! A `struct Local` declared inside a synchronous `fn` body with `impl Drop for Local` in the same
//! block cannot be dropped by an erased value origin in another module when every instance is
//! bound directly by `let` in that block, never escapes into a return value, closure, `async`
//! state machine, `unsafe` block, macro, or call other than `drop`, and no other `impl` or item in
//! the block mentions `Local`.

use std::collections::BTreeSet;

use proc_macro2::{TokenStream, TokenTree};
use syn::{
    Attribute, Block, Expr, ExprArray, ExprBlock, ExprBreak, ExprContinue, ExprLit, ExprLoop,
    ExprReturn, ExprTuple, File, Ident, ImplItem, Item, ItemImpl, Pat, PatParen, PatReference,
    PatRest, PatSlice, PatTuple, PatWild, Path, Signature, Stmt, TraitItem, Type, TypeGroup,
    TypeParen, TypeReference, TypeSlice,
};

use crate::std_macros;
use crate::tokens::plain;

type Inert = fn(&[Attribute]) -> bool;

/// The `(line, column)` sites of `impl Drop` blocks proven never to escape their enclosing
/// synchronous function body.
pub(super) fn non_escaping(file: &File, drop_safe: bool, inert: Inert) -> BTreeSet<(i64, i64)> {
    let mut sites = BTreeSet::new();
    walk_items(&file.items, drop_safe, inert, &mut sites);
    sites
}

fn walk_items(items: &[Item], drop_safe: bool, inert: Inert, sites: &mut BTreeSet<(i64, i64)>) {
    let visit = |sig: &Signature, attrs: &[Attribute], body: &Block, sites: &mut _| {
        if sig.asyncness.is_none() && inert(attrs) {
            check_block(body, drop_safe, inert, sites);
        }
    };
    for item in items {
        match item {
            Item::Fn(f) => visit(&f.sig, &f.attrs, &f.block, sites),
            Item::Impl(b) if inert(&b.attrs) => b.items.iter().for_each(|m| {
                if let ImplItem::Fn(f) = m {
                    visit(&f.sig, &f.attrs, &f.block, sites);
                }
            }),
            Item::Trait(b) if inert(&b.attrs) => b.items.iter().for_each(|m| {
                if let TraitItem::Fn(f) = m {
                    f.default
                        .iter()
                        .for_each(|body| visit(&f.sig, &f.attrs, body, sites));
                }
            }),
            Item::Mod(m) if inert(&m.attrs) => {
                if let Some((_, inner)) = &m.content {
                    walk_items(inner, drop_safe, inert, sites);
                }
            }
            _ => {}
        }
    }
}

fn check_block(block: &Block, drop_safe: bool, inert: Inert, sites: &mut BTreeSet<(i64, i64)>) {
    for (impl_idx, stmt) in block.stmts.iter().enumerate() {
        let Stmt::Item(Item::Impl(impl_item)) = stmt else {
            continue;
        };
        let Some(local_name) = plain_drop_target(impl_item, inert) else {
            continue;
        };
        if block_proves_local(block, impl_idx, &local_name, drop_safe, inert) {
            let start = impl_item.impl_token.span.start();
            sites.insert((
                i64::try_from(start.line).unwrap_or(i64::MAX),
                i64::try_from(start.column).unwrap_or(i64::MAX),
            ));
        }
    }
}

fn plain_drop_target(item: &ItemImpl, inert: Inert) -> Option<String> {
    let ok = inert(&item.attrs)
        && item.generics.params.is_empty()
        && item.generics.where_clause.is_none();
    let (trait_path, _) = ok.then_some(item.trait_.as_ref()).flatten()?;
    let Type::Path(ty) = &*item.self_ty else {
        return None;
    };
    (is_drop_trait(trait_path) && ty.qself.is_none() && ty.path.leading_colon.is_none())
        .then(|| ty.path.get_ident().map(plain))
        .flatten()
}

fn is_drop_trait(path: &Path) -> bool {
    let names: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
    matches!(
        names.as_slice(),
        [a] if a == "Drop"
    ) || matches!(names.as_slice(), [a, b, c] if matches!(a.as_str(), "std" | "core") && b == "ops" && c == "Drop")
}

fn local_decl_index(
    block: &Block,
    impl_idx: usize,
    local_name: &str,
    inert: Inert,
) -> Option<usize> {
    let mut decl_idx = None;
    for (idx, stmt) in block.stmts.iter().enumerate() {
        let Stmt::Item(item) = stmt else {
            continue;
        };
        if idx == impl_idx {
            continue;
        }
        let (ident, attrs, generics) = match item {
            Item::Struct(s) => (&s.ident, &s.attrs, &s.generics),
            Item::Enum(e) => (&e.ident, &e.attrs, &e.generics),
            Item::Union(u) => (&u.ident, &u.attrs, &u.generics),
            // Refuse local `use`, `macro`, `static`, other `impl`, or nested items conservatively.
            _ => return None,
        };
        let valid = plain(ident) == local_name
            && decl_idx.is_none()
            && inert(attrs)
            && generics.params.is_empty()
            && generics.where_clause.is_none();
        if !valid {
            return None;
        }
        decl_idx = Some(idx);
    }
    decl_idx
}

fn block_proves_local(
    block: &Block,
    impl_idx: usize,
    local_name: &str,
    drop_safe: bool,
    inert: Inert,
) -> bool {
    let Some(decl_idx) = local_decl_index(block, impl_idx, local_name, inert) else {
        return false;
    };
    let mut bindings = BTreeSet::new();
    let mut ctor_stmts = BTreeSet::new();
    for (idx, stmt) in block.stmts.iter().enumerate() {
        let Stmt::Local(local) = stmt else { continue };
        let Some(init) = local.init.as_ref().filter(|i| i.diverge.is_none()) else {
            continue;
        };
        if idx == impl_idx
            || idx == decl_idx
            || !inert(&local.attrs)
            || !is_ctor_head(&init.expr, local_name, inert)
        {
            continue;
        }
        if !record_ctor_binding(&local.pat, local_name, inert, &mut bindings) {
            return false;
        }
        ctor_stmts.insert(idx);
    }

    let mut forbidden = bindings.clone();
    forbidden.insert(local_name.to_owned());
    let check = Check {
        forbidden: &forbidden,
        inert,
    };
    let mut uses_bare_drop = false;

    for (idx, stmt) in block.stmts.iter().enumerate() {
        if idx == impl_idx || idx == decl_idx {
            continue;
        }
        if ctor_stmts.contains(&idx) {
            let Stmt::Local(syn::Local {
                init: Some(init), ..
            }) = stmt
            else {
                return false;
            };
            if !check.ctor_args(&init.expr) {
                return false;
            }
            continue;
        }
        if let Stmt::Expr(expr, Some(_)) = stmt {
            if let Some(bare) = drop_call_kind(expr, &bindings, inert) {
                uses_bare_drop |= bare;
                continue;
            }
        }
        if !check.stmt(stmt) {
            return false;
        }
    }
    !uses_bare_drop || drop_safe
}

fn record_ctor_binding(
    pat: &Pat,
    local_name: &str,
    inert: Inert,
    bindings: &mut BTreeSet<String>,
) -> bool {
    match pat {
        Pat::Ident(pi) if pi.by_ref.is_none() && pi.subpat.is_none() && inert(&pi.attrs) => {
            let name = plain(&pi.ident);
            name != "drop" && name != local_name && bindings.insert(name)
        }
        Pat::Wild(w) => inert(&w.attrs),
        _ => false,
    }
}

fn is_plain_ident(path: &Path, expected: &str) -> bool {
    path.leading_colon.is_none() && path.get_ident().is_some_and(|id| plain(id) == expected)
}

fn is_ctor_head(expr: &Expr, local_name: &str, inert: Inert) -> bool {
    let (attrs, qself, path) = match expr {
        Expr::Call(c) => match &*c.func {
            Expr::Path(p) => (&c.attrs, &p.qself, &p.path),
            _ => return false,
        },
        Expr::Struct(s) if s.rest.is_none() => (&s.attrs, &s.qself, &s.path),
        Expr::Path(p) => (&p.attrs, &p.qself, &p.path),
        _ => return false,
    };
    inert(attrs) && qself.is_none() && is_plain_ident(path, local_name)
}

fn drop_call_kind(expr: &Expr, bindings: &BTreeSet<String>, inert: Inert) -> Option<bool> {
    let Expr::Call(call) = expr else {
        return None;
    };
    let Expr::Path(arg) = (inert(&call.attrs) && call.args.len() == 1)
        .then(|| call.args.first())
        .flatten()?
    else {
        return None;
    };
    let Expr::Path(func) = &*call.func else {
        return None;
    };
    let valid_arg = arg.qself.is_none()
        && arg.path.leading_colon.is_none()
        && arg
            .path
            .get_ident()
            .is_some_and(|i| bindings.contains(&plain(i)));
    if !valid_arg || func.qself.is_some() {
        return None;
    }
    let names: Vec<String> = func.path.segments.iter().map(|s| plain(&s.ident)).collect();
    match names.as_slice() {
        [a] if a == "drop" && func.path.leading_colon.is_none() => Some(true),
        [a, b, c] if (a == "std" || a == "core") && b == "mem" && c == "drop" => {
            Some(func.path.leading_colon.is_none())
        }
        _ => None,
    }
}

struct Check<'a> {
    forbidden: &'a BTreeSet<String>,
    inert: Inert,
}

fn expr_pair(expr: &Expr) -> Option<(&[Attribute], &Expr, &Expr)> {
    match expr {
        Expr::Assign(e) => Some((&e.attrs, &e.left, &e.right)),
        Expr::Binary(e) => Some((&e.attrs, &e.left, &e.right)),
        Expr::Index(e) => Some((&e.attrs, &e.expr, &e.index)),
        Expr::Repeat(e) => Some((&e.attrs, &e.expr, &e.len)),
        _ => None,
    }
}

fn expr_one(expr: &Expr) -> Option<(&[Attribute], &Expr)> {
    match expr {
        Expr::Field(e) => Some((&e.attrs, &e.base)),
        Expr::Group(e) => Some((&e.attrs, &e.expr)),
        Expr::Paren(e) => Some((&e.attrs, &e.expr)),
        Expr::Reference(e) => Some((&e.attrs, &e.expr)),
        Expr::Try(e) => Some((&e.attrs, &e.expr)),
        Expr::Unary(e) => Some((&e.attrs, &e.expr)),
        _ => None,
    }
}

impl Check<'_> {
    fn ok(&self, attrs: &[Attribute]) -> bool {
        (self.inert)(attrs)
    }

    fn ctor_args(&self, expr: &Expr) -> bool {
        match expr {
            Expr::Call(call) => self.exprs(&call.args),
            Expr::Struct(s) => s.fields.iter().all(|f| self.expr(&f.expr)),
            Expr::Path(_) => true,
            _ => false,
        }
    }

    fn stmt(&self, stmt: &Stmt) -> bool {
        match stmt {
            Stmt::Local(l) => {
                self.ok(&l.attrs)
                    && self.pat(&l.pat)
                    && l.init.as_ref().is_none_or(|i| {
                        self.expr(&i.expr) && self.opt_expr(i.diverge.as_ref().map(|(_, e)| &**e))
                    })
            }
            Stmt::Expr(expr, _) => self.expr(expr),
            Stmt::Macro(mac) => self.ok(&mac.attrs) && self.mac(&mac.mac),
            Stmt::Item(_) => false,
        }
    }

    fn block(&self, block: &Block) -> bool {
        block.stmts.iter().all(|s| self.stmt(s))
    }

    fn exprs<'a>(&self, items: impl IntoIterator<Item = &'a Expr>) -> bool {
        items.into_iter().all(|x| self.expr(x))
    }

    fn opt_expr(&self, expr: Option<&Expr>) -> bool {
        expr.is_none_or(|x| self.expr(x))
    }

    fn with_pat(&self, attrs: &[Attribute], expr: &Expr, pat: &Pat) -> bool {
        self.ok(attrs) && self.expr(expr) && self.pat(pat)
    }

    fn qpath(&self, attrs: &[Attribute], qself: Option<&syn::QSelf>, path: &Path) -> bool {
        self.ok(attrs) && qself.is_none_or(|q| self.ty(&q.ty)) && self.path(path)
    }

    fn expr(&self, expr: &Expr) -> bool {
        if let Some((attrs, a, b)) = expr_pair(expr) {
            return self.ok(attrs) && self.expr(a) && self.expr(b);
        }
        if let Some((attrs, inner)) = expr_one(expr) {
            return self.ok(attrs) && self.expr(inner);
        }
        match expr {
            Expr::Array(ExprArray { attrs, elems, .. })
            | Expr::Tuple(ExprTuple { attrs, elems, .. }) => self.ok(attrs) && self.exprs(elems),
            Expr::Break(ExprBreak { attrs, expr, .. })
            | Expr::Return(ExprReturn { attrs, expr, .. }) => {
                self.ok(attrs) && self.opt_expr(expr.as_deref())
            }
            Expr::Call(e) => self.ok(&e.attrs) && self.expr(&e.func) && self.exprs(&e.args),
            Expr::MethodCall(e) => {
                self.ok(&e.attrs) && self.expr(&e.receiver) && self.exprs(&e.args)
            }
            Expr::Block(ExprBlock { attrs, block, .. })
            | Expr::Loop(ExprLoop {
                attrs, body: block, ..
            }) => self.ok(attrs) && self.block(block),
            Expr::Continue(ExprContinue { attrs, .. }) | Expr::Lit(ExprLit { attrs, .. }) => {
                self.ok(attrs)
            }
            Expr::Cast(e) => self.ok(&e.attrs) && self.expr(&e.expr) && self.ty(&e.ty),
            Expr::Closure(e) => self.ok(&e.attrs) && self.expr(&e.body) && self.pats(&e.inputs),
            Expr::ForLoop(e) => self.with_pat(&e.attrs, &e.expr, &e.pat) && self.block(&e.body),
            Expr::If(e) => {
                self.ok(&e.attrs)
                    && self.expr(&e.cond)
                    && self.block(&e.then_branch)
                    && self.opt_expr(e.else_branch.as_ref().map(|(_, x)| &**x))
            }
            Expr::Let(e) => self.with_pat(&e.attrs, &e.expr, &e.pat),
            Expr::Macro(e) => self.ok(&e.attrs) && self.mac(&e.mac),
            Expr::Match(e) => {
                self.ok(&e.attrs)
                    && self.expr(&e.expr)
                    && e.arms
                        .iter()
                        .all(|a| self.with_pat(&a.attrs, &a.body, &a.pat))
            }
            Expr::Path(e) => self.qpath(&e.attrs, e.qself.as_ref(), &e.path),
            Expr::Range(e) => {
                self.ok(&e.attrs)
                    && self.opt_expr(e.start.as_deref())
                    && self.opt_expr(e.end.as_deref())
            }
            Expr::Struct(e) => {
                self.qpath(&e.attrs, e.qself.as_ref(), &e.path)
                    && self.opt_expr(e.rest.as_deref())
                    && e.fields.iter().all(|x| self.expr(&x.expr))
            }
            Expr::While(e) => self.ok(&e.attrs) && self.expr(&e.cond) && self.block(&e.body),
            // Fail closed on `Unsafe`, `Async`, `Await`, `TryBlock`, `Yield`, `Verbatim`, etc.
            _ => false,
        }
    }

    fn mac(&self, mac: &syn::Macro) -> bool {
        if mac.path.leading_colon.is_some() {
            return false;
        }
        let Some(name) = mac.path.get_ident().map(plain) else {
            return false;
        };
        std_macros::has(&name, std_macros::NO_BIND) && self.tokens(mac.tokens.clone())
    }

    fn tokens(&self, stream: TokenStream) -> bool {
        stream.into_iter().all(|token| match token {
            TokenTree::Group(g) => self.tokens(g.stream()),
            TokenTree::Ident(id) => {
                let word = plain(&id);
                word != "unsafe" && !self.forbidden.contains(&word)
            }
            _ => true,
        })
    }

    fn ident(&self, ident: &Ident) -> bool {
        !self.forbidden.contains(&plain(ident))
    }

    fn path(&self, path: &Path) -> bool {
        path.segments.iter().all(|seg| {
            self.ident(&seg.ident)
                && match &seg.arguments {
                    syn::PathArguments::None => true,
                    syn::PathArguments::AngleBracketed(args) => args.args.iter().all(|a| match a {
                        syn::GenericArgument::Type(ty) => self.ty(ty),
                        syn::GenericArgument::Lifetime(_) => true,
                        syn::GenericArgument::Const(expr) => self.expr(expr),
                        _ => false,
                    }),
                    syn::PathArguments::Parenthesized(_) => false,
                }
        })
    }

    fn pats<'a>(&self, items: impl IntoIterator<Item = &'a Pat>) -> bool {
        items.into_iter().all(|p| self.pat(p))
    }

    fn pat(&self, pat: &Pat) -> bool {
        match pat {
            Pat::Ident(p) => {
                self.ok(&p.attrs)
                    && self.ident(&p.ident)
                    && p.subpat.as_ref().is_none_or(|(_, sub)| self.pat(sub))
            }
            Pat::Slice(PatSlice { attrs, elems, .. })
            | Pat::Tuple(PatTuple { attrs, elems, .. }) => self.ok(attrs) && self.pats(elems),
            Pat::Or(p) => self.ok(&p.attrs) && self.pats(&p.cases),
            Pat::Path(p) => p.qself.is_none() && self.qpath(&p.attrs, None, &p.path),
            Pat::Paren(PatParen { attrs, pat, .. })
            | Pat::Reference(PatReference { attrs, pat, .. }) => self.ok(attrs) && self.pat(pat),
            Pat::Rest(PatRest { attrs, .. })
            | Pat::Wild(PatWild { attrs, .. })
            | Pat::Lit(ExprLit { attrs, .. }) => self.ok(attrs),
            Pat::Struct(p) => {
                p.qself.is_none()
                    && self.qpath(&p.attrs, None, &p.path)
                    && p.fields.iter().all(|x| self.pat(&x.pat))
            }
            Pat::TupleStruct(p) => {
                p.qself.is_none() && self.qpath(&p.attrs, None, &p.path) && self.pats(&p.elems)
            }
            Pat::Type(p) => self.ok(&p.attrs) && self.pat(&p.pat) && self.ty(&p.ty),
            _ => false,
        }
    }

    fn ty(&self, ty: &Type) -> bool {
        match ty {
            Type::Array(t) => self.ty(&t.elem) && self.expr(&t.len),
            Type::Group(TypeGroup { elem, .. })
            | Type::Paren(TypeParen { elem, .. })
            | Type::Reference(TypeReference { elem, .. })
            | Type::Slice(TypeSlice { elem, .. }) => self.ty(elem),
            Type::Infer(_) | Type::Never(_) => true,
            Type::Path(t) => t.qself.as_ref().is_none_or(|q| self.ty(&q.ty)) && self.path(&t.path),
            Type::Tuple(t) => t.elems.iter().all(|e| self.ty(e)),
            _ => false,
        }
    }
}
