// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Find a module that a JSDoc comment names (`parse._jsdoc_imports`).
//!
//! `tsc` 5.9.3 reads these only in JavaScript files (#744). The Python collector scans the
//! comment with one regular expression that uses a look-behind, so this scanner follows it by hand.

use crate::pytext::{is_space, is_word};

/// How a tag can name a module.
#[derive(Clone, Copy, PartialEq, Eq)]
enum TagType {
    Braced,
    // The type can omit its braces.
    Bare,
    // A `[name=default]` also holds a type.
    Template,
    Import,
}

fn tag_type(name: &str) -> Option<TagType> {
    match name {
        "import" => Some(TagType::Import),
        "template" => Some(TagType::Template),
        "type" | "this" | "enum" | "extends" | "augments" | "implements" | "satisfies" => {
            Some(TagType::Bare)
        }
        "return" | "returns" | "param" | "arg" | "argument" | "prop" | "property" | "typedef"
        | "throws" | "exception" => Some(TagType::Braced),
        _ => None,
    }
}

enum Token<'a> {
    // `@tag`, and whether a `{` follows after spaces and margin stars.
    Tag { name: &'a [char], braced: bool },
    Open,
    Close,
    Bracket,
    End,
    Quote(char),
    Call,
}

fn margin(c: char) -> bool {
    is_space(c) || c == '*'
}

/// The token at `index`, with its length, or `None` when no token starts there.
fn token_at(text: &[char], index: usize) -> Option<(Token<'_>, usize)> {
    match text[index] {
        '@' if index == 0 || margin(text[index - 1]) => {
            let name_end = index
                + 1
                + text[index + 1..]
                    .iter()
                    .take_while(|c| is_word(**c))
                    .count();
            if name_end == index + 1 {
                return None;
            }
            let run = text[name_end..].iter().take_while(|c| margin(**c)).count();
            let braced = text.get(name_end + run) == Some(&'{');
            let length = if braced {
                name_end + run + 1 - index
            } else {
                name_end - index
            };
            Some((
                Token::Tag {
                    name: &text[index + 1..name_end],
                    braced,
                },
                length,
            ))
        }
        '{' => Some((Token::Open, 1)),
        '}' => Some((Token::Close, 1)),
        '[' => Some((Token::Bracket, 1)),
        ']' => Some((Token::End, 1)),
        quote @ ('\'' | '"' | '`') => Some((Token::Quote(quote), 1)),
        'i' if text[index..].starts_with(&['i', 'm', 'p', 'o', 'r', 't'])
            && (index == 0 || !is_word(text[index - 1])) =>
        {
            let run = text[index + 6..].iter().take_while(|c| margin(**c)).count();
            (text.get(index + 6 + run) == Some(&'(')).then_some((Token::Call, 6 + run + 1))
        }
        _ => None,
    }
}

/// An `@import` tag, or `import(` in the type of a tag; prose is no type (#744).
pub fn imports(body: &str) -> bool {
    let text: Vec<char> = body.chars().collect();
    // Only a `/**` comment is a JSDoc block.
    if !text.starts_with(&['/', '*', '*']) {
        return false;
    }
    let mut kind: Option<TagType> = None;
    let mut depth = 0usize;
    // `armed`: the end of a type is not known, so any later import counts.
    let mut armed = false;
    // The quotes seen an odd number of times in the open types.
    let mut odd: Vec<char> = Vec::new();
    let mut index = 3;
    while index < text.len() {
        let Some((token, length)) = token_at(&text, index) else {
            index += 1;
            continue;
        };
        index += length;
        match token {
            Token::Call => {
                if armed || depth > 0 {
                    return true;
                }
            }
            Token::Tag { name, braced } => {
                // A tag inside an open type: a broken type, or an `@` inside a string.
                armed = armed || depth > 0;
                kind = tag_type(&name.iter().collect::<String>());
                if kind == Some(TagType::Import) {
                    return true;
                }
                depth = usize::from(kind.is_some() && braced);
                // Without braces the end of the type is not known.
                armed = armed || (kind == Some(TagType::Bare) && depth == 0);
            }
            _ if kind.is_none() => {}
            Token::Open => depth += 1,
            Token::Bracket if kind == Some(TagType::Template) => depth += 1,
            Token::Close if depth > 0 => {
                depth -= 1;
                // An odd quote count can put this brace or bracket inside a string.
                armed = armed || !odd.is_empty();
            }
            Token::End if kind == Some(TagType::Template) && depth > 0 => {
                depth -= 1;
                armed = armed || !odd.is_empty();
            }
            Token::Quote(quote) if depth > 0 => match odd.iter().position(|seen| *seen == quote) {
                Some(position) => {
                    odd.remove(position);
                }
                None => odd.push(quote),
            },
            _ => {}
        }
    }
    false
}

/// `augmentations.triple_slash`: the quoted text of the first attribute of a leading
/// `/// <tag attribute="value" ... />` that names a file of the project. tsc lowercases the tag
/// name and reads the attributes in any order: `path` or `lib` in `reference`, `path` in
/// `amd-dependency`, and a `types` that names a path (or any name, with a type root inside the
/// project, `type_roots`). #976, #988.
pub fn triple_slash(body: &str, type_roots: bool) -> Option<String> {
    let rest = body.strip_prefix("///")?.trim_start_matches(is_space);
    let rest = rest.strip_prefix('<')?;
    let name_end = rest
        .find(|c: char| is_space(c) || c == '/' || c == '>')
        .unwrap_or(rest.len());
    let name = rest.get(..name_end)?.to_ascii_lowercase();
    let attributes = rest.get(name_end..)?;
    // The tag name is followed by one space; the attributes read from the next character.
    let first = attributes.chars().next().filter(|c| is_space(*c))?;
    let mut found = None;
    attribute_list(attributes.get(first.len_utf8()..)?, |attribute, value| {
        let file = match (name.as_str(), attribute.to_ascii_lowercase().as_str()) {
            ("reference", "path" | "lib") | ("amd-dependency", "path") => true,
            ("reference", "types") => type_roots || value.starts_with(['.', '/']),
            _ => false,
        };
        if file && found.is_none() {
            found = Some(value.to_owned());
        }
    });
    found
}

/// `([^\s=]+)\s*=\s*(['"])(.*?)\2` over the text: each attribute and its quoted value, scanned
/// from every position as `re.finditer` does. A value does not hold a line feed.
fn attribute_list<'a>(text: &'a str, mut each: impl FnMut(&'a str, &'a str)) {
    let mut from = 0;
    while from < text.len() {
        match attribute_at(text, from) {
            Some((name, value, end)) => {
                each(name, value);
                from = end;
            }
            None => {
                from += text
                    .get(from..)
                    .and_then(|t| t.chars().next())
                    .map_or(1, char::len_utf8)
            }
        }
    }
}

fn attribute_at(text: &str, from: usize) -> Option<(&str, &str, usize)> {
    let tail = text.get(from..)?;
    let name_len = tail
        .find(|c: char| is_space(c) || c == '=')
        .unwrap_or(tail.len());
    let name = tail.get(..name_len).filter(|name| !name.is_empty())?;
    let after = tail
        .get(name_len..)?
        .trim_start_matches(is_space)
        .strip_prefix('=')?;
    let after = after.trim_start_matches(is_space);
    let quote = after.chars().next().filter(|c| matches!(c, '\'' | '"'))?;
    let value_text = after.get(1..)?;
    let close = value_text.find(quote)?;
    let value = value_text
        .get(..close)
        .filter(|value| !value.contains('\n'))?;
    let end = text.len() - value_text.len() + close + 1;
    Some((name, value, end))
}
