// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! How a `fn` binds names (AD-524): each name that a pattern or an item binds, the names that a
//! `use` or a macro call may bind, the macros that the `fn` calls, and whether an attribute that
//! is not inert is in it.

use std::collections::{BTreeMap, BTreeSet};

use proc_macro2::{TokenStream, TokenTree};
use syn::visit::{self, Visit};
use syn::{Attribute, Item};

use crate::std_macros;
use crate::tokens::plain;

/// How the body and the signature bind names.
pub(super) struct Bound {
    /// Whether each attribute is inert: a `cfg` or an unknown attribute on a statement, an
    /// expression, an arm or a block can remove the code around a call (AD-524).
    pub(super) inert: fn(&[Attribute]) -> bool,
    /// A non-inert attribute is somewhere in the `fn`.
    pub(super) gated: bool,
    /// A macro call can pass a nested macro call through to its expansion.
    pub(super) nested_macro: bool,
    /// The macros that the `fn` calls and that are no silent macro of `std`.
    pub(super) macros: BTreeSet<String>,
    /// How many times each name is bound by a pattern or an item.
    pub(super) counts: BTreeMap<String, usize>,
    /// Names that a `use` or a macro call may bind.
    pub(super) tainted: BTreeSet<String>,
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
            .is_some_and(|name| std_macros::has(name, std_macros::NO_BIND));
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
