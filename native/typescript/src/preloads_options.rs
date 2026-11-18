// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Reading Node preload options from command text.

/// The flags of Node that load a module before the program.
const FLAGS: [&str; 5] = [
    "-r",
    "--require",
    "--import",
    "--loader",
    "--experimental-loader",
];

/// A Node preload flag whose target the plain command reader cannot find.
pub(super) fn has_preload_flag(command: &str) -> bool {
    command.split_whitespace().any(|token| {
        FLAGS
            .iter()
            .any(|flag| token == *flag || token.starts_with(&format!("{flag}=")))
            || token.starts_with("-r")
    })
}

/// The modules named by Node preload flags. Quotes are dropped, including in `NODE_OPTIONS`.
pub(super) fn option_names(command: &str) -> Vec<String> {
    let plain: String = command
        .chars()
        .map(|character| {
            if matches!(character, '"' | '\'') {
                ' '
            } else {
                character
            }
        })
        .collect();
    let mut tokens = plain.split_whitespace().map(|token| {
        let lower = str::to_ascii_lowercase(token);
        let prefix = ["node_options=", "node-options="]
            .iter()
            .find(|prefix| lower.starts_with(*prefix));
        prefix.map_or(token, |prefix| {
            token.get(str::len(prefix)..).unwrap_or_default()
        })
    });
    let mut names = Vec::new();
    while let Some(token) = tokens.next() {
        if FLAGS.contains(&token) {
            Vec::extend(&mut names, tokens.next().map(str::to_owned));
            continue;
        }
        let joined = FLAGS
            .iter()
            .find_map(|flag| token.strip_prefix(&format!("{flag}=")));
        Vec::extend(&mut names, joined.map(str::to_owned));
    }
    names.retain(|name| !str::is_empty(name));
    names
}
