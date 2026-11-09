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
}

/// The nesting of groups that the scan follows. A deeper stream is cut off: its inner paths are
/// not read, so the caller reports the cut as a concern.
const MAX_DEPTH: usize = 64;

/// Each `a::b` chain (two names or more) in `stream`, in source order.
/// The result is `None` when the stream nests deeper than `MAX_DEPTH`.
pub fn chains(stream: TokenStream) -> Option<Vec<Chain>> {
    let mut found = Vec::new();
    collect(stream, 0, &mut found).then_some(found)
}

fn collect(stream: TokenStream, depth: usize, found: &mut Vec<Chain>) -> bool {
    if depth > MAX_DEPTH {
        return false;
    }
    let mut tokens = stream.into_iter().peekable();
    while let Some(token) = tokens.next() {
        match token {
            TokenTree::Group(group) => {
                if !collect(group.stream(), depth + 1, found) {
                    return false;
                }
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
                    });
                }
            }
            _ => {}
        }
    }
    true
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

/// The paths in the string literals of a token stream, with their spans.
///
/// A string in an attribute can hold a whole path (`"crate::codec"`) or a bound (`"T: a::B"`), so
/// the text is read as tokens, like the body of a macro. A text with `::` that does not read as
/// tokens, or that nests too deep, makes the result `None`: the caller reports it, and never
/// drops a path silently.
pub fn string_paths(stream: TokenStream, depth: usize, found: &mut Vec<Chain>) -> Option<()> {
    if depth > MAX_DEPTH {
        return None;
    }
    for token in stream {
        match token {
            TokenTree::Group(group) => string_paths(group.stream(), depth + 1, found)?,
            TokenTree::Literal(literal) => {
                let Ok(text) = syn::parse_str::<syn::LitStr>(&literal.to_string()) else {
                    continue;
                };
                let value = text.value();
                if !value.contains("::") {
                    continue;
                }
                for mut chain in chains(value.parse::<TokenStream>().ok()?)? {
                    chain.span = literal.span();
                    found.push(chain);
                }
            }
            _ => {}
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
