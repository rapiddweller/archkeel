// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Detect computed entries in configuration setup arrays.

/// Whether any setup array contains executable expressions outside its literal entries.
pub(super) fn list(text: &str, key: &str) -> bool {
    let mut remaining = text;
    while let Some(at) = remaining.find(key) {
        let rest = remaining.get(at + key.len()..).unwrap_or_default();
        if array(rest) {
            return true;
        }
        remaining = rest;
    }
    false
}

fn array(rest: &str) -> bool {
    let Some(end) = rest.find(']') else {
        return true;
    };
    let mut quoted = false;
    let mut quote = '\0';
    let mut code = String::new();
    for character in rest[..end].chars() {
        if quoted {
            if character == quote {
                quoted = false;
            }
        } else if matches!(character, '\'' | '"' | '`') {
            quoted = true;
            quote = character;
        } else {
            code.push(character);
        }
    }
    quoted
        || code
            .chars()
            .any(|c| !c.is_whitespace() && !":[],".contains(c))
}
