// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `use` item and in `extern crate self as name`: each leaf is a
//! reference that carries its segments, its scope and the local name that it binds. The walker
//! of `scan.rs` owns the facts; this file only fills them.

use syn::{ItemExternCrate, ItemUse, UseTree, Visibility};

use super::attributes::concern;
use super::state::{Via, Walker};
use crate::tokens::plain;

/// A name that the file declares or imports, anywhere in it.
pub(super) fn bind(walker: &mut Walker<'_>, name: String) {
    count(walker, &name);
    walker.out.shadows.insert(name.clone());
    walker.out.names.insert(name);
}

/// A `use` leaf binds `name`. When the path of the leaf starts with a crate of that same name,
/// the binding is no shadow of that crate.
pub(super) fn bind_leaf(walker: &mut Walker<'_>, name: String, prefix: &[String]) {
    if prefix.first() == Some(&name) {
        count(walker, &name);
        walker.out.names.insert(name);
    } else {
        bind(walker, name);
    }
}

/// One declaration of `name` in the file and in its inline module.
fn count(walker: &mut Walker<'_>, name: &str) {
    *walker.out.counts.entry(name.to_owned()).or_default() += 1;
    let key = (walker.inline.clone(), name.to_owned());
    *walker.out.scoped_counts.entry(key).or_default() += 1;
}

pub(super) fn use_item(walker: &mut Walker<'_>, node: &ItemUse) {
    walker.absolute_use = node.leading_colon.is_some();
    walker.public_use = !matches!(node.vis, Visibility::Inherited);
    use_tree(walker, &mut Vec::new(), &node.tree);
    walker.absolute_use = false;
    walker.via = Via::Path;
}

pub(super) fn use_tree(walker: &mut Walker<'_>, prefix: &mut Vec<String>, tree: &UseTree) {
    match tree {
        UseTree::Path(path) => {
            prefix.push(plain(&path.ident));
            use_tree(walker, prefix, &path.tree);
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
                bind_leaf(walker, bound, prefix);
            }
            leaf(walker, prefix, &name.ident, bound);
        }
        UseTree::Rename(rename) => {
            let bound = plain(&rename.rename);
            bind_leaf(walker, bound.clone(), prefix);
            leaf(walker, prefix, &rename.ident, Some(bound));
        }
        UseTree::Glob(glob) => {
            walker.via = Via::Glob {
                reexport: walker.public_use,
                block: walker.blocks > 0,
            };
            let span = glob.star_token.spans[0];
            walker.refer_as(prefix, span, walker.absolute_use);
        }
        UseTree::Group(group) => {
            for item in &group.items {
                use_tree(walker, prefix, item);
            }
        }
    }
}

pub(super) fn leaf(
    walker: &mut Walker<'_>,
    prefix: &[String],
    name: &syn::Ident,
    binding: Option<String>,
) {
    walker.via = Via::Use {
        binding,
        reexport: walker.public_use,
        block: walker.blocks > 0,
    };
    let mut names = prefix.to_vec();
    // `use a::b::{self}` names the module `a::b`.
    if name != "self" {
        names.push(plain(name));
    }
    walker.refer_as(&names, name.span(), walker.absolute_use);
}

/// `extern crate foo;` names the crate `foo`. `extern crate self as name;` binds `name` to
/// the root of this crate, so `name::a::f` is a path into the module `a`.
pub(super) fn extern_crate(walker: &mut Walker<'_>, node: &ItemExternCrate) {
    let span = node.ident.span();
    walker.refer(&[plain(&node.ident)], span);
    if node.ident != "self" {
        let site = walker.site(span);
        walker.out.extern_crates.push((plain(&node.ident), site));
    }
    // A `cfg` may remove the alias, so a path that starts with its name may name the alias
    // or a crate of that name: the scan cannot say which.
    let gated = node
        .attrs
        .iter()
        .any(|a| a.path().is_ident("cfg") || a.path().is_ident("cfg_attr"));
    if let (true, Some((_, rename)), true) = (node.ident == "self", &node.rename, gated) {
        let reason = format!(
            "The alias {} of the crate has a cfg: a path that starts with it may name the alias or a crate",
            plain(rename)
        );
        concern(walker, reason, span);
        return;
    }
    if let (true, Some((_, rename))) = (node.ident == "self", &node.rename) {
        walker.via = Via::Use {
            binding: Some(plain(rename)),
            reexport: false,
            block: walker.blocks > 0,
        };
        walker.refer(&["crate".to_owned()], span);
        walker.via = Via::Path;
        if walker.blocks == 0 {
            walker
                .out
                .self_aliases
                .push((walker.inline.clone(), plain(rename)));
        }
    }
}
