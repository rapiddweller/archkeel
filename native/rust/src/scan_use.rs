// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `use` item and in `extern crate self as name`: each leaf is a
//! reference that carries its segments, its scope and the local name that it binds. The walker
//! of `scan.rs` owns the facts; this file only fills them.

use syn::{ItemExternCrate, ItemUse, UseTree, Visibility};

use super::{Via, Walker};
use crate::tokens::plain;

impl Walker<'_> {
    /// A name that the file declares or imports, anywhere in it.
    pub(super) fn bind(&mut self, name: String) {
        *self.out.counts.entry(name.clone()).or_default() += 1;
        self.out.shadows.insert(name.clone());
        self.out.names.insert(name);
    }

    /// A `use` leaf binds `name`. When the path of the leaf starts with a crate of that same name,
    /// the binding is no shadow of that crate.
    fn bind_leaf(&mut self, name: String, prefix: &[String]) {
        if prefix.first() == Some(&name) {
            *self.out.counts.entry(name.clone()).or_default() += 1;
            self.out.names.insert(name);
        } else {
            self.bind(name);
        }
    }

    pub(super) fn use_item(&mut self, node: &ItemUse) {
        self.absolute_use = node.leading_colon.is_some();
        self.public_use = !matches!(node.vis, Visibility::Inherited);
        self.use_tree(&mut Vec::new(), &node.tree);
        self.absolute_use = false;
        self.via = Via::Path;
    }

    fn use_tree(&mut self, prefix: &mut Vec<String>, tree: &UseTree) {
        match tree {
            UseTree::Path(path) => {
                prefix.push(plain(&path.ident));
                self.use_tree(prefix, &path.tree);
                prefix.pop();
            }
            UseTree::Name(name) => {
                // `use a::b::{self}` binds `b`.
                let bound = if name.ident == "self" {
                    prefix.last().cloned()
                } else {
                    Some(plain(&name.ident))
                };
                if let Some(bound) = bound.clone() {
                    self.bind_leaf(bound, prefix);
                }
                self.leaf(prefix, &name.ident, bound);
            }
            UseTree::Rename(rename) => {
                let bound = plain(&rename.rename);
                self.bind_leaf(bound.clone(), prefix);
                self.leaf(prefix, &rename.ident, Some(bound));
            }
            UseTree::Glob(glob) => {
                self.via = Via::Glob {
                    reexport: self.public_use,
                    block: self.blocks > 0,
                };
                let span = glob.star_token.spans[0];
                self.refer_as(prefix, span, self.absolute_use);
            }
            UseTree::Group(group) => {
                for item in &group.items {
                    self.use_tree(prefix, item);
                }
            }
        }
    }

    fn leaf(&mut self, prefix: &[String], name: &syn::Ident, binding: Option<String>) {
        self.via = Via::Use {
            binding,
            reexport: self.public_use,
            block: self.blocks > 0,
        };
        let mut names = prefix.to_vec();
        // `use a::b::{self}` names the module `a::b`.
        if name != "self" {
            names.push(plain(name));
        }
        self.refer_as(&names, name.span(), self.absolute_use);
    }

    /// `extern crate foo;` names the crate `foo`. `extern crate self as name;` binds `name` to
    /// the root of this crate, so `name::a::f` is a path into the module `a`.
    pub(super) fn extern_crate(&mut self, node: &ItemExternCrate) {
        let span = node.ident.span();
        self.refer(&[plain(&node.ident)], span);
        if node.ident != "self" {
            let site = self.site(span);
            self.out.extern_crates.push((plain(&node.ident), site));
        }
        if let (true, Some((_, rename))) = (node.ident == "self", &node.rename) {
            self.via = Via::Use {
                binding: Some(plain(rename)),
                reexport: false,
                block: self.blocks > 0,
            };
            self.refer(&["crate".to_owned()], span);
            self.via = Via::Path;
            if self.blocks == 0 {
                self.out
                    .self_aliases
                    .push((self.inline.clone(), plain(rename)));
            }
        }
    }
}
