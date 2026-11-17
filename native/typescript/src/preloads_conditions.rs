// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Detection of custom Node resolution conditions.

/// Whether a preload command adds custom Node export conditions.
pub(super) fn has_conditions_flag(commands: &[String]) -> bool {
    commands.iter().any(|command| {
        if has_opaque_options(command) {
            return true;
        }
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
        plain.split_whitespace().any(|token| {
            let lower = str::to_ascii_lowercase(token);
            let option = ["node_options=", "node-options="]
                .iter()
                .find_map(|prefix| lower.strip_prefix(prefix))
                .unwrap_or(&lower);
            ["--conditions", "-c"].contains(&lower.as_str())
                || ["--conditions", "-c"].contains(&option)
                || option.starts_with("--conditions")
                || option.starts_with("-c=")
        })
    })
}

pub(super) fn has_opaque_options(command: &str) -> bool {
    command.contains('\\') || command.contains('$') || command.contains('`')
}

pub(super) fn has_opaque_preload_command(command: &str) -> bool {
    if !has_opaque_options(command) {
        return false;
    }
    let lower = command.to_ascii_lowercase();
    if lower.contains("node_options") || lower.contains("node-options") {
        return true;
    }
    let normalized: String = command
        .chars()
        .filter(|character| !matches!(character, '\\' | '"' | '\''))
        .collect();
    normalized.split_whitespace().any(|token| {
        [
            "-r",
            "--require",
            "--import",
            "--loader",
            "--experimental-loader",
        ]
        .iter()
        .any(|flag| token == *flag || token.starts_with(&format!("{flag}=")))
    })
}
