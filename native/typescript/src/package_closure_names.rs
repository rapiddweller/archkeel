// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Text helpers for the installed-package closure.

/// A runtime loader whose target is not a literal.
pub(super) fn unknown_loader(
    computed_form: Option<&str>,
    text: &str,
    repaired: Option<i64>,
) -> Option<String> {
    if let Some(form) = computed_form {
        return Some(format!("computed {form}"));
    }
    if text.contains("createRequire(") {
        return Some("createRequire".to_owned());
    }
    let line = repaired?;
    let bare = ["require(", "import("].iter().any(|call| {
        text.match_indices(call).any(|(at, _)| {
            let rest = text
                .get(at + str::len(call)..)
                .unwrap_or_default()
                .trim_start();
            !rest.starts_with(['"', '\'', '`'])
        })
    });
    bare.then(|| format!("a call of require or import() in the repaired file (line {line})"))
}

/// The names that a `node_modules` search tries for a package.
pub(super) fn package_names(name: &str, type_only: bool) -> Vec<String> {
    let mut names = vec![name.to_owned()];
    if type_only {
        let mangled = name
            .strip_prefix('@')
            .map_or_else(|| name.to_owned(), |scoped| scoped.replacen('/', "__", 1));
        Vec::push(&mut names, format!("@types/{mangled}"));
    }
    names
}

/// Each quoted text after one of the words. A word in a comment is read too, on purpose.
pub(super) fn quoted_after(text: &str, words: &[&str]) -> Vec<String> {
    let bytes = text.as_bytes();
    let mut found = Vec::new();
    for word in words {
        for (at, _) in text.match_indices(word) {
            let before = at.checked_sub(1).and_then(|i| bytes.get(i));
            let joined = |b: &u8| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'$' | b'.');
            if before.is_some_and(joined) {
                continue;
            }
            let rest = text
                .get(at + str::len(word)..)
                .unwrap_or_default()
                .trim_start();
            let rest = rest.strip_prefix('(').map_or(rest, str::trim_start);
            if let Some(quoted) = quoted(rest) {
                Vec::push(&mut found, quoted);
            }
        }
    }
    found
}

/// A leading quoted specifier without spaces or delimiters.
fn quoted(rest: &str) -> Option<String> {
    let quote = rest
        .chars()
        .next()
        .filter(|c| matches!(c, '"' | '\'' | '`'))?;
    let inner = rest.get(1..)?;
    let text = inner.get(..inner.find(quote)?)?;
    let specifier = !str::is_empty(text)
        && !text.contains(|c: char| c.is_whitespace() || "(){}[],;".contains(c));
    specifier.then(|| text.to_owned())
}
