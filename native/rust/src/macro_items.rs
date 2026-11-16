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
