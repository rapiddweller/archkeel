// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one Rust file: each path that starts at a crate name, each `mod` declaration, and
//! each thing that the scan cannot read (a concern, which becomes UNKNOWN).
//!
//! The scan does not know which names are crates. It records the first segment of each qualified
//! path, and `resolve.rs` decides which of them name a crate.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::visit::{self, Visit};
use syn::{Attribute, Item, ItemExternCrate, ItemMacro, ItemMod, ItemUse, Macro, UseTree};

use crate::attrs::{hidden_by, path_literal};
use crate::net;
use crate::tokens::{chains, plain, Chain};

/// Macros of the standard library and of `serde_json`. Their bodies are expressions, so a path
/// inside is a path of this file. A macro of another name that holds a path is UNKNOWN.
const KNOWN_MACROS: [&str; 33] = [
    "assert",
    "assert_eq",
    "assert_ne",
    "debug_assert",
    "debug_assert_eq",
    "debug_assert_ne",
    "format",
    "format_args",
    "print",
    "println",
    "eprint",
    "eprintln",
    "write",
    "writeln",
    "panic",
    "unreachable",
    "todo",
    "unimplemented",
    "vec",
    "matches",
    "dbg",
    "env",
    "option_env",
    "concat",
    "stringify",
    "line",
    "file",
    "column",
    "module_path",
    "include_str",
    "include_bytes",
    "cfg",
    "json",
];

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Site {
    pub line: i64,
    pub end_line: i64,
    pub column: i64,
    pub excerpt: String,
}

/// A qualified path, or a `use` leaf: its first segment and the path as written.
#[derive(Clone, Debug, PartialEq)]
pub struct Reference {
    pub root: String,
    pub path: String,
    pub site: Site,
    /// The path starts with `::`: its first segment is a crate, and no local name hides it.
    pub absolute: bool,
}

/// A place that the scan cannot read.
#[derive(Clone, Debug, PartialEq)]
pub struct Concern {
    pub reason: String,
    pub site: Site,
}

/// A `mod name;` declaration: its file is not in this file.
#[derive(Clone, Debug, PartialEq)]
pub struct Child {
    pub name: String,
    pub path: Option<String>,
    /// The names of the inline modules that enclose the declaration.
    pub inline: Vec<String>,
    pub site: Site,
}

#[derive(Debug, Default)]
pub struct Scan {
    pub references: Vec<Reference>,
    pub concerns: Vec<Concern>,
    pub children: Vec<Child>,
    /// Every name that the file declares or imports, in any namespace and at any depth. The scan
    /// does not decide which item a path means: a root that is also in this set is UNKNOWN.
    pub names: BTreeSet<String>,
    /// The names of `names` that can hide a crate. A name is left out only when its single
    /// source is a `use` leaf that the crate of that name itself provides (`use anyhow::anyhow;`):
    /// whichever item a path `anyhow::x` then picks, it lies in the crate `anyhow`.
    pub shadows: BTreeSet<String>,
    /// Every name that the file writes in any token, for the safety net of `collect.rs`.
    pub mentioned: BTreeSet<String>,
}

/// Scan one file. A syntax error is `Err` with its line.
pub fn scan(text: &str, features: &BTreeSet<String>) -> Result<Scan, String> {
    let file = syn::parse_file(text).map_err(|error| {
        format!(
            "unparseable construct at line {}",
            error.span().start().line
        )
    })?;
    let mut walker = Walker {
        lines: text.split('\n').collect(),
        features,
        inline: Vec::new(),
        absolute_use: false,
        out: Scan::default(),
    };
    walker.visit_file(&file);
    Ok(walker.out)
}

struct Walker<'a> {
    lines: Vec<&'a str>,
    features: &'a BTreeSet<String>,
    inline: Vec<String>,
    /// The `use` item that the walk is in starts with `::`.
    absolute_use: bool,
    out: Scan,
}

impl Walker<'_> {
    fn site(&self, span: Span) -> Site {
        let (start, end) = (span.start(), span.end());
        let line = self.lines.get(start.line.saturating_sub(1)).copied();
        let excerpt: String = line.unwrap_or("").trim().chars().take(200).collect();
        Site {
            line: to_i64(start.line),
            end_line: to_i64(end.line),
            column: to_i64(start.column),
            excerpt,
        }
    }

    /// A name that the file declares or imports, anywhere in it.
    fn bind(&mut self, name: String) {
        self.out.shadows.insert(name.clone());
        self.out.names.insert(name);
    }

    /// A `use` leaf binds `name`. When the path of the leaf starts with a crate of that same name,
    /// the binding is no shadow of that crate.
    fn bind_leaf(&mut self, name: String, prefix: &[String]) {
        if prefix.first() == Some(&name) {
            self.out.names.insert(name);
        } else {
            self.bind(name);
        }
    }

    fn concern(&mut self, reason: String, span: Span) {
        let site = self.site(span);
        self.out.concerns.push(Concern { reason, site });
    }

    fn refer(&mut self, names: &[String], span: Span) {
        self.refer_as(names, span, false);
    }

    fn refer_as(&mut self, names: &[String], span: Span, absolute: bool) {
        if let Some(first) = names.first() {
            let site = self.site(span);
            self.out.references.push(Reference {
                root: first.clone(),
                path: names.join("::"),
                site,
                absolute,
            });
        }
    }

    fn refer_chains(&mut self, found: Vec<Chain>) {
        for chain in found {
            self.refer_as(&chain.names, chain.span, chain.absolute);
        }
    }

    fn gate(&mut self, attrs: &[Attribute], what: &str, span: Span) {
        if let Some(reason) = hidden_by(attrs, what, self.features) {
            self.concern(reason, span);
        }
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
                bound
                    .into_iter()
                    .for_each(|bound| self.bind_leaf(bound, prefix));
                self.leaf(prefix, Some(&name.ident));
            }
            UseTree::Rename(rename) => {
                self.bind_leaf(plain(&rename.rename), prefix);
                self.leaf(prefix, Some(&rename.ident));
            }
            UseTree::Glob(glob) => {
                let span = glob.star_token.spans[0];
                self.leaf_at(prefix, span);
            }
            UseTree::Group(group) => {
                for item in &group.items {
                    self.use_tree(prefix, item);
                }
            }
        }
    }

    fn leaf(&mut self, prefix: &[String], name: Option<&syn::Ident>) {
        let Some(name) = name else { return };
        let mut names = prefix.to_vec();
        names.push(plain(name));
        self.refer_as(&names, name.span(), self.absolute_use);
    }

    fn leaf_at(&mut self, prefix: &[String], span: Span) {
        self.refer_as(prefix, span, self.absolute_use);
    }

    /// A `macro_rules!` definition. Its expansion stays in this crate, so its body is read as code
    /// of the file: a path is an edge, and a crate name in any token is checked by the net. An
    /// exported macro expands in other crates too, and those edges are not in this file: UNKNOWN.
    fn macro_rules(&mut self, node: &ItemMacro) {
        let span = node
            .mac
            .path
            .segments
            .first()
            .map_or(Span::call_site(), |s| s.ident.span());
        let name = node.ident.as_ref().map_or(String::new(), plain);
        if node
            .attrs
            .iter()
            .any(|attr| attr.path().is_ident("macro_export"))
        {
            let reason = format!(
                "The macro_rules! definition {name} is exported: it expands in other crates"
            );
            self.concern(reason, span);
        }
        net::walk(node.mac.tokens.clone(), &mut self.out.mentioned);
        match chains(node.mac.tokens.clone()) {
            Some(found) => self.refer_chains(found),
            None => self.concern(
                format!("The macro_rules! definition {name} is nested too deep to read"),
                span,
            ),
        }
        for attr in &node.attrs {
            self.attribute(attr);
        }
    }

    fn macro_call(&mut self, node: &Macro) {
        let Some(name) = node.path.segments.last().map(|s| plain(&s.ident)) else {
            return;
        };
        let span = node
            .path
            .segments
            .first()
            .map_or(Span::call_site(), |s| s.ident.span());
        if name == "include" {
            self.concern(
                "The macro include! adds code that the scan does not read".to_owned(),
                span,
            );
            return;
        }
        net::walk(node.tokens.clone(), &mut self.out.mentioned);
        let Some(found) = chains(node.tokens.clone()) else {
            self.concern(
                format!("The macro {name}! is nested too deep to read"),
                span,
            );
            return;
        };
        if KNOWN_MACROS.contains(&name.as_str()) {
            self.refer_chains(found);
        } else if !found.is_empty() {
            let reason = format!("The macro {name}! holds a path that the scan cannot read");
            self.concern(reason, span);
        }
    }
}

fn to_i64(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

/// The name that an item declares. Every kind counts, whatever its namespace.
fn item_name(item: &Item) -> Option<String> {
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

/// The name of an item of an `extern` block.
fn foreign_name(item: &syn::ForeignItem) -> Option<String> {
    let ident = match item {
        syn::ForeignItem::Fn(item) => &item.sig.ident,
        syn::ForeignItem::Static(item) => &item.ident,
        syn::ForeignItem::Type(item) => &item.ident,
        _ => return None,
    };
    Some(plain(ident))
}

impl<'ast> Visit<'ast> for Walker<'_> {
    fn visit_item(&mut self, item: &'ast Item) {
        if let Some(name) = item_name(item) {
            self.bind(name);
        }
        visit::visit_item(self, item);
    }

    fn visit_foreign_item(&mut self, item: &'ast syn::ForeignItem) {
        if let Some(name) = foreign_name(item) {
            self.bind(name);
        }
        visit::visit_foreign_item(self, item);
    }

    fn visit_attribute(&mut self, attr: &'ast Attribute) {
        self.attribute(attr);
    }

    fn visit_path(&mut self, path: &'ast syn::Path) {
        if path.segments.len() > 1 {
            let names: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
            if let Some(first) = path.segments.first() {
                self.refer_as(&names, first.ident.span(), path.leading_colon.is_some());
            }
        }
        visit::visit_path(self, path);
    }

    fn visit_lit_str(&mut self, text: &'ast syn::LitStr) {
        net::note_string(&text.value(), &mut self.out.mentioned);
    }

    fn visit_macro(&mut self, node: &'ast Macro) {
        self.macro_call(node);
        visit::visit_macro(self, node);
    }

    fn visit_item_macro(&mut self, node: &'ast ItemMacro) {
        if node.mac.path.is_ident("macro_rules") {
            self.macro_rules(node);
            return;
        }
        visit::visit_item_macro(self, node);
    }

    fn visit_item_extern_crate(&mut self, node: &'ast ItemExternCrate) {
        self.refer(&[plain(&node.ident)], node.ident.span());
    }

    fn visit_item_use(&mut self, node: &'ast ItemUse) {
        let span = node.use_token.span;
        self.gate(&node.attrs, "use", span);
        for attr in &node.attrs {
            self.attribute(attr);
        }
        self.absolute_use = node.leading_colon.is_some();
        self.use_tree(&mut Vec::new(), &node.tree);
        self.absolute_use = false;
    }

    fn visit_item_mod(&mut self, node: &'ast ItemMod) {
        let span = node.mod_token.span;
        self.gate(&node.attrs, "module", span);
        let name = plain(&node.ident);
        if node.content.is_none() {
            match path_literal(&node.attrs) {
                Ok(path) => {
                    let site = self.site(node.ident.span());
                    let inline = self.inline.clone();
                    self.out.children.push(Child {
                        name,
                        path,
                        inline,
                        site,
                    });
                }
                Err(reason) => self.concern(reason, span),
            }
            for attr in &node.attrs {
                self.attribute(attr);
            }
            return;
        }
        self.inline.push(name);
        visit::visit_item_mod(self, node);
        self.inline.pop();
    }
}

/// The read of an attribute: its path, its tokens, its strings and the value of `key = value`.
#[path = "scan_attributes.rs"]
mod attributes;

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
