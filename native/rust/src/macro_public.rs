// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The public items that a module-level call of a `macro_rules!` of the workspace writes (#1450,
//! AD-718). A call expands one arm: an arm whose matcher disagrees with the leading literal tokens
//! of the input cannot match. A transcriber states an item by `pub` and its keyword, or by a `vis`
//! metavariable, which is public only when the call holds a bare `pub`. A metavariable at the start
//! of an item may be the item itself, written from the call tokens: then the call tokens show it.

use std::collections::BTreeSet;

use proc_macro2::{Delimiter, TokenStream, TokenTree};

use crate::tokens::{is_punct, plain, MAX_DEPTH};

/// The public items: kind, name or metavariable, and whether a `vis` metavariable gives the
/// visibility. The kind `item` is an item of no known kind.
pub(crate) type Items = BTreeSet<(String, String, bool)>;

/// One arm of a `macro_rules!`: what its transcriber publishes at item level.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct Arm {
    /// The leading literal tokens of the matcher, up to its first metavariable or group.
    pub head: Vec<String>,
    pub public: Items,
    pub item_calls: Vec<(String, Vec<String>)>,
    pub opaque: bool,
}

/// The name of a type at `at`: an identifier, or `$` and a metavariable.
pub(crate) fn type_name(tokens: &[TokenTree], at: usize) -> Option<String> {
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

/// What the tokens of a call tell of the public items that its expansion may write.
#[derive(Clone, Debug, Default, PartialEq)]
pub(crate) struct CallTokens {
    /// The leading literal tokens: an arm whose matcher disagrees cannot match.
    pub head: Vec<String>,
    /// A bare `pub`, which a `vis` metavariable may take.
    pub bare_pub: bool,
    /// The items that the tokens declare with a bare `pub`.
    pub items: Items,
}

impl CallTokens {
    pub(crate) fn of(tokens: TokenStream) -> Self {
        let mut items = Items::new();
        call_items(tokens.clone(), &mut items);
        CallTokens {
            head: head(tokens.clone()),
            bare_pub: bare_pub(tokens, 0),
            items,
        }
    }
}

const KEYWORDS: [&str; 9] = [
    "fn", "const", "static", "struct", "enum", "union", "trait", "type", "mod",
];

/// The leading literal tokens of a stream: identifiers, punctuation and literals up to the first
/// group or `$`. A matcher arm can match an input only when the two agree on their common part.
pub(crate) fn head(stream: TokenStream) -> Vec<String> {
    let mut found = Vec::new();
    for token in stream {
        match token {
            TokenTree::Punct(p) if p.as_char() == '$' => break,
            TokenTree::Group(_) => break,
            TokenTree::Punct(p) => found.push(p.as_char().to_string()),
            TokenTree::Ident(word) => found.push(plain(&word)),
            TokenTree::Literal(text) => found.push(text.to_string()),
        }
    }
    found
}

/// The item that the visibility at `at` (`pub`, or the name of a `$vis` metavariable) declares:
/// its kind and its name. `pub(crate)` and the like declare nothing public. A metavariable that
/// stands before no item keyword is no visibility.
pub(crate) fn public_item(tokens: &[TokenTree], at: usize) -> Option<(String, String, bool)> {
    let from_call = !matches!(&tokens[at], TokenTree::Ident(word) if word == "pub");
    let mut next = at + 1;
    let word = |i: usize| match tokens.get(i) {
        Some(TokenTree::Ident(word)) => Some(plain(word)),
        _ => None,
    };
    if matches!(tokens.get(next), Some(TokenTree::Group(g)) if g.delimiter() == Delimiter::Parenthesis)
    {
        return None;
    }
    // Qualifiers of a function: `const`, `async`, `unsafe`, `extern "abi"`.
    loop {
        match word(next).as_deref() {
            Some("async" | "unsafe") => next += 1,
            Some("const")
                if matches!(
                    word(next + 1).as_deref(),
                    Some("fn" | "unsafe" | "async" | "extern")
                ) =>
            {
                next += 1
            }
            Some("extern") => {
                next += 1;
                if matches!(tokens.get(next), Some(TokenTree::Literal(_))) {
                    next += 1;
                }
            }
            _ => break,
        }
    }
    if !from_call && tokens.get(next).is_some_and(|t| is_punct(t, '$')) {
        return Some(("item".to_owned(), String::new(), false));
    }
    let kind = word(next)?;
    let kind = match kind.as_str() {
        word if KEYWORDS.contains(&word) => kind,
        "macro_rules" => "macro".to_owned(),
        _ => return None,
    };
    let mut name_at = next + 1;
    if kind == "static" && word(name_at).as_deref() == Some("mut") {
        name_at += 1;
    }
    let name = type_name(tokens, name_at).unwrap_or_default();
    Some((kind, name, from_call))
}

/// True when the stream holds a bare `pub` (no `( .. )` after it): only such a token can make a
/// `vis` metavariable public (#1450).
pub(crate) fn bare_pub(stream: TokenStream, depth: usize) -> bool {
    let tokens: Vec<TokenTree> = stream.into_iter().collect();
    depth > MAX_DEPTH
        || tokens.iter().enumerate().any(|(at, token)| match token {
            TokenTree::Group(group) => bare_pub(group.stream(), depth + 1),
            TokenTree::Ident(word) if word == "pub" => !matches!(
                tokens.get(at + 1),
                Some(TokenTree::Group(g)) if g.delimiter() == Delimiter::Parenthesis
            ),
            _ => false,
        })
}

/// True when the token at `at` ends an item or an attribute, so the next token starts an item.
pub(crate) fn item_start(tokens: &[TokenTree], at: usize) -> bool {
    let Some(before) = at.checked_sub(1).map(|i| &tokens[i]) else {
        return true;
    };
    match before {
        TokenTree::Punct(p) => matches!(p.as_char(), ';' | '*' | '+' | '?'),
        TokenTree::Group(g) => matches!(g.delimiter(), Delimiter::Brace | Delimiter::Bracket),
        _ => false,
    }
}

/// Visit each token of the stream and of each group down to `MAX_DEPTH`, with the tokens of its
/// level; `deep` runs for a group below that depth.
pub(crate) fn each_token(
    stream: TokenStream,
    depth: usize,
    deep: &mut dyn FnMut(),
    visit: &mut dyn FnMut(&[TokenTree], usize),
) {
    if depth > MAX_DEPTH {
        return deep();
    }
    let tokens: Vec<TokenTree> = stream.into_iter().collect();
    for (at, token) in tokens.iter().enumerate() {
        match token {
            TokenTree::Group(group) => each_token(group.stream(), depth + 1, deep, visit),
            _ => visit(&tokens, at),
        }
    }
}

/// The items that the call tokens declare with a bare `pub`: `pub [qualifiers] keyword name`. A
/// field (`pub name:`) is a member. Any other bare `pub` declares an item of no known kind.
pub(crate) fn call_items(stream: TokenStream, found: &mut Items) {
    let unknown = || ("item".to_owned(), String::new(), false);
    let mut deep = Vec::new();
    each_token(
        stream,
        0,
        &mut || deep.push(unknown()),
        &mut |tokens, at| {
            if !matches!(&tokens[at], TokenTree::Ident(word) if word == "pub") {
                return;
            }
            let next = tokens.get(at + 1);
            let restricted = matches!(next, Some(TokenTree::Group(g)) if g.delimiter() == Delimiter::Parenthesis);
            let field = matches!(next, Some(TokenTree::Ident(_)))
                && tokens.get(at + 2).is_some_and(|t| is_punct(t, ':'));
            if !restricted && !field {
                found.insert(public_item(tokens, at).unwrap_or_else(unknown));
            }
        },
    );
    found.extend(deep);
}
