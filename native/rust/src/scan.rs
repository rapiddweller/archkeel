// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The facts of one Rust file: each path that starts at a crate name, each `mod` declaration, and
//! each thing that the scan cannot read (a concern, which becomes UNKNOWN).
//!
//! The scan does not know which names are crates. It records the first segment of each qualified
//! path, and `resolve.rs` decides which of them name a crate.

use std::collections::{BTreeMap, BTreeSet};

use proc_macro2::Span;
use syn::visit::{self, Visit};
use syn::{Attribute, Item, ItemExternCrate, ItemMacro, ItemMod, ItemUse, Macro};

use crate::attrs::{
    hidden_by, impl_item_attributes, is_test_attributes, item_attributes, path_literal,
    statement_attributes, trait_item_attributes, CFG_GATE_MODULE,
};
use crate::definitions::{Definition, Holder};
use crate::net;
pub use crate::site::Site;
use crate::tokens::{plain, Chain};

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

/// A qualified path, or a `use` leaf: its first segment and the path as written.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Reference {
    pub root: String,
    pub path: String,
    pub site: Site,
    /// The path starts with `::`: its first segment is a crate, and no local name hides it.
    pub absolute: bool,
    /// The segments of the path. A `use a::b::{self}` leaf is `a::b`.
    pub names: Vec<String>,
    /// The inline modules of the file that enclose the path: its lexical module.
    pub scope: Vec<String>,
    pub via: Via,
    /// The name of the `macro_rules!` definition whose body holds the path.
    pub in_macro: Option<String>,
}

/// A `macro_rules!` definition: the macros that its body calls, and the reasons why the scan
/// cannot read all of its body. Each call of the macro takes these reasons as UNKNOWN.
#[derive(Clone, Debug, PartialEq)]
pub struct MacroDef {
    pub name: String,
    pub calls: BTreeSet<String>,
    pub unknowns: Vec<String>,
}

/// A call of a macro. A call is placed when the scan reads it in code, and the macro is named by
/// a plain or a `crate::`, `self::` or `super::` path. A call in the tokens of another macro, or
/// by the path of a module, is not placed: the scan does not know which macro it names.
#[derive(Clone, Debug, PartialEq)]
pub struct MacroCall {
    pub name: String,
    pub site: Site,
    pub placed: bool,
}

/// How a reference comes into the file.
#[derive(Clone, Debug, Default, PartialEq)]
pub enum Via {
    /// A path in code, in an attribute or in the body of a macro call.
    #[default]
    Path,
    /// A leaf of a `use` item: the local name that it binds.
    Use {
        binding: Option<String>,
        reexport: bool,
        block: bool,
    },
    /// `use path::*`.
    Glob { reexport: bool, block: bool },
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
    /// A `cfg(test)` on the declaration, or on an item that holds it, marks a test module.
    pub test: bool,
    pub site: Site,
    /// The place of the gap that a `cfg` on the declaration gave, if it gave one.
    pub cfg_gate: Option<Site>,
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
    /// How many times the file declares or imports each name, in any namespace and at any depth.
    pub counts: BTreeMap<String, usize>,
    /// The inline modules of the file, each as the names from the file down.
    pub inlines: Vec<Vec<String>>,
    pub macro_defs: Vec<MacroDef>,
    /// The calls of macros in the file, placed or not.
    pub macro_calls: Vec<MacroCall>,
    /// Every name that the file writes in any token, for the safety net of `collect.rs`.
    pub mentioned: BTreeSet<String>,
    /// The items, the members of the inherent `impl` blocks and the members of the traits.
    pub definitions: Vec<Definition>,
}

/// Scan one file. A syntax error is `Err` with its line. With `exclude_tests`, an item that only
/// a test build compiles gives no fact, except the `mod x;` files below it, which are test scope.
pub fn scan(text: &str, features: &BTreeSet<String>, exclude_tests: bool) -> Result<Scan, String> {
    let file = syn::parse_file(text).map_err(|error| {
        format!(
            "unparseable construct at line {}",
            error.span().start().line
        )
    })?;
    let mut walker = Walker {
        lines: text.split('\n').collect(),
        features,
        exclude_tests,
        inline: Vec::new(),
        absolute_use: false,
        public_use: false,
        blocks: 0,
        in_macro: None,
        via: Via::Path,
        holder: Holder::default(),
        out: Scan::default(),
    };
    walker.visit_file(&file);
    Ok(walker.out)
}

struct Walker<'a> {
    lines: Vec<&'a str>,
    features: &'a BTreeSet<String>,
    exclude_tests: bool,
    inline: Vec<String>,
    /// The `use` item that the walk is in starts with `::`.
    absolute_use: bool,
    /// The `use` item that the walk is in is `pub`: it re-exports.
    public_use: bool,
    /// The depth of the blocks (function bodies) that enclose the walk.
    blocks: usize,
    /// The name of the `macro_rules!` definition that the walk is in.
    in_macro: Option<String>,
    /// What the next reference is: set by the `use` handling, `Path` otherwise.
    via: Via,
    /// What the walk is inside: it decides which members are definitions.
    holder: Holder,
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
                names: names.to_vec(),
                scope: self.inline.clone(),
                via: self.via.clone(),
                in_macro: self.in_macro.clone(),
            });
        }
    }

    fn refer_chains(&mut self, found: Vec<Chain>) {
        for chain in found {
            self.refer_as(&chain.names, chain.span, chain.absolute);
        }
    }

    /// Record what the attributes hide. The result is the place of a gap that a `cfg` gave.
    fn gate(&mut self, attrs: &[Attribute], what: &str, span: Span) -> Option<Site> {
        let reason = hidden_by(attrs, what, self.features)?;
        let cfg = reason.starts_with(CFG_GATE_MODULE).then(|| self.site(span));
        self.concern(reason, span);
        cfg
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
        if self.exclude_tests && is_test_attributes(item_attributes(item)) {
            // Keep only the files of `mod x;` below: the tree must claim them as test scope.
            let kept = std::mem::take(&mut self.out);
            visit::visit_item(self, item);
            let found = std::mem::replace(&mut self.out, kept).children;
            let tests = found.into_iter().map(|child| Child {
                test: true,
                ..child
            });
            self.out.children.extend(tests);
            return;
        }
        if let Some(name) = item_name(item) {
            self.bind(name);
        }
        self.define(item);
        let outer = match item {
            Item::Impl(item) if self.blocks == 0 => Some(self.enter_impl(item)),
            Item::Trait(item) if self.blocks == 0 => Some(self.enter_trait(item)),
            _ => None,
        };
        visit::visit_item(self, item);
        if let Some(holder) = outer {
            self.holder = holder;
        }
    }

    fn visit_impl_item(&mut self, item: &'ast syn::ImplItem) {
        if !(self.exclude_tests && is_test_attributes(impl_item_attributes(item))) {
            self.define_impl_item(item);
            visit::visit_impl_item(self, item);
        }
    }

    fn visit_trait_item(&mut self, item: &'ast syn::TraitItem) {
        if !(self.exclude_tests && is_test_attributes(trait_item_attributes(item))) {
            self.define_trait_item(item);
            visit::visit_trait_item(self, item);
        }
    }

    fn visit_stmt(&mut self, stmt: &'ast syn::Stmt) {
        if !(self.exclude_tests && is_test_attributes(statement_attributes(stmt))) {
            visit::visit_stmt(self, stmt);
        }
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
        self.extern_crate(node);
    }

    fn visit_block(&mut self, node: &'ast syn::Block) {
        self.blocks += 1;
        visit::visit_block(self, node);
        self.blocks -= 1;
    }

    /// `pub(in crate::a)` restricts visibility: it is no use of the module `a`.
    fn visit_visibility(&mut self, _: &'ast syn::Visibility) {}

    fn visit_item_use(&mut self, node: &'ast ItemUse) {
        let span = node.use_token.span;
        self.gate(&node.attrs, "use", span);
        for attr in &node.attrs {
            self.attribute(attr);
        }
        self.use_item(node);
    }

    fn visit_item_mod(&mut self, node: &'ast ItemMod) {
        let span = node.mod_token.span;
        let cfg_gate = self.gate(&node.attrs, "module", span);
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
                        test: is_test_attributes(&node.attrs),
                        site,
                        cfg_gate,
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
        self.out.inlines.push(self.inline.clone());
        visit::visit_item_mod(self, node);
        self.inline.pop();
    }
}

/// The read of an attribute: its path, its tokens, its strings and the value of `key = value`.
#[path = "scan_attributes.rs"]
mod attributes;

/// The read of `macro_rules!` definitions and macro calls: what their bodies hold.
#[path = "scan_macros.rs"]
mod macros;

/// The read of the items that a file defines: names, forms and visibility.
#[path = "scan_definitions.rs"]
mod define;

/// The read of a `use` item: its leaves, the names that they bind and the globs.
#[path = "scan_use.rs"]
mod use_items;

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
