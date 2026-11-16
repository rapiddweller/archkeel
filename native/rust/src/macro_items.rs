// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the expansion of a `macro_rules!` body writes at the item level of the module of its call
//! (AD-608, #1346): `item_level` reads one definition.

use std::collections::BTreeSet;

use proc_macro2::{TokenStream, TokenTree};

use crate::tokens::{called, is_punct, plain, writes_use, MAX_DEPTH};

/// What the expansion of a `macro_rules!` body writes at the item level of the module of its call
/// (AD-608): the tokens of each transcriber (the group after `=>`), with each `$( .. )` repetition
/// at the same level. A `use` or a macro call inside a block, an `impl` or an inline `mod` of the
/// expansion binds no name of that module.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct ItemLevel {
    /// A `use`, `extern` or `mod` at item level, or anywhere in a `macro_rules!` at item level.
    pub writes_use: bool,
    /// The macros that the expansion calls at item level, by their last name.
    pub calls: BTreeSet<String>,
    /// A call at item level by a path (`dep::m!`, `$crate::m!`): its macro is not the one of
    /// that last name in the crate (#1346).
    pub path_calls: bool,
    /// A `macro_rules!` at item level: the expansion defines a macro that no scan of a
    /// definition sees (#1346).
    pub defines_macros: bool,
    /// The types that the expansion defines at item level (`struct`, `enum`, `union`), by their
    /// name or their metavariable (`$name`).
    pub defines: BTreeSet<String>,
    /// Each `impl` at item level: its trait (`None` for an inherent impl) and its self type. A
    /// name is one identifier or a metavariable (`$name`); any other form (a path, a reference, a
    /// tuple) is the empty string, which no proof anchors.
    pub impls: BTreeSet<(Option<String>, String)>,
}

impl ItemLevel {
    /// True when the expansion of the macro `own` can add a member to an `impl` block that is
    /// not anchored in the module of the call (#1196, AD-357, AD-516): an impl is anchored when
    /// the expansion defines its self type, or when the module of the call declares its trait or
    /// its self type by that one name (`declared`). A call of another macro, a path call and a
    /// macro definition hold an expansion that this reading does not see. A call of `own` expands
    /// to arms that this reading holds already.
    pub(crate) fn foreign_impl(&self, own: &str, declared: impl Fn(&str) -> bool) -> bool {
        let anchored = |(tr, ty): &(Option<String>, String)| {
            let written = |name: &str| !name.is_empty() && !name.starts_with('$') && declared(name);
            self.defines.contains(ty) || written(ty) || tr.as_deref().is_some_and(written)
        };
        self.path_calls
            || self.defines_macros
            || self.calls.iter().any(|call| call != own)
            || self.impls.iter().any(|head| !anchored(head))
    }
}

/// The name of a type at `at`: an identifier, or `$` and a metavariable.
fn type_name(tokens: &[TokenTree], at: usize) -> Option<String> {
    match (tokens.get(at), tokens.get(at + 1)) {
        (Some(TokenTree::Punct(dollar)), Some(TokenTree::Ident(name)))
            if dollar.as_char() == '$' =>
        {
            Some(format!("${}", plain(name)))
        }
        (Some(TokenTree::Ident(name)), _) => Some(plain(name)),
        _ => None,
    }
}

/// The trait and the self type of the `impl` at `at`, up to its body. Generic parameters and
/// arguments are skipped.
fn impl_head(tokens: &[TokenTree], at: usize) -> (Option<String>, String) {
    let body = (at + 1..tokens.len()).find(|&i| {
        matches!(&tokens[i], TokenTree::Group(g) if g.delimiter() == proc_macro2::Delimiter::Brace)
    });
    let mut depth = 0usize;
    let mut level: Vec<&TokenTree> = Vec::new();
    for token in &tokens[at + 1..body.unwrap_or(tokens.len())] {
        match token {
            TokenTree::Punct(p) if p.as_char() == '<' => depth += 1,
            TokenTree::Punct(p) if p.as_char() == '>' => depth = depth.saturating_sub(1),
            _ if depth > 0 => {}
            _ => level.push(token),
        }
    }
    let split = level
        .iter()
        .position(|t| matches!(t, TokenTree::Ident(word) if word == "for"));
    match split {
        Some(at) => (Some(one_name(&level[..at])), one_name(&level[at + 1..])),
        None => (None, one_name(&level)),
    }
}

/// One identifier, or `$` and a metavariable; else the empty string.
fn one_name(tokens: &[&TokenTree]) -> String {
    match tokens {
        [TokenTree::Ident(name)] => plain(name),
        [TokenTree::Punct(dollar), TokenTree::Ident(name)] if dollar.as_char() == '$' => {
            format!("${}", plain(name))
        }
        _ => String::new(),
    }
}

pub(crate) fn item_level(rules: TokenStream) -> ItemLevel {
    let mut found = ItemLevel::default();
    let tokens: Vec<TokenTree> = rules.into_iter().collect();
    for (at, token) in tokens.iter().enumerate() {
        let arrow = at >= 2 && is_punct(&tokens[at - 2], '=') && is_punct(&tokens[at - 1], '>');
        if let (TokenTree::Group(group), true) = (token, arrow) {
            items(group.stream(), 0, &mut found);
        }
    }
    found
}

fn items(stream: TokenStream, depth: usize, found: &mut ItemLevel) {
    if depth > MAX_DEPTH {
        found.writes_use = true;
        return;
    }
    let tokens: Vec<TokenTree> = stream.into_iter().collect();
    for (at, token) in tokens.iter().enumerate() {
        let next = |step: usize| tokens.get(at + step);
        match token {
            TokenTree::Group(group) if at > 0 && is_punct(&tokens[at - 1], '$') => {
                items(group.stream(), depth + 1, found);
            }
            TokenTree::Ident(word) if word == "use" || word == "extern" || word == "mod" => {
                found.writes_use = true
            }
            TokenTree::Ident(word) if word == "struct" || word == "enum" || word == "union" => {
                found.defines.extend(type_name(&tokens, at + 1));
            }
            TokenTree::Ident(word) if word == "impl" => {
                found.impls.insert(impl_head(&tokens, at));
            }
            // `macro_rules! name { ... }`: the name stands between the `!` and the body (#1346).
            TokenTree::Ident(word)
                if word == "macro_rules" && next(1).is_some_and(|bang| is_punct(bang, '!')) =>
            {
                found.defines_macros = true;
                let body = tokens[at + 1..].iter().find_map(|token| match token {
                    TokenTree::Group(group) => Some(group),
                    _ => None,
                });
                found.writes_use |= body.is_none_or(|body| writes_use(body.stream(), depth));
            }
            TokenTree::Ident(word) if called(next(1), next(2)) => {
                found.path_calls |= at > 0 && is_punct(&tokens[at - 1], ':');
                found.calls.insert(plain(word));
            }
            _ => {}
        }
    }
}
