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
use syn::{
    Attribute, Expr, ExprLit, Item, ItemExternCrate, ItemMacro, ItemMod, ItemUse, Lit, Macro, Meta,
};

use crate::attrs::model::KNOWN;
use crate::attrs::{
    impl_item_attributes, is_test_attributes, item_attributes, path_literal, statement_attributes,
    trait_item_attributes,
};
use crate::definitions::Holder;
use crate::net;
pub(crate) use crate::site::Site;
use crate::tokens::{attribute_chains, plain, read_value, LINTS, MESSAGE_KEYS};
use attributes::{attribute_strings, concern, expansion, helper_strings};
use define::{
    define_impl_item, define_item, define_trait_item, enter_impl, enter_trait, exact_type,
    foreign_name, impl_block,
};
use macros::{macro_call, macro_rules};
use receivers::{item_name, Selves};
use use_items::{bind, extern_crate, use_item};

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
    let mut visitor = Visitor {
        walker: Walker {
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
        },
    };
    visitor.walker.out.gated_file = !receivers::module_inert(&file.attrs);
    visitor.visit_file(&file);
    attributes::finish(&mut visitor.walker);
    Ok(visitor.walker.out)
}

/// The walk of a file: the state that the files below fill, and the visit of the syntax tree.
struct Visitor<'a> {
    walker: Walker<'a>,
}

impl Visitor<'_> {
    /// An attribute holds paths in its name, its tokens and its strings.
    pub(super) fn attribute(&mut self, attr: &Attribute) {
        expansion(&mut self.walker, &attr.meta, 0);
        let path = attr.path();
        // The text of a doc comment is no code. A `doc` with an expression is read below.
        let text =
            matches!(&attr.meta, Meta::NameValue(pair) if matches!(pair.value, Expr::Lit(_)));
        if path.is_ident("doc") && text {
            return;
        }
        let names: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
        if names.len() > 1 {
            self.walker.out.tally.unseen += 1;
            self.walker.refer(
                &names,
                path.segments
                    .first()
                    .map_or(Span::call_site(), |s| s.ident.span()),
            );
        }
        // A lint attribute holds lint names and a `reason` text, not paths of the file.
        let lint = LINTS.iter().any(|lint| path.is_ident(lint));
        if let Meta::List(list) = &attr.meta {
            net::walk(list.tokens.clone(), &mut self.walker.out.mentioned);
        }
        if let (Meta::List(list), false) = (&attr.meta, lint) {
            match attribute_chains(list.tokens.clone()) {
                Some(found) => self.walker.refer_chains(found),
                None => concern(
                    &mut self.walker,
                    "An attribute is nested too deep".to_owned(),
                    list.delimiter.span().join(),
                ),
            }
            let helper = !self.walker.helpers.candidates.is_empty()
                && KNOWN
                    .iter()
                    .any(|k| k.helpers.iter().any(|name| path.is_ident(name)));
            if helper {
                helper_strings(&mut self.walker, attr, list);
            } else {
                attribute_strings(&mut self.walker, list);
            }
        }
        if let (Meta::NameValue(pair), false) = (&attr.meta, lint) {
            self.name_value(&names, &pair.value);
        }
    }

    /// The value of `key = value`. A string is read as under any key of a list; another
    /// expression (`doc = crate_a::readme!()`) is walked like code.
    fn name_value(&mut self, key: &[String], value: &Expr) {
        let Expr::Lit(ExprLit { lit, .. }) = value else {
            self.visit_expr(value);
            return;
        };
        let (Lit::Str(text), Some(name)) = (lit, key.last()) else {
            return;
        };
        if MESSAGE_KEYS.contains(&name.as_str()) {
            return;
        }
        net::note_string(&text.value(), &mut self.walker.out.mentioned);
        let mut found = Vec::new();
        if read_value(&text.value(), text.span(), &mut found).is_none() {
            let reason = "A string in an attribute holds a path that the scan cannot read";
            concern(&mut self.walker, reason.to_owned(), text.span());
        }
        self.walker.refer_chains(found);
    }
}

impl<'ast> Visit<'ast> for Visitor<'_> {
    fn visit_item(&mut self, item: &'ast Item) {
        if self.walker.exclude_tests && is_test_attributes(item_attributes(item)) {
            // Keep only the files of `mod x;` below: the tree must claim them as test scope.
            let kept = std::mem::take(&mut self.walker.out);
            let derives = self.walker.derives.len();
            visit::visit_item(self, item);
            self.walker.derives.truncate(derives);
            let found = std::mem::replace(&mut self.walker.out, kept).children;
            let tests = found.into_iter().map(|child| Child {
                test: true,
                ..child
            });
            self.walker.out.children.extend(tests);
            return;
        }
        if let Some(name) = item_name(item) {
            bind(&mut self.walker, name);
        }
        define_item(&mut self.walker, item);
        if let Item::Impl(found) = item {
            impl_block(&mut self.walker, found);
            self.walker
                .selves
                .enter_impl(found, &self.walker.inline, self.walker.blocks);
        } else if let Item::Fn(found) = item {
            let at = (&self.walker.inline[..], self.walker.blocks);
            self.walker.selves.enter_function(found, at);
        }
        exact_type(&mut self.walker, item);
        let outer = match item {
            Item::Impl(item) if self.walker.blocks == 0 => Some(enter_impl(&mut self.walker, item)),
            Item::Trait(item) if self.walker.blocks == 0 => {
                Some(enter_trait(&mut self.walker, item))
            }
            _ => None,
        };
        let tools = self.walker.tools;
        self.walker.tools &= !crate::attrs::kinds::no_tools(item_attributes(item));
        let helpers = std::mem::replace(
            &mut self.walker.helpers,
            crate::attrs::model::Context::of(item, self.walker.blocks > 0, self.walker.tools),
        );
        visit::visit_item(self, item);
        self.walker.helpers = helpers;
        self.walker.tools = tools;
        if let Some(holder) = outer {
            self.walker.holder = holder;
        }
        if matches!(item, Item::Impl(_) | Item::Fn(_)) {
            self.walker.selves.leave();
        }
    }

    fn visit_impl_item(&mut self, item: &'ast syn::ImplItem) {
        if !(self.walker.exclude_tests && is_test_attributes(impl_item_attributes(item))) {
            define_impl_item(&mut self.walker, item);
            if let syn::ImplItem::Fn(method) = item {
                let at = (&self.walker.inline[..], self.walker.blocks);
                self.walker.selves.enter_method(method, at);
            }
            visit::visit_impl_item(self, item);
            if let syn::ImplItem::Fn(_) = item {
                self.walker.selves.leave();
            }
        }
    }

    fn visit_trait_item(&mut self, item: &'ast syn::TraitItem) {
        if !(self.walker.exclude_tests && is_test_attributes(trait_item_attributes(item))) {
            define_trait_item(&mut self.walker, item);
            self.walker.selves.enter_opaque();
            visit::visit_trait_item(self, item);
            self.walker.selves.leave();
        }
    }

    fn visit_stmt(&mut self, stmt: &'ast syn::Stmt) {
        if !(self.walker.exclude_tests && is_test_attributes(statement_attributes(stmt))) {
            visit::visit_stmt(self, stmt);
        }
    }

    fn visit_foreign_item(&mut self, item: &'ast syn::ForeignItem) {
        if let Some(name) = foreign_name(item) {
            bind(&mut self.walker, name);
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
                self.walker
                    .refer_as(&names, first.ident.span(), path.leading_colon.is_some());
            }
        }
        visit::visit_path(self, path);
    }

    fn visit_expr_method_call(&mut self, node: &'ast syn::ExprMethodCall) {
        let (arity, on_self) = (Some(node.args.len()), self.walker.selves.of(&node.receiver));
        let name = plain(&node.method);
        self.walker
            .method_call_on(name, node.method.span(), (false, arity), on_self);
        visit::visit_expr_method_call(self, node);
    }

    /// `<T>::m(..)` names `T` in its qualified self; the scan does not resolve the member (#953).
    fn visit_expr_path(&mut self, node: &'ast syn::ExprPath) {
        if let (Some(_), Some(last)) = (&node.qself, node.path.segments.last()) {
            self.walker
                .method_call(plain(&last.ident), last.ident.span(), (true, None));
        }
        // `Self::m` names a member of the type of the block (AD-383).
        if let Some(last) = receivers::self_member(node) {
            let on_self = self.walker.selves.of_type();
            self.walker
                .method_call_on(plain(last), last.span(), (true, None), on_self);
        }
        visit::visit_expr_path(self, node);
    }

    fn visit_lit_str(&mut self, text: &'ast syn::LitStr) {
        net::note_string(&text.value(), &mut self.walker.out.mentioned);
    }

    fn visit_macro(&mut self, node: &'ast Macro) {
        macro_call(&mut self.walker, node);
        visit::visit_macro(self, node);
    }

    fn visit_item_macro(&mut self, node: &'ast ItemMacro) {
        if node.mac.path.is_ident("macro_rules") {
            macro_rules(&mut self.walker, node);
            for attr in &node.attrs {
                self.attribute(attr);
            }
            return;
        }
        visit::visit_item_macro(self, node);
    }

    fn visit_item_extern_crate(&mut self, node: &'ast ItemExternCrate) {
        extern_crate(&mut self.walker, node);
    }

    fn visit_block(&mut self, node: &'ast syn::Block) {
        let end = node.brace_token.span.close().end();
        self.walker
            .block_ends
            .push((to_i64(end.line), to_i64(end.column)));
        self.walker.blocks += 1;
        visit::visit_block(self, node);
        self.walker.blocks -= 1;
        self.walker.block_ends.pop();
    }

    /// `pub(in crate::a)` restricts visibility: it is no use of the module `a`.
    fn visit_visibility(&mut self, _: &'ast syn::Visibility) {}

    fn visit_item_use(&mut self, node: &'ast ItemUse) {
        let span = node.use_token.span;
        attributes::gate(&mut self.walker, &node.attrs, "use", span);
        for attr in &node.attrs {
            self.attribute(attr);
        }
        use_item(&mut self.walker, node);
    }

    fn visit_item_mod(&mut self, node: &'ast ItemMod) {
        let span = node.mod_token.span;
        attributes::gate(&mut self.walker, &node.attrs, "module", span);
        let name = plain(&node.ident);
        if node.content.is_none() {
            match path_literal(&node.attrs) {
                Ok(path) => {
                    let site = self.walker.site(node.ident.span());
                    let inline = self.walker.inline.clone();
                    self.walker.out.children.push(Child {
                        name,
                        path,
                        inline,
                        test: is_test_attributes(&node.attrs),
                        gated: !receivers::module_inert(&node.attrs) || self.walker.selves.gated(),
                        site,
                    });
                }
                Err(reason) => concern(&mut self.walker, reason, span),
            }
            for attr in &node.attrs {
                self.attribute(attr);
            }
            return;
        }
        for attr in &node.attrs {
            self.attribute(attr);
        }
        self.walker.inline.push(name);
        self.walker.out.inlines.push(self.walker.inline.clone());
        self.walker.selves.enter_module(&node.attrs);
        if let Some((_, items)) = &node.content {
            for item in items {
                self.visit_item(item);
            }
        }
        self.walker.selves.leave_module();
        self.walker.inline.pop();
    }
}

/// The state of the scan: the facts and the walker that holds them.
#[path = "scan_state.rs"]
mod state;
use state::{to_i64, Walker};
pub(crate) use state::{Child, Concern, MacroCall, MacroDef, Reference, Scan, Via};

/// The read of an attribute: its path, its tokens, its strings and the value of `key = value`.
#[path = "scan_attributes.rs"]
mod attributes;

/// The read of `macro_rules!` definitions and macro calls: what their bodies hold.
#[path = "scan_macros.rs"]
mod macros;

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
