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
    impl_item_attributes, is_test_attributes, item_attributes, path_literal, statement_attributes,
    trait_item_attributes,
};
use crate::definitions::{Definition, Holder, ImplBlock, MethodCall, OnSelf};
use crate::net;
use crate::plant;
pub(crate) use crate::site::Site;
use crate::tokens::{plain, Chain};
use define::{foreign_name, item_name};
use receivers::Selves;

/// A qualified path, or a `use` leaf: its first segment and the path as written.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct Reference {
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
    /// The `MacroDef::id` of that definition, in the file of the path.
    pub macro_id: usize,
}

/// How a reference comes into the file.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) enum Via {
    /// A path in code, in an attribute or in the body of a macro call.
    #[default]
    Path,
    /// A validated derive-helper path, including a bare child-module name.
    Helper,
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
pub(crate) struct Concern {
    pub reason: String,
    pub site: Site,
    /// Known source module, relative to the file. The expansion target is unseen.
    pub source: Option<Vec<String>>,
    pub proof: Option<crate::attrs::model::Proof>,
}

/// A `mod name;` declaration: its file is not in this file.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct Child {
    pub name: String,
    pub path: Option<String>,
    /// The names of the inline modules that enclose the declaration.
    pub inline: Vec<String>,
    /// A `cfg(test)` on the declaration, or on an item that holds it, marks a test module.
    pub test: bool,
    /// The declaration, or an inline module that holds it, may be removed by a `cfg` (AD-383).
    pub gated: bool,
    pub site: Site,
}

#[derive(Debug, Default)]
pub(crate) struct Scan {
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
    /// The crate of each `extern crate name;` other than `self`, and its place.
    pub extern_crates: Vec<(String, Site)>,
    /// The inherent `impl` blocks at any depth, and the method calls (#953).
    pub impls: Vec<ImplBlock>,
    pub method_calls: Vec<MethodCall>,
    /// The structs and enums at module level that are in every configuration (AD-383).
    pub exact_types: BTreeSet<String>,
    /// An inner attribute of the file may remove the module in some configuration.
    pub gated_file: bool,
    /// The second count of the tree, for the invariant of the extraction.
    pub tally: Tally,
}

/// Scan one file. A syntax error is `Err` with its line. With `exclude_tests`, an item that only
/// a test build compiles gives no fact, except the `mod x;` files below it, which are test scope.
pub(crate) fn scan(
    text: &str,
    features: &BTreeSet<String>,
    exclude_tests: bool,
) -> Result<Scan, String> {
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
        block_ends: Vec::new(),
        via: Via::Path,
        holder: Holder::default(),
        selves: Selves::default(),
        helpers: crate::attrs::model::Context::default(),
        tools: !crate::attrs::kinds::no_tools(&file.attrs),
        derives: Vec::new(),
        out: Scan {
            tally: Tally::of(&file, exclude_tests),
            ..Scan::default()
        },
    };
    walker.out.gated_file = !receivers::module_inert(&file.attrs);
    walker.visit_file(&file);
    attributes::finish(&mut walker);
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
    /// The end of each block that encloses the walk, the inner block last.
    block_ends: Vec<(i64, i64)>,
    /// What the next reference is: set by the `use` handling, `Path` otherwise.
    via: Via,
    /// What the walk is inside: it decides which members are definitions.
    holder: Holder,
    /// What a plain `self` is at the walk (AD-383).
    selves: Selves,
    helpers: crate::attrs::model::Context,
    tools: bool,
    derives: Vec<Concern>,
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

    /// A call `x.m(..)` (`path` false), or a path call that the scan cannot resolve (`path` true).
    fn method_call(&mut self, name: String, span: Span, (path, arity): (bool, Option<usize>)) {
        self.method_call_on(name, span, (path, arity), None);
    }

    fn method_call_on(
        &mut self,
        name: String,
        span: Span,
        (path, arity): (bool, Option<usize>),
        on_self: Option<OnSelf>,
    ) {
        let (site, scope) = (self.site(span), self.inline.clone());
        if plant::lose("method") {
            return;
        }
        self.out.method_calls.push(MethodCall {
            name,
            site,
            scope,
            path,
            arity,
            on_self,
        });
    }

    fn refer(&mut self, names: &[String], span: Span) {
        self.refer_as(names, span, false);
    }

    fn refer_as(&mut self, names: &[String], span: Span, absolute: bool) {
        if let Some(first) = names.first() {
            if plant::lose("reference") {
                return;
            }
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
                macro_id: self.out.macro_defs.len(),
            });
        }
    }

    fn refer_chains(&mut self, found: Vec<Chain>) {
        let before = self.out.references.len();
        for chain in found {
            self.refer_as(&chain.names, chain.span, chain.absolute);
        }
        self.out.tally.unseen += self.out.references.len() - before;
    }
}

fn to_i64(value: usize) -> i64 {
    i64::try_from(value).unwrap_or(i64::MAX)
}

impl<'ast> Visit<'ast> for Walker<'_> {
    fn visit_item(&mut self, item: &'ast Item) {
        if self.exclude_tests && is_test_attributes(item_attributes(item)) {
            // Keep only the files of `mod x;` below: the tree must claim them as test scope.
            let kept = std::mem::take(&mut self.out);
            let derives = self.derives.len();
            visit::visit_item(self, item);
            self.derives.truncate(derives);
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
        if let Item::Impl(found) = item {
            self.impl_block(found);
            self.selves.enter_impl(found, &self.inline, self.blocks);
        } else if let Item::Fn(_) = item {
            self.selves.enter_opaque();
        }
        self.exact_type(item);
        let outer = match item {
            Item::Impl(item) if self.blocks == 0 => Some(self.enter_impl(item)),
            Item::Trait(item) if self.blocks == 0 => Some(self.enter_trait(item)),
            _ => None,
        };
        let tools = self.tools;
        self.tools &= !crate::attrs::kinds::no_tools(item_attributes(item));
        let helpers = std::mem::replace(
            &mut self.helpers,
            crate::attrs::model::Context::of(item, self.blocks > 0, self.tools),
        );
        visit::visit_item(self, item);
        self.helpers = helpers;
        self.tools = tools;
        if let Some(holder) = outer {
            self.holder = holder;
        }
        if matches!(item, Item::Impl(_) | Item::Fn(_)) {
            self.selves.leave();
        }
    }

    fn visit_impl_item(&mut self, item: &'ast syn::ImplItem) {
        if !(self.exclude_tests && is_test_attributes(impl_item_attributes(item))) {
            self.define_impl_item(item);
            if let syn::ImplItem::Fn(method) = item {
                self.selves.enter_method(&method.sig, &method.attrs);
            }
            visit::visit_impl_item(self, item);
            if let syn::ImplItem::Fn(_) = item {
                self.selves.leave();
            }
        }
    }

    fn visit_trait_item(&mut self, item: &'ast syn::TraitItem) {
        if !(self.exclude_tests && is_test_attributes(trait_item_attributes(item))) {
            self.define_trait_item(item);
            self.selves.enter_opaque();
            visit::visit_trait_item(self, item);
            self.selves.leave();
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

    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        let (arity, on_self) = (Some(node.args.len()), self.selves.of(&node.receiver));
        let name = plain(&node.method);
        self.method_call_on(name, node.method.span(), (false, arity), on_self);
        visit::visit_expr_method_call(self, node);
    }

    /// `<T>::m(..)` names `T` in its qualified self; the scan does not resolve the member (#953).
    fn visit_expr_path(&mut self, node: &'ast syn::ExprPath) {
        if let (Some(_), Some(last)) = (&node.qself, node.path.segments.last()) {
            self.method_call(plain(&last.ident), last.ident.span(), (true, None));
        }
        // `Self::m` names a member of the type of the block (AD-383).
        if let Some(last) = receivers::self_member(node) {
            let on_self = self.selves.of_type();
            self.method_call_on(plain(last), last.span(), (true, None), on_self);
        }
        visit::visit_expr_path(self, node);
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
        let end = node.brace_token.span.close().end();
        self.block_ends.push((to_i64(end.line), to_i64(end.column)));
        self.blocks += 1;
        visit::visit_block(self, node);
        self.blocks -= 1;
        self.block_ends.pop();
    }

    /// `pub(in crate::a)` restricts visibility: it is no use of the module `a`.
    fn visit_visibility(&mut self, _: &'ast syn::Visibility) {}

    fn visit_item_use(&mut self, node: &'ast ItemUse) {
        let span = node.use_token.span;
        attributes::gate(self, &node.attrs, "use", span);
        for attr in &node.attrs {
            self.attribute(attr);
        }
        self.use_item(node);
    }

    fn visit_item_mod(&mut self, node: &'ast ItemMod) {
        let span = node.mod_token.span;
        attributes::gate(self, &node.attrs, "module", span);
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
                        gated: !receivers::module_inert(&node.attrs) || self.selves.gated(),
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
        for attr in &node.attrs {
            self.attribute(attr);
        }
        self.inline.push(name);
        self.out.inlines.push(self.inline.clone());
        self.selves.enter_module(&node.attrs);
        if let Some((_, items)) = &node.content {
            for item in items {
                self.visit_item(item);
            }
        }
        self.selves.leave_module();
        self.inline.pop();
    }
}

/// The read of an attribute: its path, its tokens, its strings and the value of `key = value`.
#[path = "scan_attributes.rs"]
mod attributes;

/// The read of `macro_rules!` definitions and macro calls: what their bodies hold.
#[path = "scan_macros.rs"]
mod macros;
pub(crate) use macros::{MacroCall, MacroDef};

/// The second count of the nodes that must end as an outcome (`edges_extracted.rs`).
#[path = "scan_extracted.rs"]
mod extracted;
pub(crate) use extracted::Tally;

/// The read of the items that a file defines: names, forms and visibility.
#[path = "scan_definitions.rs"]
mod define;

/// What a plain `self` receiver is: the type of its `impl` block and its kind (AD-383).
#[path = "scan_receivers.rs"]
mod receivers;

/// The read of a `use` item: its leaves, the names that they bind and the globs.
#[path = "scan_use.rs"]
mod use_items;

#[cfg(test)]
#[path = "scan_tests.rs"]
mod tests;
