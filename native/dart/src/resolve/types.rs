// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type texts that the resolver reads (AD-796): a simple name with an optional import
//! prefix, the type arguments of a generic, and a substitution of type parameters. Each function
//! reads the text as written and never guesses: a form that it does not read gives `None`.

/// True for a character that may start a Dart identifier (`[A-Za-z_$]`).
fn starts_name(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_' || c == '$'
}

/// True for a character that may continue a Dart identifier (`[A-Za-z0-9_$]`).
pub(crate) fn continues_name(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '$'
}

/// True when `text` is one Dart identifier.
pub(crate) fn is_name(text: &str) -> bool {
    let mut chars = text.chars();
    chars.next().is_some_and(starts_name) && chars.all(continues_name)
}

/// The identifier at the start of `text` after white space (`_type_name`).
#[cfg_attr(
    not(test),
    expect(dead_code, reason = "AD-796 S2 reads the type name of a site")
)]
pub(crate) fn type_name(text: &str) -> Option<&str> {
    let text = text.trim_start();
    let end = text
        .char_indices()
        .find(|(at, c)| {
            if *at == 0 {
                !starts_name(*c)
            } else {
                !continues_name(*c)
            }
        })
        .map_or(text.len(), |(at, _)| at);
    (end > 0).then(|| text.get(..end)).flatten()
}

/// Each identifier of `text`, in order.
pub(crate) fn names(text: &str) -> Vec<&str> {
    let mut found = Vec::new();
    let mut start = None;
    for (at, c) in text.char_indices() {
        match start {
            None if starts_name(c) => start = Some(at),
            Some(from) if !continues_name(c) => {
                found.extend(text.get(from..at));
                start = None;
            }
            _ => {}
        }
    }
    if let Some(from) = start {
        found.extend(text.get(from..));
    }
    found
}

/// A simple type name with an optional import prefix (`_nominal_type_reference`): `T`, `p.T`,
/// `T<...>` or `p.T<...>` with balanced angle brackets. Any other form gives `None`.
pub(crate) fn nominal(text: &str) -> Option<(Option<&str>, &str)> {
    let mut value = text.trim();
    if let Some(open) = value.find('<') {
        if !value.ends_with('>') {
            return None;
        }
        let mut depth = 0_usize;
        for c in value.get(open..)?.chars() {
            match c {
                '<' => depth = depth.saturating_add(1),
                '>' => depth = depth.checked_sub(1)?,
                _ => {}
            }
        }
        if depth != 0 {
            return None;
        }
        value = value.get(..open)?.trim_end();
    }
    let parts: Vec<&str> = value.split('.').collect();
    if !(1..=2).contains(&parts.len()) || !parts.iter().all(|part| is_name(part)) {
        return None;
    }
    match parts.as_slice() {
        [prefix, name] => Some((Some(prefix), name)),
        [name] => Some((None, name)),
        _ => None,
    }
}

/// `text` with each type parameter of `substitutions` replaced as a whole word
/// (`_substitute_type`), in the order of the type parameters.
pub(crate) fn substitute(text: Option<&str>, substitutions: &[(String, String)]) -> Option<String> {
    let mut value = text?.to_owned();
    for (name, replacement) in substitutions {
        value = replace_word(&value, name, replacement);
    }
    Some(value)
}

fn replace_word(text: &str, word: &str, replacement: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut rest = text;
    let mut before: Option<char> = None;
    while let Some(at) = rest.find(word) {
        let head = rest.get(..at).unwrap_or("");
        let tail = rest.get(at.saturating_add(word.len())..).unwrap_or("");
        let left = head.chars().next_back().or(before);
        let bounded =
            !left.is_some_and(continues_name) && !tail.chars().next().is_some_and(continues_name);
        out.push_str(head);
        out.push_str(if bounded { replacement } else { word });
        before = word.chars().next_back();
        rest = tail;
    }
    out.push_str(rest);
    out
}

/// `text` without white space (`_type_key`): two type texts are equal when their keys are.
pub(crate) fn key(text: &str) -> String {
    text.chars().filter(|c| !c.is_whitespace()).collect()
}

/// The top-level arguments of a type argument list (`_split_types`).
pub(crate) fn split(text: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth = 0_usize;
    let mut start = 0;
    for (at, c) in text.char_indices() {
        match c {
            '<' => depth = depth.saturating_add(1),
            '>' => depth = depth.saturating_sub(1),
            ',' if depth == 0 => {
                parts.push(text.get(start..at).unwrap_or("").trim().to_owned());
                start = at.saturating_add(1);
            }
            _ => {}
        }
    }
    let last = text.get(start..).unwrap_or("").trim();
    if !last.is_empty() {
        parts.push(last.to_owned());
    }
    parts
}

#[cfg(test)]
#[path = "types_tests.rs"]
mod tests;
