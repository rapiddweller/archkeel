// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The safety net: every name that the file writes in a place that syn does not read as code.
//!
//! In ordinary Rust, a bare name that is not followed by `::` is a local, a field or a value, and
//! cannot be a crate. A path that starts with a crate is read by the scan. So the net walks only
//! macro bodies, attribute streams and string literals.
//!
//! The scan reads the places where Rust takes a path: items, `use`, macro bodies of known macros
//! and attributes. A crate name can also appear in a place that nobody listed: a macro argument
//! (`other::call!(base_crate)`), an attribute argument (`#[other::attr(base_crate)]`), a string
//! under a key that no list names. So the collector does not trust its list. It walks all the
//! tokens once, and `collect.rs` says UNKNOWN for each reachable crate whose name appears and
//! that the file has no edge to. A name in a comment, in a doc comment or under a message key is
//! no use of a crate, and does not count.

use std::collections::BTreeSet;

use proc_macro2::{token_stream::IntoIter, TokenStream, TokenTree};

use crate::tokens::{plain, MESSAGE_KEYS};

/// One level of brackets that the walk is in, with the last name and whether `=` follows it.
struct Level {
    tokens: IntoIter,
    key: Option<String>,
    armed: bool,
}

impl Level {
    fn new(stream: TokenStream) -> Self {
        Self {
            tokens: stream.into_iter(),
            key: None,
            armed: false,
        }
    }
}

/// Add the names that a token stream writes: each identifier, and the first segment of each
/// string that is a name or starts with `name::`. The caller passes the places that syn does not
/// read as code: a macro body and an attribute stream.
pub fn walk(stream: TokenStream, found: &mut BTreeSet<String>) {
    let mut levels = vec![Level::new(stream)];
    // The walk keeps its own stack, so the depth of the brackets costs no stack frame.
    while let Some(level) = levels.last_mut() {
        let Some(token) = level.tokens.next() else {
            levels.pop();
            continue;
        };
        match token {
            TokenTree::Group(group) => {
                (level.key, level.armed) = (None, false);
                levels.push(Level::new(group.stream()));
            }
            TokenTree::Ident(name) => {
                let name = plain(&name);
                found.insert(name.clone());
                (level.key, level.armed) = (Some(name), false);
            }
            TokenTree::Punct(punct) if punct.as_char() == '=' => level.armed = level.key.is_some(),
            TokenTree::Literal(literal) => {
                let message = level.armed
                    && level
                        .key
                        .as_deref()
                        .is_some_and(|name| MESSAGE_KEYS.contains(&name));
                (level.key, level.armed) = (None, false);
                if !message {
                    note_literal(&literal.to_string(), found);
                }
            }
            _ => (level.key, level.armed) = (None, false),
        }
    }
}

/// A literal of a token stream: only a string counts.
fn note_literal(literal: &str, found: &mut BTreeSet<String>) {
    if let Ok(text) = syn::parse_str::<syn::LitStr>(literal) {
        note_string(&text.value(), found);
    }
}

/// The first segment of a string value that is a name or starts with `name::`.
pub fn note_string(value: &str, found: &mut BTreeSet<String>) {
    let first = value.split("::").next().unwrap_or("");
    let named = value == first || value.starts_with(&format!("{first}::"));
    if named && !first.is_empty() && first.chars().all(|c| c == '_' || c.is_ascii_alphanumeric()) {
        found.insert(plain(&first));
    }
}

#[cfg(test)]
#[path = "net_tests.rs"]
mod tests;
