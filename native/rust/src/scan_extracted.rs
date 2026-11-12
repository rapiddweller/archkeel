// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The second count of the extraction invariant (`edges_extracted.rs`). A visitor apart from the
//! walker of `scan.rs` counts the `use` leaves, the `extern crate` items, the qualified paths and
//! the macro calls of the tree. Each of them must end as a record, a gap, or a local path that
//! gives no edge. The count shares no code with the walker except the rule of which items the
//! scan leaves out.

use syn::visit::{self, Visit};
use syn::{ImplItem, Item, ItemExternCrate, ItemMacro, ItemUse, Macro, TraitItem, UseTree};

use crate::attrs::{
    impl_item_attributes, is_test_attributes, item_attributes, statement_attributes,
    trait_item_attributes,
};
use crate::tokens::LINTS;

/// What the count of a file needs, besides the references and macro calls that the scan holds.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Tally {
    /// Use leaves, `extern crate` items, qualified paths and macro calls of the tree.
    pub expected: usize,
    /// References that the tree does not show as nodes: paths of attributes and paths that the
    /// scan reads in the tokens of a macro or an attribute.
    pub unseen: usize,
    /// Calls that the scan reads in the tokens of a macro call: they are no node of the tree.
    pub hidden: usize,
    /// Method calls that the scan reads in the tokens of a macro call: they are no node either.
    pub hidden_methods: usize,
}

impl Tally {
    /// The count of the nodes of the tree that must end as an outcome.
    pub fn of(file: &syn::File, exclude_tests: bool) -> Self {
        let mut nodes = Nodes {
            exclude_tests,
            found: 0,
        };
        nodes.visit_file(file);
        Self {
            expected: nodes.found,
            ..Self::default()
        }
    }
}

struct Nodes {
    exclude_tests: bool,
    found: usize,
}

impl Nodes {
    /// The scan leaves out an item that only a test build compiles, when it excludes tests.
    fn hidden(&self, attrs: &[syn::Attribute]) -> bool {
        self.exclude_tests && is_test_attributes(attrs)
    }
}

/// The leaves of a `use` tree: a name, a rename or a glob. A leaf with no segment at all
/// (`use ::*;`, `use self as x;`) names no path, so the scan reads none.
fn leaves(tree: &UseTree, prefixed: bool) -> usize {
    match tree {
        UseTree::Path(path) => leaves(&path.tree, true),
        UseTree::Group(group) => group.items.iter().map(|item| leaves(item, prefixed)).sum(),
        UseTree::Glob(_) => usize::from(prefixed),
        UseTree::Name(syn::UseName { ident }) | UseTree::Rename(syn::UseRename { ident, .. }) => {
            usize::from(prefixed || ident != "self")
        }
    }
}

impl<'ast> Visit<'ast> for Nodes {
    fn visit_item(&mut self, item: &'ast Item) {
        if !self.hidden(item_attributes(item)) {
            visit::visit_item(self, item);
        }
    }

    fn visit_impl_item(&mut self, item: &'ast ImplItem) {
        if !self.hidden(impl_item_attributes(item)) {
            visit::visit_impl_item(self, item);
        }
    }

    fn visit_trait_item(&mut self, item: &'ast TraitItem) {
        if !self.hidden(trait_item_attributes(item)) {
            visit::visit_trait_item(self, item);
        }
    }

    fn visit_stmt(&mut self, stmt: &'ast syn::Stmt) {
        if !self.hidden(statement_attributes(stmt)) {
            visit::visit_stmt(self, stmt);
        }
    }

    /// The path of an attribute and the tokens of a list are read as `unseen`. The value of
    /// `key = value` is code when it is no literal (`doc = include_str!("x")`): its macro calls
    /// and paths are nodes. A lint attribute is not read.
    fn visit_attribute(&mut self, attr: &'ast syn::Attribute) {
        if let syn::Meta::NameValue(pair) = &attr.meta {
            let lint = LINTS.iter().any(|lint| pair.path.is_ident(lint));
            if !lint && !matches!(pair.value, syn::Expr::Lit(_)) {
                self.visit_expr(&pair.value);
            }
        }
    }

    fn visit_visibility(&mut self, _: &'ast syn::Visibility) {}

    fn visit_path(&mut self, path: &'ast syn::Path) {
        self.found += usize::from(path.segments.len() > 1);
        visit::visit_path(self, path);
    }

    /// `x.m(..)` and `<T>::m(..)` are method calls of the scan (#953).
    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        self.found += 1;
        visit::visit_expr_method_call(self, node);
    }

    fn visit_expr_path(&mut self, node: &'ast syn::ExprPath) {
        self.found += usize::from(node.qself.is_some() && !node.path.segments.is_empty());
        self.found += usize::from(super::receivers::self_member(node).is_some());
        visit::visit_expr_path(self, node);
    }

    fn visit_macro(&mut self, node: &'ast Macro) {
        self.found += 1;
        visit::visit_macro(self, node);
    }

    /// A `macro_rules!` body is read as tokens: the scan counts what it finds there as `unseen`.
    fn visit_item_macro(&mut self, node: &'ast ItemMacro) {
        if node.mac.path.is_ident("macro_rules") {
            for attr in &node.attrs {
                self.visit_attribute(attr);
            }
        } else {
            visit::visit_item_macro(self, node);
        }
    }

    fn visit_item_use(&mut self, node: &'ast ItemUse) {
        self.found += leaves(&node.tree, false);
        for attr in &node.attrs {
            self.visit_attribute(attr);
        }
    }

    /// `extern crate self as name;` names the crate and then the root of this crate.
    fn visit_item_extern_crate(&mut self, node: &'ast ItemExternCrate) {
        let own = node.ident == "self" && node.rename.is_some();
        self.found += 1 + usize::from(own);
    }
}

#[cfg(test)]
#[path = "scan_extracted_tests.rs"]
mod tests;
