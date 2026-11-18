// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The deliberately narrow package-script command form with a proven working directory.

use serde_json::Value;

/// Preload names and unresolved preload flags from package scripts.
pub(super) fn script_names(scripts: Option<&Value>) -> Vec<String> {
    let scripts = scripts.and_then(Value::as_object);
    let names: Vec<String> = scripts
        .into_iter()
        .flat_map(serde_json::Map::values)
        .filter_map(Value::as_str)
        .flat_map(|script| {
            let mut found = super::options_reader::option_names(script);
            if super::conditions::has_opaque_preload_command(script) {
                found.push("<dynamic preload target>".to_owned());
            }
            if found.is_empty() && super::options_reader::has_preload_flag(script) {
                vec!["<dynamic preload target>".to_owned()]
            } else {
                found
            }
        })
        .collect();
    if names.is_empty()
        && scripts.is_some_and(|scripts| {
            scripts
                .values()
                .filter_map(Value::as_str)
                .any(opaque_command)
        })
    {
        return vec!["<unsupported package script>".to_owned()];
    }
    names
}

/// Whether any package script can change the working directory or command target.
pub(crate) fn script_cwd_unknown(base: &str, text: &str) -> bool {
    if base != "package.json" {
        return false;
    }
    serde_json::from_str::<Value>(text)
        .ok()
        .and_then(|json| json.get("scripts").cloned())
        .and_then(|scripts| scripts.as_object().cloned())
        .is_some_and(|scripts| {
            scripts
                .values()
                .filter_map(Value::as_str)
                .any(|command| !simple_node_command(command))
        })
}

pub(super) fn opaque_command(command: &str) -> bool {
    !simple_node_command(command)
}

fn simple_node_command(command: &str) -> bool {
    let Some(rest) = command.trim_start().strip_prefix("node") else {
        return false;
    };
    if rest
        .chars()
        .next()
        .is_some_and(|character| !character.is_whitespace())
    {
        return false;
    }
    let mut quote = None;
    let mut just_closed = false;
    let mut previous: Option<char> = None;
    for character in rest.chars() {
        if matches!(character, '\\' | '$' | '`' | '\n' | '\r') {
            return false;
        }
        if just_closed && !character.is_whitespace() {
            return false;
        }
        just_closed = false;
        match quote {
            Some(delimiter) if character == delimiter => {
                quote = None;
                just_closed = true;
            }
            Some(_) if character.is_whitespace() => return false,
            Some(_) => {}
            None if matches!(character, '\'' | '"') => {
                if previous.is_some_and(|before| !before.is_whitespace()) {
                    return false;
                }
                quote = Some(character);
            }
            None if character.is_whitespace() => {}
            None if matches!(
                character,
                ';' | '|' | '&' | '<' | '>' | '(' | ')' | '*' | '?' | '[' | ']' | '!' | '#' | '~'
            ) =>
            {
                return false;
            }
            None => {}
        }
        previous = Some(character);
    }
    quote.is_none()
}
