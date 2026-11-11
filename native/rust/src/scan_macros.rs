// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `macro_rules!` definition and in a macro call. The walker of
//! `scan.rs` owns the facts; this file only fills them.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::{ItemMacro, Macro};

use super::{Local, MacroCall, MacroDef, Walker, KNOWN_MACROS};
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
        let exported = node
            .attrs
            .iter()
            .any(|attr| attr.path().is_ident("macro_export"));
        if exported {
            let reason = format!(
                "The macro_rules! definition {name} is exported: it expands in other crates"
            );
            self.concern(reason, span);
        }
        // An exported macro is UNKNOWN above; the reasons below belong to each call in this crate.
        let first_unknown = self.out.concerns.len();
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
        let unknowns = (self.out.concerns.iter().skip(first_unknown))
            .map(|concern| concern.reason.clone())
            .collect();
        // A macro of a function body is scoped to the rest of that body. An exported one is also
        // a path at the crate root, so it stays crate-wide.
        let from = self.site(span);
        let local = self
            .block_ends
            .last()
            .filter(|_| !exported)
            .map(|until| Local {
                from: (from.line, from.column),
                until: *until,
            });
        self.out.macro_defs.push(MacroDef {
            name,
            id: self.out.macro_defs.len(),
            calls,
            unknowns,
            local,
        });
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
        let site = self.site(span);
        let call = MacroCall {
            name: name.clone(),
            site,
            placed: local,
        };
        // The tokens of a macro are not code that the scan reads: a call in them is not placed.
        let mut inner = BTreeSet::new();
        macro_names(node.tokens.clone(), 0, &mut inner);
        let hidden = inner.into_iter().map(|name| MacroCall {
            name,
            placed: false,
            ..call.clone()
        });
        self.out.macro_calls.extend(hidden);
        self.out.macro_calls.push(call);
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
