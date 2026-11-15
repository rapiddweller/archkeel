// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The typed parameters of a `fn` (AD-524). A parameter `x: T`, `x: &T` or `x: &mut T` with a
//! plain identifier and a plain path has the type that is written, so a call `x.m()` has the
//! same first step as a call on `self` (AD-383): the written type, and the kind of the written
//! reference. A written type is a proof; inference is not.
//!
//! A parameter has a proof only when its name is bound once in the `fn`: the parameter. Any other
//! binding is a refusal: a `let`, a pattern of a `match`, `if let`, `while let` or `for`, a
//! parameter of a closure or of a nested `fn`, an item of that name, a `use` that may bind it,
//! and a macro call whose tokens name it (a macro can bind a name that its call passes), except
//! the macros of `std` that bind nothing. A type that names a generic parameter of the `fn` or of
//! the `impl` is generic, so it is not read. The resolution of the type, its exactness and the
//! member are the checks of `impl_receivers.rs`.

use std::collections::{BTreeMap, BTreeSet};

use proc_macro2::{TokenStream, TokenTree};
use syn::visit::{self, Visit};
use syn::{
    Attribute, FnArg, GenericArgument, GenericParam, Item, Pat, PathArguments, Signature, Type,
};

use crate::definitions::{OnSelf, SelfKind};
use crate::tokens::{plain, NO_BIND_MACROS};

/// Whether a generic argument binds a type or a const: a lifetime does not change which
/// inherent methods a type has.
fn binds_type(argument: &GenericArgument) -> bool {
    !matches!(argument, GenericArgument::Lifetime(_))
}

/// The segments of a plain relative type path: no qualified self, no leading `::`, and no type
/// or const argument (a lifetime does not change which inherent methods a type has).
pub(super) fn plain_path(ty: &Type) -> Option<Vec<String>> {
    let Type::Path(path) = ty else {
        return None;
    };
    if path.qself.is_some() || path.path.leading_colon.is_some() {
        return None;
    }
    let mut names = Vec::new();
    for segment in &path.path.segments {
        match &segment.arguments {
            PathArguments::None => {}
            PathArguments::AngleBracketed(list) if !list.args.iter().any(binds_type) => {}
            _ => return None,
        }
        names.push(plain(&segment.ident));
    }
    Some(names)
}

/// The name of a type or const parameter. A lifetime has none.
pub(super) fn generic_name(param: &GenericParam) -> Option<String> {
    match param {
        GenericParam::Type(found) => Some(plain(&found.ident)),
        GenericParam::Const(found) => Some(plain(&found.ident)),
        GenericParam::Lifetime(_) => None,
    }
}

#[derive(Debug)]
struct Binding {
    receiver: OnSelf,
    after: Option<(usize, usize)>,
    sites: Option<BTreeSet<(usize, usize)>>,
}

impl Binding {
    fn new(
        name: &str,
        (path, kind): (Vec<String>, SelfKind),
        scope: &[String],
        bound: &Bound,
        after: Option<(usize, usize)>,
        sites: Option<BTreeSet<(usize, usize)>>,
    ) -> Self {
        Self {
            receiver: OnSelf {
                name: name.to_owned(),
                path,
                scope: scope.to_vec(),
                kind: Some(kind),
                macros: bound.macros.iter().cloned().collect(),
                fields: Vec::new(),
            },
            after,
            sites,
        }
    }
}

/// The bindings of one `fn` that have a proof, by name.
#[derive(Debug, Default)]
pub(super) struct Params(BTreeMap<String, Binding>);

impl Params {
    pub(super) fn get(&self, name: &str, at: (usize, usize)) -> Option<&OnSelf> {
        let found = self.0.get(name)?;
        (found.after.is_none_or(|after| at > after)
            && found.sites.as_ref().is_none_or(|sites| sites.contains(&at)))
        .then_some(&found.receiver)
    }
}

/// How the body and the signature bind names.
struct Bound {
    /// Whether each attribute is inert: a `cfg` or an unknown attribute on a statement, an
    /// expression, an arm or a block can remove the code around a call (AD-524).
    inert: fn(&[Attribute]) -> bool,
    /// A non-inert attribute is somewhere in the `fn`.
    gated: bool,
    /// A macro call can pass a nested macro call through to its expansion.
    nested_macro: bool,
    /// The macros that the `fn` calls and that are no silent macro of `std`.
    macros: BTreeSet<String>,
    /// How many times each name is bound by a pattern or an item.
    counts: BTreeMap<String, usize>,
    /// Names that a `use` or a macro call may bind.
    tainted: BTreeSet<String>,
}

impl Bound {
    fn count(&mut self, name: String) {
        *self.counts.entry(name).or_default() += 1;
    }

    fn taint(&mut self, tokens: TokenStream) {
        for tree in tokens {
            match tree {
                TokenTree::Ident(ident) => {
                    self.tainted.insert(plain(&ident));
                }
                TokenTree::Group(group) => self.taint(group.stream()),
                _ => {}
            }
        }
    }

    fn has_macro(tokens: TokenStream) -> bool {
        let mut trees = tokens.into_iter().peekable();
        while let Some(tree) = trees.next() {
            match tree {
                TokenTree::Group(group) if Self::has_macro(group.stream()) => return true,
                TokenTree::Ident(_) if matches!(trees.peek(), Some(TokenTree::Punct(p)) if p.as_char() == '!') => {
                    return true
                }
                TokenTree::Punct(p)
                    if p.as_char() == '#'
                        && matches!(trees.peek(), Some(TokenTree::Group(g)) if g.delimiter() == proc_macro2::Delimiter::Bracket) =>
                {
                    return true
                }
                _ => {}
            }
        }
        false
    }

    fn leaves(&mut self, tree: &syn::UseTree) {
        match tree {
            syn::UseTree::Path(path) => self.leaves(&path.tree),
            syn::UseTree::Group(group) => group.items.iter().for_each(|item| self.leaves(item)),
            syn::UseTree::Name(name) => self.count(plain(&name.ident)),
            syn::UseTree::Rename(rename) => self.count(plain(&rename.rename)),
            // A glob never shadows a local, and an item of a block wins over it.
            syn::UseTree::Glob(_) => {}
        }
    }
}

impl<'ast> Visit<'ast> for Bound {
    fn visit_pat_ident(&mut self, node: &'ast syn::PatIdent) {
        self.count(plain(&node.ident));
        visit::visit_pat_ident(self, node);
    }

    fn visit_item(&mut self, node: &'ast syn::Item) {
        match node {
            syn::Item::Use(found) => self.leaves(&found.tree),
            other => {
                if let Some(name) = item_name(other) {
                    self.count(name);
                }
            }
        }
        visit::visit_item(self, node);
    }

    fn visit_attribute(&mut self, node: &'ast Attribute) {
        self.gated |= !(self.inert)(std::slice::from_ref(node));
    }

    fn visit_macro(&mut self, node: &'ast syn::Macro) {
        let name = node.path.get_ident().map(plain);
        let silent = name
            .as_deref()
            .is_some_and(|name| NO_BIND_MACROS.contains(&name));
        // A `macro_rules!` item defines a macro; it is no call.
        if !silent && name.as_deref() != Some("macro_rules") {
            self.nested_macro |= Self::has_macro(node.tokens.clone());
            let written = |path: &syn::Path| {
                let segments = path.segments.iter().map(|s| plain(&s.ident));
                segments.collect::<Vec<_>>().join("::")
            };
            self.macros
                .insert(name.unwrap_or_else(|| written(&node.path)));
            self.taint(node.tokens.clone());
        }
        visit::visit_macro(self, node);
    }
}

/// The name that an item declares. Every kind counts, whatever its namespace.
pub(in crate::scan) fn item_name(item: &Item) -> Option<String> {
    let ident = match item {
        Item::Fn(item) => &item.sig.ident,
        Item::Struct(item) => &item.ident,
        Item::Enum(item) => &item.ident,
        Item::Union(item) => &item.ident,
        Item::Trait(item) => &item.ident,
        Item::TraitAlias(item) => &item.ident,
        Item::Type(item) => &item.ident,
        Item::Const(item) => &item.ident,
        Item::Static(item) => &item.ident,
        Item::Mod(item) => &item.ident,
        Item::Macro(item) => item.ident.as_ref()?,
        Item::ExternCrate(item) => item.rename.as_ref().map_or(&item.ident, |(_, name)| name),
        _ => return None,
    };
    Some(plain(ident))
}

/// The kind and the path of a written parameter type: `T`, `&T` or `&mut T`, and one level only.
pub(in crate::scan) fn typed(ty: &Type) -> Option<(Vec<String>, SelfKind)> {
    match ty {
        Type::Reference(found) => {
            let kind = match found.mutability {
                Some(_) => SelfKind::Unique,
                None => SelfKind::Shared,
            };
            Some((plain_path(&found.elem)?, kind))
        }
        other => Some((plain_path(other)?, SelfKind::Value)),
    }
}

/// The parameters of a `fn` that have a proof: a plain identifier (`mut` is fine), bound once in
/// the signature and the body, with a written plain type that no generic parameter of the `fn` or
/// of the enclosing `impl` can hide. `scope` is the inline modules that enclose the `fn`.
pub(super) fn read(
    sig: &Signature,
    block: &syn::Block,
    outer: &[String],
    scope: &[String],
    inert: fn(&[Attribute]) -> bool,
) -> Params {
    let mut bound = Bound {
        inert,
        gated: false,
        nested_macro: false,
        macros: BTreeSet::new(),
        counts: BTreeMap::new(),
        tainted: BTreeSet::new(),
    };
    bound.visit_signature(sig);
    bound.visit_block(block);
    if bound.gated || bound.nested_macro {
        return Params::default();
    }
    let mut hidden: BTreeSet<String> = outer.iter().cloned().collect();
    hidden.extend(sig.generics.params.iter().filter_map(generic_name));
    let mut found = BTreeMap::new();
    for input in &sig.inputs {
        let FnArg::Typed(param) = input else {
            continue;
        };
        let Pat::Ident(pattern) = &*param.pat else {
            continue;
        };
        let plain_pattern = pattern.by_ref.is_none()
            && pattern.subpat.is_none()
            && pattern.attrs.is_empty()
            && param.attrs.is_empty();
        let name = plain(&pattern.ident);
        let once = bound.counts.get(&name) == Some(&1) && !bound.tainted.contains(&name);
        let Some((path, kind)) = typed(&param.ty) else {
            continue;
        };
        let generic = path.first().is_some_and(|first| hidden.contains(first));
        if plain_pattern && once && !generic {
            let binding = Binding::new(&name, (path, kind), scope, &bound, None, None);
            found.insert(name, binding);
        }
    }
    read_locals(block, &bound, &hidden, scope, &mut found);
    Closures {
        bound: &bound,
        hidden: &hidden,
        scope,
        found: &mut found,
    }
    .visit_block(block);
    Params(found)
}

/// Read only top-level initialized locals; their binding begins after the complete statement.
fn read_locals(
    block: &syn::Block,
    bound: &Bound,
    hidden: &BTreeSet<String>,
    scope: &[String],
    found: &mut BTreeMap<String, Binding>,
) {
    for statement in &block.stmts {
        let syn::Stmt::Local(local) = statement else {
            continue;
        };
        let Pat::Type(pattern) = &local.pat else {
            continue;
        };
        let Pat::Ident(ident) = &*pattern.pat else {
            continue;
        };
        let Some((path, kind)) = typed(&pattern.ty) else {
            continue;
        };
        let name = plain(&ident.ident);
        let first = path.first();
        if local.init.is_none()
            || ident.by_ref.is_some()
            || ident.subpat.is_some()
            || !ident.attrs.is_empty()
            || !pattern.attrs.is_empty()
            || bound.counts.get(&name) != Some(&1)
            || bound.tainted.contains(&name)
            || macro_hides_type(&path, bound)
            || first.is_some_and(|name| hidden.contains(name) || bound.counts.contains_key(name))
        {
            continue;
        }
        let end = local.semi_token.spans[0].end();
        let binding = Binding::new(
            &name,
            (path, kind),
            scope,
            bound,
            Some((end.line, end.column)),
            None,
        );
        found.insert(name, binding);
    }
}

/// A macro can add a type or import in a function body without naming it at the call.
fn macro_hides_type(path: &[String], bound: &Bound) -> bool {
    !bound.macros.is_empty()
        && path
            .first()
            .is_some_and(|first| !matches!(first.as_str(), "crate" | "self" | "super"))
}

/// The receiver sites inside one closure, without nested items, macros or closures.
#[derive(Default)]
struct ClosureSites(BTreeMap<String, BTreeSet<(usize, usize)>>);

impl<'ast> Visit<'ast> for ClosureSites {
    fn visit_item(&mut self, _: &'ast Item) {}
    fn visit_expr_closure(&mut self, _: &'ast syn::ExprClosure) {}
    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        let mut receiver = &*node.receiver;
        for _ in 0..2 {
            let syn::Expr::Field(field) = receiver else {
                break;
            };
            if !field.attrs.is_empty() || !matches!(field.member, syn::Member::Named(_)) {
                break;
            }
            receiver = &field.base;
        }
        if let syn::Expr::Path(path) = receiver {
            let name = path
                .path
                .get_ident()
                .filter(|_| path.qself.is_none() && path.attrs.is_empty());
            if let Some(name) = name {
                let at = name.span().start();
                self.0
                    .entry(plain(name))
                    .or_default()
                    .insert((at.line, at.column));
            }
        }
        visit::visit_expr_method_call(self, node);
    }
}

struct Closures<'a> {
    bound: &'a Bound,
    hidden: &'a BTreeSet<String>,
    scope: &'a [String],
    found: &'a mut BTreeMap<String, Binding>,
}

impl<'ast> Visit<'ast> for Closures<'_> {
    fn visit_item(&mut self, _: &'ast Item) {}

    fn visit_expr_closure(&mut self, node: &'ast syn::ExprClosure) {
        let mut sites = ClosureSites::default();
        sites.visit_expr(&node.body);
        for input in &node.inputs {
            let Pat::Type(param) = input else { continue };
            let Pat::Ident(ident) = &*param.pat else {
                continue;
            };
            let Some((path, kind)) = typed(&param.ty) else {
                continue;
            };
            let name = plain(&ident.ident);
            if ident.by_ref.is_some()
                || ident.subpat.is_some()
                || !ident.attrs.is_empty()
                || !param.attrs.is_empty()
                || self.bound.counts.get(&name) != Some(&1)
                || self.bound.tainted.contains(&name)
                || macro_hides_type(&path, self.bound)
                || path.first().is_some_and(|first| {
                    self.hidden.contains(first) || self.bound.counts.contains_key(first)
                })
            {
                continue;
            }
            let Some(places) = sites.0.remove(&name) else {
                continue;
            };
            let binding = Binding::new(
                &name,
                (path, kind),
                self.scope,
                self.bound,
                None,
                Some(places),
            );
            self.found.insert(name, binding);
        }
        visit::visit_expr_closure(self, node);
    }
}

#[cfg(test)]
mod tests {
    use super::read;

    #[test]
    fn a_closure_binding_proves_only_receiver_sites_in_its_body() {
        let text = "fn f() { let _c = |s: &crate::c::S| s.m(); s.m(); }";
        let item: syn::ItemFn = syn::parse_str(text).unwrap();
        let found = read(&item.sig, &item.block, &[], &[], |_| true);
        let first = text.find("s.m()").unwrap();
        let last = text.rfind("s.m()").unwrap();
        assert!(found.get("s", (1, first)).is_some());
        assert!(found.get("s", (1, last)).is_none());
    }
}
