// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The text predicates of the Python grammar: `str.strip`, `str.isidentifier` and its regular
//! expressions, written out so that they accept the same texts.

/// A character that Python `str.isspace` accepts. Rust `char::is_whitespace` omits the four
/// separators U+001C to U+001F.
fn python_space(character: char) -> bool {
    character.is_whitespace() || ('\u{1c}'..='\u{1f}').contains(&character)
}

/// `bool(value.strip())` of Python.
pub(crate) fn has_text(value: &str) -> bool {
    value.chars().any(|character| !python_space(character))
}

/// Python `str.isidentifier`: an XID start or `_`, then XID continue characters.
pub(crate) fn python_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    match characters.next() {
        Some(first) if first == '_' || unicode_ident::is_xid_start(first) => {
            characters.all(unicode_ident::is_xid_continue)
        }
        _ => false,
    }
}

/// `[A-Za-z_][A-Za-z0-9_]*`.
fn ascii_identifier(value: &str) -> bool {
    let mut characters = value.chars();
    match characters.next() {
        Some(first) if first == '_' || first.is_ascii_alphabetic() => {
            characters.all(|character| character == '_' || character.is_ascii_alphanumeric())
        }
        _ => false,
    }
}

/// `_PACKAGE_NAME`: ASCII identifiers joined by dots.
pub(crate) fn dotted_name(value: &str) -> bool {
    value.split('.').all(ascii_identifier)
}

/// `_PUBLIC_ENTRY`: `pkg.module` or `pkg.module:Name`.
pub(crate) fn public_entry(value: &str) -> bool {
    match value.split_once(':') {
        Some((module, name)) => dotted_name(module) && ascii_identifier(name),
        None => dotted_name(value),
    }
}

/// Each part between dots is a Python identifier.
pub(crate) fn qualified_identifier(value: &str) -> bool {
    value.split('.').all(python_identifier)
}

fn package_character(character: char) -> bool {
    character.is_ascii_lowercase() || character.is_ascii_digit()
}

/// `(?:@[a-z0-9_-]+/)?[a-z0-9][a-z0-9._-]*`: a package identity with an optional scope.
pub(crate) fn package_identity(value: &str) -> bool {
    let name = match value.strip_prefix('@') {
        Some(scoped) => match scoped.split_once('/') {
            Some((scope, name))
                if !scope.is_empty()
                    && scope
                        .chars()
                        .all(|c| package_character(c) || c == '_' || c == '-') =>
            {
                name
            }
            _ => return false,
        },
        None => value,
    };
    let mut characters = name.chars();
    match characters.next() {
        Some(first) if package_character(first) => {
            characters.all(|c| package_character(c) || matches!(c, '.' | '_' | '-'))
        }
        _ => false,
    }
}
