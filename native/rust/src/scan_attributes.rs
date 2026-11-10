// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in an attribute: a path in its name, its tokens, its strings and the value
//! of `key = value`. The walker of `scan.rs` owns the facts; this file only fills them.

use proc_macro2::Span;
use syn::visit::Visit;
use syn::{Attribute, Expr, ExprLit, Lit, Meta};

use super::Walker;
use crate::net;
use crate::tokens::{attribute_chains, plain, read_value, string_paths, LINTS, MESSAGE_KEYS};

impl Walker<'_> {
    /// An attribute holds paths in its name, its tokens and its strings. `derive` is read like
    /// any other: it adds impls, so a path in it is an edge and it never hides one.
    pub(super) fn attribute(&mut self, attr: &Attribute) {
        let path = attr.path();
        // The text of a doc comment is no code. A `doc` with an expression is read below.
        let text =
            matches!(&attr.meta, Meta::NameValue(pair) if matches!(pair.value, Expr::Lit(_)));
        if path.is_ident("doc") && text {
            return;
        }
        let names: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
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
        if let Meta::List(list) = &attr.meta {
            net::walk(list.tokens.clone(), &mut self.out.mentioned);
        }
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
        net::note_string(&text.value(), &mut self.out.mentioned);
        let mut found = Vec::new();
        if read_value(&text.value(), text.span(), &mut found).is_none() {
            let reason = "A string in an attribute holds a path that the scan cannot read";
            self.concern(reason.to_owned(), text.span());
        }
        self.refer_chains(found);
    }

    /// The paths in the strings of an attribute, under any key but the message keys of `tokens`.
    fn attribute_strings(&mut self, list: &syn::MetaList) {
        let mut found = Vec::new();
        if string_paths(list.tokens.clone(), 0, &mut found).is_none() {
            let reason = "A string in an attribute holds a path that the scan cannot read";
            self.concern(reason.to_owned(), list.delimiter.span().join());
        }
        self.refer_chains(found);
    }
}
