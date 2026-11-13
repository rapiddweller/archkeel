// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in an attribute: a path in its name, its tokens, its strings and the value
//! of `key = value`. The walker of `scan.rs` owns the facts; this file only fills them.

use proc_macro2::Span;
use syn::visit::Visit;
use syn::{Attribute, Expr, ExprLit, Lit, Meta};

use super::Concern;
use super::Walker;
use crate::attrs::kinds::{self as attribute_kinds, Kind};
use crate::attrs::model::{Proof, Usage, KNOWN};
use crate::net;
use crate::tokens::{attribute_chains, plain, read_value, string_paths, LINTS, MESSAGE_KEYS};

impl Walker<'_> {
    pub(super) fn concern(&mut self, reason: String, span: Span) {
        let site = self.site(span);
        self.out.concerns.push(Concern {
            reason,
            site,
            source: None,
            proof: None,
        });
    }

    /// An attribute holds paths in its name, its tokens and its strings.
    pub(super) fn attribute(&mut self, attr: &Attribute) {
        self.expansion(&attr.meta, 0);
        let path = attr.path();
        // The text of a doc comment is no code. A `doc` with an expression is read below.
        let text =
            matches!(&attr.meta, Meta::NameValue(pair) if matches!(pair.value, Expr::Lit(_)));
        if path.is_ident("doc") && text {
            return;
        }
        let names: Vec<String> = path.segments.iter().map(|s| plain(&s.ident)).collect();
        if names.len() > 1 {
            self.out.tally.unseen += 1;
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
            let helper = !self.helpers.candidates.is_empty()
                && KNOWN
                    .iter()
                    .any(|k| k.helpers.iter().any(|name| path.is_ident(name)));
            if helper {
                self.helper_strings(attr, list);
            } else {
                self.attribute_strings(list);
            }
        }
        if let (Meta::NameValue(pair), false) = (&attr.meta, lint) {
            self.name_value(&names, &pair.value);
        }
    }

    fn helper_strings(&mut self, attr: &Attribute, list: &syn::MetaList) {
        let via = std::mem::replace(&mut self.via, super::Via::Helper);
        if let Some(found) = crate::attrs::model::helper_paths(attr) {
            self.refer_chains(found);
        } else {
            self.attribute_strings(list);
        }
        self.via = via;
    }

    fn expansion(&mut self, meta: &Meta, depth: usize) {
        let path = meta.path();
        let name = path
            .segments
            .iter()
            .map(|s| plain(&s.ident))
            .collect::<Vec<_>>()
            .join("::");
        match (depth < 16, attribute_kinds::kind(path)) {
            (true, Some(Kind::Builtin)) => return,
            (true, Some(Kind::Derive)) if self.derive_expansion(meta).is_some() => return,
            (true, Some(Kind::Conditional | Kind::Unsafe))
                if self.nested_expansion(meta, depth).is_some() =>
            {
                return
            }
            (true, None) if self.tools && attribute_kinds::tool(path) => return,
            _ => (),
        }
        let mut concern = self.expansion_concern(
            format!("The attribute macro {name} can add code that the scan does not read"),
            path.segments
                .first()
                .map_or(Span::call_site(), |s| s.ident.span()),
        );
        if (name == "default"
            || KNOWN
                .iter()
                .any(|known| known.helpers.contains(&name.as_str())))
            && !self.helpers.candidates.is_empty()
        {
            concern.proof = Some(Proof::Helper {
                namespace: name,
                candidates: self.helpers.candidates.clone(),
            });
        }
        self.out.concerns.push(concern);
    }

    fn derive_expansion(&mut self, meta: &Meta) -> Option<()> {
        for path in attribute_kinds::list::<syn::Path>(meta)? {
            let name = path
                .segments
                .iter()
                .map(|s| plain(&s.ident))
                .collect::<Vec<_>>()
                .join("::");
            let span = path
                .segments
                .first()
                .map_or(Span::call_site(), |s| s.ident.span());
            let mut concern = self.expansion_concern(
                format!("The derive macro {name} can add code that the scan does not read"),
                span,
            );
            let parts: Vec<_> = path.segments.iter().map(|s| plain(&s.ident)).collect();
            let complete = self
                .helpers
                .candidates
                .iter()
                .find(|c| c.path == parts)
                .is_some_and(|c| c.complete);
            concern.proof = Some(Proof::Derive(Usage {
                path: parts,
                absolute: path.leading_colon.is_some(),
                complete,
                block: self.blocks > 0,
                prelude: self.tools,
            }));
            self.derives.push(concern);
        }
        Some(())
    }

    fn nested_expansion(&mut self, meta: &Meta, depth: usize) -> Option<()> {
        let nested = attribute_kinds::list::<Meta>(meta)?;
        let skip = usize::from(meta.path().is_ident("cfg_attr"));
        for nested in nested.iter().skip(skip) {
            self.expansion(nested, depth + 1);
        }
        Some(())
    }

    fn expansion_concern(&self, reason: String, span: Span) -> Concern {
        Concern {
            reason,
            site: self.site(span),
            source: Some(self.inline.clone()),
            proof: None,
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

pub(super) fn finish(walker: &mut Walker<'_>) {
    // Namespace and lock proofs require the complete workspace, not this syntax walk.
    walker.out.concerns.append(&mut walker.derives);
}

pub(super) fn gate(walker: &mut Walker<'_>, attrs: &[Attribute], what: &str, span: Span) {
    if let Some(reason) = crate::attrs::hidden_by(attrs, what, walker.features) {
        walker.concern(reason, span);
    }
}
