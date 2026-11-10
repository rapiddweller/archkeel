// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The name `constructor` of a class method and the escapes that can spell it.
//!
//! These are `_instance_constructor`, `_supported_constructor` and `_valid_unicode_member_name` of
//! `parse.py`. A name with an escape that cannot be decoded is not proven, so a class that holds
//! one is not complete.

use tree_sitter::Node;

use crate::kinds::{F, K};
use crate::members::{static_member_name, Place};
use crate::pytext::has_backslash;
use crate::tree::cx::Cx;
use crate::tree::nodes::{children, named_children};

impl Cx<'_> {
    /// `_valid_unicode_member_name`: a code point that an escape names must exist.
    pub fn valid_unicode_member_name(&self, name: Node) -> bool {
        match self.k(name) {
            K::Other => false,
            K::String => named_children(name)
                .into_iter()
                .filter(|child| self.k(*child) == K::EscapeSequence)
                .all(|child| valid_escape(&self.text(child))),
            _ => !has_backslash(&self.text(name)),
        }
    }

    /// `_instance_constructor`: the restricted name `constructor` of a class method.
    pub fn instance_constructor(&self, node: Node, place: &Place) -> bool {
        let name = self.field(node, F::Name);
        let Some(name) = name else {
            return false;
        };
        if !matches!(self.k(node), K::MethodDefinition | K::MethodSignature)
            || !place.class_member()
            || place.parent_kind != K::ClassBody
            || self.modifiers(node).has_static()
            || self.k(name) == K::Other
        {
            return false;
        }
        let mut spelling = self.text(name);
        if self.k(name) == K::String {
            let chars: Vec<char> = spelling.chars().collect();
            spelling = chars
                .get(1..chars.len() - 1)
                .unwrap_or(&[])
                .iter()
                .collect();
        }
        decode_escapes(&spelling) == "constructor"
    }

    /// `_supported_constructor`.
    pub fn supported_constructor(&self, node: Node, place: &Place) -> bool {
        let Some(name) = self.field(node, F::Name) else {
            return false;
        };
        // The nearest sibling that is not a comment must not be a decorator.
        let decorated = place
            .before
            .iter()
            .rev()
            .find(|item| self.k(**item) != K::Comment)
            .is_some_and(|item| self.k(*item) == K::Decorator);
        self.instance_constructor(node, place)
            && static_member_name(&self.text(name)).as_deref() == Some("constructor")
            && !children(node).iter().any(|child| {
                matches!(
                    self.k(*child),
                    K::Get | K::Set | K::Async | K::Asterisk | K::Decorator
                )
            })
            && !decorated
    }
}

/// An escape `\u{...}` must name a code point up to U+10FFFF.
fn valid_escape(escape: &str) -> bool {
    if !escape.starts_with("\\u{") {
        return true;
    }
    let chars: Vec<char> = escape.chars().collect();
    let digits: String = chars
        .get(3..chars.len().saturating_sub(1))
        .unwrap_or(&[])
        .iter()
        .collect();
    let digits = digits.trim_start_matches('0');
    let digits = if digits.is_empty() { "0" } else { digits };
    digits.chars().count() <= 6 && u32::from_str_radix(digits, 16).is_ok_and(|v| v <= 0x10_FFFF)
}

/// `_constructor_escape` applied by `re.sub`: only an ASCII value, or one of `c`, `o` and `s`,
/// is decoded. A line continuation is removed.
fn decode_escapes(spelling: &str) -> String {
    let chars: Vec<char> = spelling.chars().collect();
    let mut out = String::new();
    let mut index = 0;
    while index < chars.len() {
        if chars[index] != '\\' || index + 1 >= chars.len() {
            out.push(chars[index]);
            index += 1;
            continue;
        }
        let (decoded, used) = escape_at(&chars, index + 1);
        match decoded {
            Some(text) => out.push_str(&text),
            None => out.extend(&chars[index..index + 1 + used]),
        }
        index += 1 + used;
    }
    out
}

fn hex_value(digits: &[char]) -> Option<u32> {
    let text: String = digits.iter().collect();
    if digits.is_empty() || !digits.iter().all(char::is_ascii_hexdigit) {
        return None;
    }
    u32::from_str_radix(text.trim_start_matches('0'), 16)
        .ok()
        .or(Some(0))
}

/// The text after a backslash: the decoded text (`None` keeps the source) and the chars it uses.
#[expect(
    clippy::excessive_nesting,
    reason = "the function nests blocks deeper than 4: flatten it (AD-327)"
)]
fn escape_at(chars: &[char], at: usize) -> (Option<String>, usize) {
    let rest = &chars[at..];
    let ascii = |value: Option<u32>| value.filter(|v| *v < 128).and_then(char::from_u32);
    if rest.first() == Some(&'u') {
        if rest.get(1) == Some(&'{') {
            if let Some(close) = rest.iter().position(|c| *c == '}') {
                let digits = &rest[2..close];
                let significant = digits.iter().skip_while(|c| **c == '0').count();
                if !digits.is_empty() && significant <= 6 {
                    if let Some(value) = hex_value(digits) {
                        return (ascii(Some(value)).map(String::from), close + 1);
                    }
                }
            }
        }
        if rest.len() >= 5 {
            if let Some(value) = hex_value(&rest[1..5]) {
                return (ascii(Some(value)).map(String::from), 5);
            }
        }
    }
    if rest.first() == Some(&'x') && rest.len() >= 3 {
        if let Some(value) = hex_value(&rest[1..3]) {
            return (ascii(Some(value)).map(String::from), 3);
        }
    }
    match rest.first() {
        Some('\r') if rest.get(1) == Some(&'\n') => (Some(String::new()), 2),
        Some('\n' | '\r' | '\u{2028}' | '\u{2029}') => (Some(String::new()), 1),
        Some(c @ ('c' | 'o' | 's')) => (Some(c.to_string()), 1),
        Some(_) => (None, 1),
        None => (None, 0),
    }
}
