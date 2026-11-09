// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Paths inside a token stream: the body of a macro call or of an attribute.
//!
//! A macro body is not Rust syntax, so `syn` cannot parse it. The scan reads `a::b::c` chains of
//! identifiers and, in an attribute, a string that is only such a path.

use proc_macro2::{Span, TokenStream, TokenTree};

/// A written path: its identifiers and the span of the first one.
#[derive(Clone, Debug)]
pub struct Chain {
    pub names: Vec<String>,
    pub span: Span,
    /// The path starts with `::`, so its first name is a crate and never a local item.
    pub absolute: bool,
}

/// The nesting of groups that the scan follows. A deeper stream is cut off: its inner paths are
/// not read, so the caller reports the cut as a concern.
const MAX_DEPTH: usize = 64;

/// Each `a::b` chain (two names or more) in `stream`, in source order.
/// The result is `None` when the stream nests deeper than `MAX_DEPTH`.
pub fn chains(stream: TokenStream) -> Option<Vec<Chain>> {
    let mut found = Vec::new();
    collect(stream, 0, false, &mut found).then_some(found)
}

/// The chains of an attribute. A lint list (`allow(...)`, `expect(...)`) holds lint names, not
/// paths of the file, so the chains skip its group.
pub fn attribute_chains(stream: TokenStream) -> Option<Vec<Chain>> {
    let mut found = Vec::new();
    collect(stream, 0, true, &mut found).then_some(found)
}

/// The lint attributes: their groups hold names of lints and reasons.
pub const LINTS: [&str; 5] = ["allow", "warn", "deny", "forbid", "expect"];

fn collect(stream: TokenStream, depth: usize, attribute: bool, found: &mut Vec<Chain>) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    let mut tokens = stream.into_iter().peekable();
    let mut colons = 0_u8;
    while let Some(token) = tokens.next() {
        let before = colons;
        colons = 0;
        match token {
            TokenTree::Group(group) => {
                if !collect(group.stream(), depth + 1, attribute, found) {
                    return false;
                }
            }
            TokenTree::Punct(punct) if punct.as_char() == ':' => colons = before.saturating_add(1),
            TokenTree::Ident(first) if attribute && skips_group(&first, tokens.peek()) => {
                tokens.next();
            }
            TokenTree::Ident(first) => {
                let mut names = vec![first.to_string()];
                while let Some(name) = separator_then_name(&mut tokens) {
                    names.push(name);
                }
                if names.len() > 1 {
                    found.push(Chain {
                        names,
                        span: first.span(),
                        absolute: before >= 2,
                    });
                }
            }
            _ => {}
        }
    }
    true
}

fn skips_group(name: &proc_macro2::Ident, next: Option<&TokenTree>) -> bool {
    LINTS.contains(&name.to_string().as_str()) && matches!(next, Some(TokenTree::Group(_)))
}

/// Take `::` and the identifier after it, or take nothing.
fn separator_then_name(
    tokens: &mut std::iter::Peekable<proc_macro2::token_stream::IntoIter>,
) -> Option<String> {
    let mut ahead = tokens.clone();
    let colons = [ahead.next()?, ahead.next()?];
    let both = colons
        .iter()
        .all(|token| matches!(token, TokenTree::Punct(punct) if punct.as_char() == ':'));
    if !both {
        return None;
    }
    let TokenTree::Ident(name) = ahead.next()? else {
        return None;
    };
    *tokens = ahead;
    Some(name.to_string())
}

/// The keys of an attribute whose string value holds a path, a type or a bound. This is the list of
/// `serde` (`with`, `bound`, `remote`, ...). A string under another key is a message, a name or a
/// regular expression, and the scan ignores it: `deprecated(note = "use a::b")` is no edge.
const PATH_KEYS: [&str; 13] = [
    "bound",
    "with",
    "serialize_with",
    "deserialize_with",
    "crate",
    "remote",
    "default",
    "skip_serializing_if",
    "from",
    "try_from",
    "into",
    "serialize",
    "deserialize",
];

/// The paths in the strings under a `PATH_KEYS` key of a token stream, with their spans.
///
/// A string can hold a whole path (`"crate::codec"`) or a bound (`"T: a::B"`), so the text is read
/// as tokens, like the body of a macro. A text with `::` that does not read as tokens, or that
/// nests too deep, makes the result `None`: the caller reports it, and never drops a path silently.
pub fn string_paths(stream: TokenStream, depth: usize, found: &mut Vec<Chain>) -> Option<()> {
    if depth > MAX_DEPTH {
        return None;
    }
    let mut key: Option<String> = None;
    let mut armed = false;
    for token in stream {
        match token {
            TokenTree::Group(group) => {
                (key, armed) = (None, false);
                string_paths(group.stream(), depth + 1, found)?;
            }
            TokenTree::Ident(name) => (key, armed) = (Some(name.to_string()), false),
            TokenTree::Punct(punct) if punct.as_char() == '=' => armed = key.is_some(),
            TokenTree::Literal(literal) => {
                let holds_path =
                    armed && key.as_deref().is_some_and(|name| PATH_KEYS.contains(&name));
                (key, armed) = (None, false);
                if holds_path {
                    read_string(&literal, found)?;
                }
            }
            _ => (key, armed) = (None, false),
        }
    }
    Some(())
}

/// The paths in one string literal; `None` when the text has `::` and does not read.
fn read_string(literal: &proc_macro2::Literal, found: &mut Vec<Chain>) -> Option<()> {
    let Ok(text) = syn::parse_str::<syn::LitStr>(&literal.to_string()) else {
        return Some(());
    };
    let value = text.value();
    if value.contains("::") {
        for mut chain in chains(value.parse::<TokenStream>().ok()?)? {
            chain.span = literal.span();
            found.push(chain);
        }
    }
    Some(())
}

/// Split a stream at its top-level commas: `cfg_attr(a, b, c)` gives three parts.
pub fn split_commas(stream: TokenStream) -> Vec<Vec<TokenTree>> {
    let mut parts = vec![Vec::new()];
    for token in stream {
        if matches!(&token, TokenTree::Punct(punct) if punct.as_char() == ',') {
            parts.push(Vec::new());
        } else if let Some(last) = parts.last_mut() {
            last.push(token);
        }
    }
    parts.retain(|part| !part.is_empty());
    parts
}

/// The identifier that starts a token list, as text.
pub fn first_name(tokens: &[TokenTree]) -> Option<String> {
    match tokens.first()? {
        TokenTree::Ident(name) => Some(name.to_string()),
        _ => None,
    }
}

#[cfg(test)]
#[path = "tokens_tests.rs"]
mod tests;
