// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `macro_rules!` definition and in a macro call. The walker of
//! `scan.rs` owns the facts; this file only fills them.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::{ItemMacro, Macro};

use super::Walker;
use crate::definitions::{Holder, MethodCall};
use crate::net;
use crate::plant;
use crate::site::Site;
use crate::tokens::{
    chains, fn_names, macro_names, method_names, names_relative, plain, string_paths,
};

/// A `macro_rules!` definition: the macros that its body calls, and the reasons why the scan
/// cannot read all of its body. Each call of the macro takes these reasons as UNKNOWN.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct MacroDef {
    pub name: String,
    /// The place of the definition in the macro list of its file.
    pub id: usize,
    pub calls: BTreeSet<String>,
    /// The methods that the body calls: each call of the macro calls them too (#953).
    pub methods: BTreeSet<String>,
    /// The functions that the body defines: a call of the macro may add them as members of an
    /// `impl` block that the scan does not see (AD-383).
    pub members: BTreeSet<String>,
    pub unknowns: Vec<String>,
    /// The body holds `mod`, `use` or `extern`: an expansion may declare a module name.
    pub declares: bool,
    /// A definition in a function body is visible only in the rest of that body.
    pub local: Option<Local>,
}

/// The text where a `macro_rules!` of a block is visible: from its definition to the end of the
/// block. A position is a line and a column.
#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct Local {
    pub from: (i64, i64),
    pub until: (i64, i64),
}

impl Local {
    /// Whether the call at `site` is in the text of the block after the definition.
    pub(crate) fn sees(&self, site: &Site) -> bool {
        let at = (site.line, site.column);
        self.from < at && at <= self.until
    }
}

/// A call of a macro. A call is placed when the scan reads it in code, and the macro is named by
/// a plain or a `crate::`, `self::` or `super::` path. A call in the tokens of another macro, or
/// by the path of a module, is not placed: the scan does not know which macro it names.
#[derive(Clone, Debug, PartialEq)]
pub(crate) struct MacroCall {
    pub name: String,
    pub site: Site,
    pub placed: bool,
    /// The call is at module level: it may define a name of the module, which a glob `use` of
    /// the module then brings in. `modules/filled.rs` decides which such calls are safe.
    pub fills: bool,
    /// The tokens of the call hold `mod`, `use`, `extern` or a macro call by a path: they may
    /// declare a module name.
    pub declares: bool,
    /// The path that names the macro, or nothing when it starts with `::`.
    pub path: Vec<String>,
}

/// Macros of the standard library and of `serde_json`. Their bodies are expressions, so a path
/// inside is a path of this file. A macro of another name that holds a path is UNKNOWN.
pub(crate) const KNOWN_MACROS: [&str; 33] = [
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

/// Whether the tokens hold a macro call by a path (`a::m!`) at any depth. Its name alone does not
/// say which macro it is.
fn path_call(tokens: proc_macro2::TokenStream) -> bool {
    let trees: Vec<_> = tokens.into_iter().collect();
    trees.iter().enumerate().any(|(at, tree)| match tree {
        proc_macro2::TokenTree::Group(group) => path_call(group.stream()),
        proc_macro2::TokenTree::Ident(_) => {
            let colon = |i: usize| {
                matches!(trees.get(i), Some(proc_macro2::TokenTree::Punct(p)) if p.as_char() == ':')
            };
            let bang = matches!(trees.get(at + 1), Some(proc_macro2::TokenTree::Punct(p)) if p.as_char() == '!');
            bang && at > 0 && colon(at - 1)
        }
        _ => false,
    })
}

/// Whether the tokens hold `mod`, `use` or `extern` at any depth.
fn declares(tokens: proc_macro2::TokenStream) -> bool {
    tokens.into_iter().any(|tree| match tree {
        proc_macro2::TokenTree::Ident(id) => {
            matches!(id.to_string().as_str(), "mod" | "use" | "extern")
        }
        proc_macro2::TokenTree::Group(group) => declares(group.stream()),
        _ => false,
    })
}

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
        let (mut calls, mut methods) = (BTreeSet::new(), BTreeSet::new());
        macro_names(node.mac.tokens.clone(), 0, &mut calls);
        method_names(node.mac.tokens.clone(), 0, &mut methods);
        let mut members = BTreeSet::new();
        fn_names(node.mac.tokens.clone(), 0, &mut members);
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
            methods,
            members,
            unknowns,
            declares: declares(node.mac.tokens.clone()),
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
        let module_level = self.blocks == 0 && matches!(self.holder, Holder::Module);
        let call = MacroCall {
            name: name.clone(),
            site,
            placed: local,
            fills: module_level,
            declares: declares(node.tokens.clone()) || path_call(node.tokens.clone()),
            path: (node.path.segments.iter())
                .filter(|_| node.path.leading_colon.is_none())
                .map(|segment| plain(&segment.ident))
                .collect(),
        };
        // The tokens of a macro are not code that the scan reads: a call in them is not placed.
        let mut inner = BTreeSet::new();
        macro_names(node.tokens.clone(), 0, &mut inner);
        // A call by a path in the tokens makes `declares` of the outer call true, so each name
        // here is a plain call.
        let hidden = inner.into_iter().map(|name| MacroCall {
            path: vec![name.clone()],
            name,
            placed: false,
            ..call.clone()
        });
        let before = self.out.macro_calls.len();
        self.out.macro_calls.extend(hidden);
        let mut methods = BTreeSet::new();
        method_names(node.tokens.clone(), 0, &mut methods);
        self.out.tally.hidden_methods += methods.len();
        let (site, scope) = (call.site.clone(), self.inline.clone());
        self.out
            .method_calls
            .extend(methods.into_iter().map(|name| MethodCall {
                name,
                site: site.clone(),
                scope: scope.clone(),
                path: false,
                arity: None,
                on_self: None,
            }));
        self.out.tally.hidden += self.out.macro_calls.len() - before;
        if !plant::lose("call") {
            self.out.macro_calls.push(call);
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
