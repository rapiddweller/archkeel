// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the scan reads in a `macro_rules!` definition and in a macro call. The walker of
//! `scan.rs` owns the facts; this file only fills them.

use std::collections::BTreeSet;

use proc_macro2::Span;
use syn::{ItemMacro, Macro};

use super::attributes::concern;
use super::state::{Local, MacroCall, MacroDef, Walker};
use crate::definitions::{Holder, MethodCall};
use crate::macro_items::item_level;
use crate::net;
use crate::plant;
use crate::tokens::{
    chains, fn_names, macro_names, method_names, names_relative, only_dollar_crate, plain,
    string_paths, writes_use, Chain, EXPRESSION_MACROS, NO_BIND_MACROS,
};

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

/// A `macro_rules!` definition. Its expansion stays in this crate, so its body is read as code
/// of the file: a path is an edge, and a crate name in any token is checked by the net. An
/// exported macro expands in other crates too, and those edges are not in this file: UNKNOWN.
pub(super) fn macro_rules(walker: &mut Walker<'_>, node: &ItemMacro) {
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
    // The reasons below belong to each call in this crate; an exported macro may get one more.
    let first_unknown = walker.out.concerns.len();
    net::walk(node.mac.tokens.clone(), &mut walker.out.mentioned);
    if names_relative(node.mac.tokens.clone()) {
        let reason = format!(
            "The macro_rules! definition {name} names crate, super or self: the scan does not know where it expands"
        );
        concern(walker, reason, span);
    }
    walker.in_macro = Some(name.clone());
    let (mut calls, mut methods) = (BTreeSet::new(), BTreeSet::new());
    macro_names(node.mac.tokens.clone(), 0, &mut calls);
    method_names(node.mac.tokens.clone(), 0, &mut methods);
    let mut members = BTreeSet::new();
    fn_names(node.mac.tokens.clone(), 0, &mut members);
    let mut found = Vec::new();
    let strings = string_paths(node.mac.tokens.clone(), 0, &mut found);
    let mut portable = exported
        && !names_relative(node.mac.tokens.clone())
        && only_dollar_crate(node.mac.tokens.clone(), 0)
        && calls.iter().all(|call| {
            *call == name
                || NO_BIND_MACROS.contains(&call.as_str())
                || EXPRESSION_MACROS.contains(&call.as_str())
        });
    match chains(node.mac.tokens.clone()).filter(|_| strings.is_some()) {
        Some(more) => {
            found.extend(more);
            let from_crate = |chain: &Chain| chain.names.first().is_some_and(|n| n == "crate");
            portable &= found.iter().all(from_crate);
            walker.refer_chains(found);
        }
        None => concern(
            walker,
            format!("The macro_rules! definition {name} is nested too deep to read"),
            span,
        ),
    }
    walker.in_macro = None;
    let unknowns: Vec<String> = (walker.out.concerns.iter().skip(first_unknown))
        .map(|concern| concern.reason.clone())
        .collect();
    // AD-614: an exported macro expands in other crates. Only a portable body names the same
    // edges there: its calls in other crates take them. Any other one is UNKNOWN here.
    portable &= unknowns.is_empty();
    if exported && !portable {
        let reason =
            format!("The macro_rules! definition {name} is exported: it expands in other crates");
        concern(walker, reason, span);
    }
    // A macro of a function body is scoped to the rest of that body. An exported one is also
    // a path at the crate root, so it stays crate-wide.
    let from = walker.site(span);
    let local = walker
        .block_ends
        .last()
        .filter(|_| !exported)
        .map(|until| Local {
            from: (from.line, from.column),
            until: *until,
        });
    walker.out.macro_defs.push(MacroDef {
        name,
        id: walker.out.macro_defs.len(),
        calls,
        methods,
        members,
        unknowns,
        local,
        item_level: item_level(node.mac.tokens.clone()),
        portable,
    });
}

pub(super) fn macro_call(walker: &mut Walker<'_>, node: &Macro) {
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
    let site = walker.site(span);
    let module_level = walker.blocks == 0 && matches!(walker.holder, Holder::Module);
    let call = MacroCall {
        name: name.clone(),
        site,
        placed: local,
        fills: module_level,
        writes_use: writes_use(node.tokens.clone(), 0),
        path: node.path.segments.iter().map(|s| plain(&s.ident)).collect(),
    };
    // The tokens of a macro are not code that the scan reads: a call in them is not placed.
    let mut inner = BTreeSet::new();
    macro_names(node.tokens.clone(), 0, &mut inner);
    // AD-614: a silent or expression macro of `std`, by its plain name, with only such macros in
    // its tokens, reads no string as a path. A macro of the file of that name is not `std`.
    let std_only = |name: &str| NO_BIND_MACROS.contains(&name) || EXPRESSION_MACROS.contains(&name);
    let local = |name: &str| walker.out.macro_defs.iter().any(|def| def.name == name);
    let plain_strings = node.path.segments.len() == 1
        && std_only(&name)
        && !local(&name)
        && inner.iter().all(|inner| std_only(inner) && !local(inner));
    let hidden = inner.into_iter().map(|name| MacroCall {
        name,
        placed: false,
        ..call.clone()
    });
    let before = walker.out.macro_calls.len();
    walker.out.macro_calls.extend(hidden);
    let mut methods = BTreeSet::new();
    method_names(node.tokens.clone(), 0, &mut methods);
    walker.out.tally.hidden_methods += methods.len();
    let (site, scope) = (call.site.clone(), walker.inline.clone());
    walker
        .out
        .method_calls
        .extend(methods.into_iter().map(|name| MethodCall {
            name,
            site: site.clone(),
            scope: scope.clone(),
            path: false,
            arity: None,
            on_self: None,
        }));
    walker.out.tally.hidden += walker.out.macro_calls.len() - before;
    if !plant::lose("call") {
        walker.out.macro_calls.push(call);
    }
    if name == "include" {
        concern(
            walker,
            "The macro include! adds code that the scan does not read".to_owned(),
            span,
        );
        return;
    }
    if plain_strings {
        net::walk_code(node.tokens.clone(), &mut walker.out.mentioned);
    } else {
        net::walk(node.tokens.clone(), &mut walker.out.mentioned);
    }
    let Some(found) = chains(node.tokens.clone()) else {
        concern(
            walker,
            format!("The macro {name}! is nested too deep to read"),
            span,
        );
        return;
    };
    if KNOWN_MACROS.contains(&name.as_str()) {
        walker.refer_chains(found);
    } else if !found.is_empty() {
        let reason = format!("The macro {name}! holds a path that the scan cannot read");
        concern(walker, reason, span);
    }
}
