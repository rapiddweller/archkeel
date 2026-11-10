// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `macro_rules!` definition and in a macro call. The walker of
//! `scan.rs` owns the facts; this file only fills them.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::{ItemMacro, Macro};

use super::{MacroDef, Walker, KNOWN_MACROS};
use crate::net;
use crate::tokens::{chains, macro_names, names_relative, plain, string_paths};

impl Walker<'_> {
    /// A `macro_rules!` definition. Its expansion stays in this crate, so its body is read as code
    /// of the file: a path is an edge, and a crate name in any token is checked by the net. An
    /// exported macro expands in other crates too, and those edges are not in this file: UNKNOWN.
    pub(super) fn macro_rules(&mut self, node: &ItemMacro) {
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
        if names_relative(node.mac.tokens.clone()) {
            let reason = format!(
                "The macro_rules! definition {name} names crate, super or self: the scan does not know where it expands"
            );
            self.concern(reason, span);
        }
        self.in_macro = Some(name.clone());
        let mut calls = BTreeSet::new();
        macro_names(node.mac.tokens.clone(), 0, &mut calls);
        self.out.macro_defs.push(MacroDef {
            name: name.clone(),
            calls,
        });
        let mut found = Vec::new();
        let strings = string_paths(node.mac.tokens.clone(), 0, &mut found);
        match chains(node.mac.tokens.clone()).filter(|_| strings.is_some()) {
            Some(more) => {
                found.extend(more);
                self.refer_chains(found);
            }
            None => self.concern(
                format!("The macro_rules! definition {name} is nested too deep to read"),
                span,
            ),
        }
        self.in_macro = None;
        for attr in &node.attrs {
            self.attribute(attr);
        }
    }

    pub(super) fn macro_call(&mut self, node: &Macro) {
        let Some(name) = node.path.segments.last().map(|s| plain(&s.ident)) else {
            return;
        };
        let span = node
            .path
            .segments
            .first()
            .map_or(Span::call_site(), |s| s.ident.span());
        let local = node.path.segments.len() == 1
            || node.path.segments.first().is_some_and(|first| {
                ["crate", "self", "super"].contains(&first.ident.to_string().as_str())
            });
        if local {
            let site = self.site(span);
            self.out.macro_calls.push((name.clone(), site));
        }
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
