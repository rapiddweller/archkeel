// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! What the expansion of a `macro_rules!` body writes at the item level of the module of its call
//! (AD-608, #1346): `item_level` reads one definition.

use std::collections::BTreeSet;

use proc_macro2::{TokenStream, TokenTree};

use crate::macro_public::{head, item_start, public_item, type_name, Arm, Items};
use crate::tokens::{called, holds_word, is_punct, plain, writes_use, MAX_DEPTH};

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
    /// The types that one transcriber defines at item level (`struct`, `enum`, `union`), by their
    /// name or their metavariable (`$name`). A call expands one arm, so a type anchors only an
    /// impl of its own arm (#1374); `item_level` keeps this set empty.
    pub defines: BTreeSet<String>,
    /// Each `impl` at item level that no type of its own arm anchors: its trait (`None` for an
    /// inherent impl) and its self type. A name is one identifier or a metavariable (`$name`);
    /// any other form (a path, a reference, a tuple) is the empty string, which no proof anchors.
    pub impls: BTreeSet<(Option<String>, String)>,
    /// Each item at item level that the expansion may declare public (`pub`, or a `$vis`
    /// metavariable): its kind (`fn`, `const`, `static`, `type`, a type keyword, `macro`, or
    /// `mod`, whose items are not read), its name or metavariable, and whether a `$vis`
    /// metavariable gives the visibility (#1450).
    pub public: BTreeSet<(String, String, bool)>,
    /// Each item-level call: the macro name and the leading literal tokens of its input.
    pub item_calls: Vec<(String, Vec<String>)>,
    /// The arms, each with the leading literal tokens of its matcher (#1450).
    pub arms: Vec<Arm>,
    /// A metavariable starts an item at item level: the expansion may write items of the call
    /// tokens (`$($t)*`, `$pub $struct $name`), which only the call shows (#1450).
    pub opaque: bool,
}

/// True when an input with the literal head `input` may match an arm with the head `arm`.
fn may_match(arm: &[String], input: &[String]) -> bool {
    arm.iter().zip(input).all(|(a, b)| a == b)
}

/// The items that a call of the macro `own` with the input head `input` may publish at item
/// level: the arms that the head may match, and each arm that an item-level call of `own` in
/// one of them may match (#1450).
pub(crate) fn published(level: &ItemLevel, own: &str, input: &[String]) -> (Items, bool) {
    let mut reached = vec![false; level.arms.len()];
    let mut heads = vec![input.to_vec()];
    while let Some(input) = heads.pop() {
        for (at, arm) in level.arms.iter().enumerate() {
            if reached[at] || !may_match(&arm.head, &input) {
                continue;
            }
            reached[at] = true;
            let own_calls = arm.item_calls.iter().filter(|(name, _)| name == own);
            heads.extend(own_calls.map(|(_, head)| head.clone()));
        }
    }
    let arms: Vec<&Arm> = (level.arms.iter().zip(reached))
        .filter_map(|(arm, hit)| hit.then_some(arm))
        .collect();
    let opaque = arms.iter().any(|arm| arm.opaque);
    (
        arms.iter()
            .flat_map(|arm| arm.public.iter().cloned())
            .collect(),
        opaque,
    )
}

impl ItemLevel {
    /// True when the expansion of the macro `own` can add a member to an `impl` block that is
    /// not anchored in the module of the call (#1196, AD-357, AD-516): an impl is anchored when
    /// its own arm defines its self type, or when the module of the call declares its trait or
    /// its self type by that one name (`declared`). A call of another macro, a path call and a
    /// macro definition hold an expansion that this reading does not see. A call of `own` expands
    /// to arms that this reading holds already.
    pub(crate) fn foreign_impl(&self, own: &str, declared: impl Fn(&str) -> bool) -> bool {
        self.calls.iter().any(|call| call != own)
            || self.path_calls
            || self.defines_macros
            || self.impls.iter().any(|head| !anchored(head, &declared))
    }

    /// True when the expansion may write a trait impl that is not anchored in the module of the
    /// call, which code may run without a name of the module (#1371, AD-516): such a trait impl,
    /// or a path call or a macro definition, whose expansion this reading does not see. A member
    /// of an inherent impl is reached only by its name, which `foreign_impl` covers. A call of a
    /// plain name is read on its own.
    pub(crate) fn trait_home(&self, declared: impl Fn(&str) -> bool) -> bool {
        let trait_impl = |head: &&(Option<String>, String)| head.0.is_some();
        self.path_calls
            || self.defines_macros
            || (self.impls.iter().filter(trait_impl)).any(|head| !anchored(head, &declared))
    }
}

/// An impl is anchored when the module of the call declares its trait or its self type by that
/// one name in every configuration (`declared`).
fn anchored((tr, ty): &(Option<String>, String), declared: &impl Fn(&str) -> bool) -> bool {
    let written = |name: &str| !name.is_empty() && !name.starts_with('$') && declared(name);
    written(ty) || tr.as_deref().is_some_and(written)
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
            let mut arm = ItemLevel::default();
            items(group.stream(), 0, &mut arm);
            found.writes_use |= arm.writes_use;
            found.path_calls |= arm.path_calls;
            found.defines_macros |= arm.defines_macros;
            found.calls.extend(arm.calls);
            found.public.extend(arm.public.iter().cloned());
            found.opaque |= arm.opaque;
            let matcher = match at.checked_sub(3).map(|i| &tokens[i]) {
                Some(TokenTree::Group(group)) => head(group.stream()),
                _ => Vec::new(),
            };
            found.arms.push(Arm {
                head: matcher,
                public: arm.public,
                item_calls: arm.item_calls.clone(),
                opaque: arm.opaque,
            });
            found.item_calls.extend(arm.item_calls);
            let defines = arm.defines;
            let own = arm
                .impls
                .into_iter()
                .filter(|(_, ty)| !defines.contains(ty));
            found.impls.extend(own);
        }
    }
    found
}

/// A `pub` or a metavariable at `at`: the public item that it declares, or, for a metavariable at
/// the start of an item that is no visibility, an item that the call tokens may write (#1450).
fn visibility(tokens: &[TokenTree], at: usize, found: &mut ItemLevel) {
    let item = public_item(tokens, at);
    let metavariable = !matches!(&tokens[at], TokenTree::Ident(word) if word == "pub");
    let start = metavariable && at >= 1 && item_start(tokens, at - 1);
    found.opaque |= item.is_none() && start;
    found.public.extend(item);
}

/// A `pub`, or a metavariable other than `$crate`, at `at`.
fn visible_at(tokens: &[TokenTree], at: usize) -> bool {
    match &tokens[at] {
        TokenTree::Ident(word) => {
            word == "pub" || (word != "crate" && at > 0 && is_punct(&tokens[at - 1], '$'))
        }
        _ => false,
    }
}

/// A module of the expansion holds items that are not read, `pub` or not (#1450).
fn module(tokens: &[TokenTree], at: usize, found: &mut ItemLevel) {
    let name = type_name(tokens, at + 1).unwrap_or_default();
    found.public.insert(("mod".to_owned(), name, false));
}

/// A `macro_rules!` of the expansion at `at`: a macro that no scan of a definition sees, public
/// with `#[macro_export]` (#1346, #1450).
fn macro_definition(tokens: &[TokenTree], at: usize, depth: usize, found: &mut ItemLevel) {
    found.defines_macros = true;
    // `#[macro_export]` before the definition publishes the macro at the crate root.
    let exported = at > 0
        && matches!(&tokens[at - 1], TokenTree::Group(g) if g.delimiter() == proc_macro2::Delimiter::Bracket
            && g.stream().into_iter().any(|t| matches!(t, TokenTree::Ident(w) if w == "macro_export")));
    if exported {
        let name = type_name(tokens, at + 2).unwrap_or_default();
        found.public.insert(("macro".to_owned(), name, false));
    }
    let body = tokens[at + 1..].iter().find_map(|token| match token {
        TokenTree::Group(group) => Some(group),
        _ => None,
    });
    found.writes_use |= body.is_none_or(|body| writes_use(body.stream(), depth));
}

/// A call at item level at `at`, by its last name.
fn item_call(tokens: &[TokenTree], at: usize, name: String, found: &mut ItemLevel) {
    found.path_calls |= at > 0 && is_punct(&tokens[at - 1], ':');
    if let Some(TokenTree::Group(input)) = tokens.get(at + 2) {
        found.item_calls.push((name.clone(), head(input.stream())));
    }
    found.calls.insert(name);
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
            TokenTree::Ident(_) if visible_at(&tokens, at) => visibility(&tokens, at, found),
            TokenTree::Ident(word) if word == "mod" => {
                found.writes_use = true;
                module(&tokens, at, found);
            }
            TokenTree::Ident(word) if word == "use" || word == "extern" => found.writes_use = true,
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
                macro_definition(&tokens, at, depth, found);
            }
            TokenTree::Ident(word) if called(next(1), next(2)) => {
                item_call(&tokens, at, plain(word), found);
            }
            _ => {}
        }
    }
}

/// The path of each macro that the stream calls, and whether it starts with `::` (#1371). A call
/// in the tokens of another macro is no code that the walk reads, so its path is read here.
pub(crate) fn macro_paths(stream: TokenStream, found: &mut BTreeSet<(bool, Vec<String>)>) {
    crate::macro_public::each_token(stream, 0, &mut || {}, &mut |tokens, at| {
        if matches!(&tokens[at], TokenTree::Ident(_))
            && called(tokens.get(at + 1), tokens.get(at + 2))
        {
            found.insert(path_before(tokens, at));
        }
    });
}

/// The path that ends with the name at `at`: the names before it, each with `::`, and whether a
/// `::` starts it.
fn path_before(tokens: &[TokenTree], at: usize) -> (bool, Vec<String>) {
    let colons =
        |end: usize| end >= 2 && is_punct(&tokens[end - 1], ':') && is_punct(&tokens[end - 2], ':');
    let mut path = Vec::new();
    let mut start = at;
    if let TokenTree::Ident(name) = &tokens[at] {
        path.push(plain(name));
    }
    while colons(start) {
        let Some(TokenTree::Ident(segment)) = start.checked_sub(3).map(|i| &tokens[i]) else {
            break;
        };
        path.insert(0, plain(segment));
        start -= 3;
    }
    (colons(start), path)
}

/// True when the stream holds an `impl`, or nests deeper than the scan reads (#1371).
pub(crate) fn holds_impl(stream: TokenStream) -> bool {
    holds_word(stream, 0, &["impl"])
}
