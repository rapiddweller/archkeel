// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Generic parameters that can hide the first name of an expression path.

use std::collections::BTreeSet;

use syn::visit::{self, Visit};
use syn::{ExprPath, GenericParam};

use crate::tokens::plain;

pub(super) struct Safety {
    pub generic_paths: BTreeSet<(i64, i64)>,
    pub conditional_use: bool,
    pub conditional_bindings: BTreeSet<String>,
    pub conditional_globs: BTreeSet<(i64, i64)>,
    pub restricted_bindings: BTreeSet<String>,
}

pub(super) fn read(file: &syn::File, exclude_tests: bool) -> Safety {
    let mut found = Names {
        exclude_tests,
        ..Names::default()
    };
    found.visit_file(file);
    let paths = found
        .paths
        .into_iter()
        .filter(|(_, name)| found.generics.contains(name))
        .map(|(site, _)| site)
        .collect();
    Safety {
        generic_paths: paths,
        conditional_use: found.conditional_use,
        conditional_bindings: found.conditional_bindings,
        conditional_globs: found.conditional_globs,
        restricted_bindings: found.restricted_bindings,
    }
}

#[derive(Default)]
struct Names {
    generics: BTreeSet<String>,
    paths: Vec<((i64, i64), String)>,
    conditional_use: bool,
    conditional_bindings: BTreeSet<String>,
    conditional_globs: BTreeSet<(i64, i64)>,
    restricted_bindings: BTreeSet<String>,
    gated: bool,
    exclude_tests: bool,
}

impl Names {
    fn use_tree(&mut self, tree: &syn::UseTree, parent: Option<&syn::Ident>) {
        match tree {
            syn::UseTree::Path(path) => self.use_tree(&path.tree, Some(&path.ident)),
            syn::UseTree::Name(name) => {
                let ident = if name.ident == "self" {
                    parent
                } else {
                    Some(&name.ident)
                };
                if let Some(ident) = ident {
                    self.conditional_bindings.insert(plain(ident));
                }
            }
            syn::UseTree::Rename(rename) => {
                self.conditional_bindings.insert(plain(&rename.rename));
            }
            syn::UseTree::Glob(glob) => {
                let start = glob.star_token.spans[0].start();
                self.conditional_globs.insert((
                    i64::try_from(start.line).unwrap_or(i64::MAX),
                    i64::try_from(start.column).unwrap_or(i64::MAX),
                ));
            }
            syn::UseTree::Group(group) => {
                for item in &group.items {
                    self.use_tree(item, parent);
                }
            }
        }
    }
}

impl<'ast> Visit<'ast> for Names {
    fn visit_item(&mut self, node: &'ast syn::Item) {
        if self.exclude_tests
            && crate::attrs::is_test_attributes(crate::attrs::item_attributes(node))
        {
            return;
        }
        visit::visit_item(self, node);
    }

    fn visit_item_mod(&mut self, node: &'ast syn::ItemMod) {
        let was_gated = self.gated;
        if node.content.is_some() {
            self.conditional_use |= !super::receivers::module_inert(&node.attrs);
            self.gated |= !super::receivers::module_inert(&node.attrs);
        }
        visit::visit_item_mod(self, node);
        self.gated = was_gated;
    }

    fn visit_item_use(&mut self, node: &'ast syn::ItemUse) {
        if self.gated || !super::receivers::inert(&node.attrs) {
            self.conditional_use = true;
            self.use_tree(&node.tree, None);
        }
        if !matches!(node.vis, syn::Visibility::Public(_)) {
            let old = std::mem::take(&mut self.conditional_bindings);
            let old_globs = std::mem::take(&mut self.conditional_globs);
            self.use_tree(&node.tree, None);
            self.restricted_bindings
                .append(&mut self.conditional_bindings);
            self.conditional_bindings = old;
            self.conditional_globs = old_globs;
        }
        visit::visit_item_use(self, node);
    }

    fn visit_generic_param(&mut self, node: &'ast GenericParam) {
        let name = match node {
            GenericParam::Type(value) => Some(&value.ident),
            GenericParam::Const(value) => Some(&value.ident),
            GenericParam::Lifetime(_) => None,
        };
        if let Some(name) = name {
            self.generics.insert(plain(name));
        }
        visit::visit_generic_param(self, node);
    }

    fn visit_expr_path(&mut self, node: &'ast ExprPath) {
        if node.qself.is_none() && node.path.leading_colon.is_none() && node.path.segments.len() > 1
        {
            if let Some(first) = node.path.segments.first() {
                let start = first.ident.span().start();
                let line = i64::try_from(start.line).unwrap_or(i64::MAX);
                let column = i64::try_from(start.column).unwrap_or(i64::MAX);
                self.paths.push(((line, column), plain(&first.ident)));
            }
        }
        visit::visit_expr_path(self, node);
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn restricted_uses_do_not_change_conditional_facts() {
        let file = syn::parse_file(
            "pub use a::Public; pub(crate) use a::{Hidden, Renamed as Alias, *}; \
             #[cfg(any())] pub use a::Conditional;",
        )
        .unwrap();
        let facts = super::read(&file, false);
        assert_eq!(
            facts.restricted_bindings.into_iter().collect::<Vec<_>>(),
            ["Alias", "Hidden"]
        );
        assert_eq!(
            facts.conditional_bindings.into_iter().collect::<Vec<_>>(),
            ["Conditional"]
        );
        assert!(facts.conditional_globs.is_empty());
    }
}
