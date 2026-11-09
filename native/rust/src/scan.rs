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
use syn::{Attribute, Item, ItemExternCrate, ItemMacro, ItemMod, ItemUse, Macro, Meta, UseTree};

use crate::attrs::{hidden_by, path_literal};
use crate::tokens::{attribute_chains, chains, string_paths, Chain, LINTS};

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
    /// Names that this file declares itself, so that a path with such a root is not a crate.
    pub declared: BTreeSet<String>,
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
        blocks: 0,
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
    /// How many blocks enclose the item that the walk is in: an item in a block is local to it.
    blocks: usize,
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

    /// A name that the file declares at its top level, in the namespace of types and modules,
    /// where the first segment of a `::` path is looked up. A function, a constant and a
    /// static are in the value namespace, so `fn serde_json() {}` does not hide `serde_json::x`.
    fn bind(&mut self, name: String) {
        if self.inline.is_empty() && self.blocks == 0 {
            self.out.declared.insert(name);
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

    /// An attribute holds paths in its name, its tokens and its strings. `derive` is read like
    /// any other: it adds impls, so a path in it is an edge and it never hides one.
    fn attribute(&mut self, attr: &Attribute) {
        let path = attr.path();
        if path.is_ident("doc") {
            return;
        }
        let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
        if names.len() > 1 {
            self.refer(
                &names,
                path.segments
                    .first()
                    .map_or(Span::call_site(), |s| s.ident.span()),
            );
        }
        // A lint attribute holds lint names and a `reason` text, not paths of the file.
        let lint = LINTS.iter().any(|lint| path.is_ident(lint));
        if let (Meta::List(list), false) = (&attr.meta, lint) {
            match attribute_chains(list.tokens.clone()) {
                Some(found) => self.refer_chains(found),
                None => self.concern(
                    "An attribute is nested too deep".to_owned(),
                    list.delimiter.span().join(),
                ),
            }
            self.attribute_strings(list);
        }
    }

    /// The paths in the strings of an attribute, under the keys of `tokens::PATH_KEYS`.
    fn attribute_strings(&mut self, list: &syn::MetaList) {
        let mut found = Vec::new();
        if string_paths(list.tokens.clone(), 0, &mut found).is_none() {
            let reason = "A string in an attribute holds a path that the scan cannot read";
            self.concern(reason.to_owned(), list.delimiter.span().join());
        }
        self.refer_chains(found);
    }

    fn gate(&mut self, attrs: &[Attribute], what: &str, span: Span) {
        if let Some(reason) = hidden_by(attrs, what, self.features) {
            self.concern(reason, span);
        }
    }

    fn use_tree(&mut self, prefix: &mut Vec<String>, tree: &UseTree) {
        match tree {
            UseTree::Path(path) => {
                prefix.push(path.ident.to_string());
                self.use_tree(prefix, &path.tree);
                prefix.pop();
            }
            UseTree::Name(name) => {
                // `use crate::a::serde_json;` declares a name; `use serde_json;` names the crate.
                if prefix
                    .first()
                    .is_some_and(|root| matches!(root.as_str(), "crate" | "self" | "super"))
                {
                    self.bind(name.ident.to_string());
                }
                self.leaf(prefix, Some(&name.ident));
            }
            UseTree::Rename(rename) => {
                self.bind(rename.rename.to_string());
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
        names.push(name.to_string());
        self.refer_as(&names, name.span(), self.absolute_use);
    }

    fn leaf_at(&mut self, prefix: &[String], span: Span) {
        self.refer_as(prefix, span, self.absolute_use);
    }

    fn macro_call(&mut self, node: &Macro) {
        let Some(name) = node.path.segments.last().map(|s| s.ident.to_string()) else {
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

fn item_name(item: &Item) -> Option<String> {
    let ident = match item {
        Item::Struct(item) => &item.ident,
        Item::Enum(item) => &item.ident,
        Item::Union(item) => &item.ident,
        Item::Trait(item) => &item.ident,
        Item::Type(item) => &item.ident,
        Item::Mod(item) => &item.ident,
        _ => return None,
    };
    Some(ident.to_string())
}

impl<'ast> Visit<'ast> for Walker<'_> {
    fn visit_item(&mut self, item: &'ast Item) {
        if let Some(name) = item_name(item) {
            self.bind(name);
        }
        visit::visit_item(self, item);
    }

    fn visit_block(&mut self, block: &'ast syn::Block) {
        self.blocks += 1;
        visit::visit_block(self, block);
        self.blocks -= 1;
    }

    fn visit_attribute(&mut self, attr: &'ast Attribute) {
        self.attribute(attr);
    }

    fn visit_path(&mut self, path: &'ast syn::Path) {
        if path.segments.len() > 1 {
            let names: Vec<String> = path.segments.iter().map(|s| s.ident.to_string()).collect();
            if let Some(first) = path.segments.first() {
                self.refer_as(&names, first.ident.span(), path.leading_colon.is_some());
            }
        }
        visit::visit_path(self, path);
    }

    fn visit_macro(&mut self, node: &'ast Macro) {
        self.macro_call(node);
        visit::visit_macro(self, node);
    }

    fn visit_item_macro(&mut self, node: &'ast ItemMacro) {
        if node.mac.path.is_ident("macro_rules") {
            let name = node
                .ident
                .as_ref()
                .map_or(String::new(), ToString::to_string);
            let span = node
                .mac
                .path
                .segments
                .first()
                .map_or(Span::call_site(), |s| s.ident.span());
            self.concern(
                format!("The macro_rules! definition {name} is not expanded"),
                span,
            );
            for attr in &node.attrs {
                self.attribute(attr);
            }
            return;
        }
        visit::visit_item_macro(self, node);
    }

    fn visit_item_extern_crate(&mut self, node: &'ast ItemExternCrate) {
        self.refer(&[node.ident.to_string()], node.ident.span());
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
        let name = node.ident.to_string();
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

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
