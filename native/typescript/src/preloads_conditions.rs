// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Detection of custom Node resolution conditions.

/// Whether a preload command adds custom Node export conditions.
pub(super) fn has_conditions_flag(commands: &[String]) -> bool {
    commands.iter().any(|command| {
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
            ["--conditions", "-c"].contains(&lower.as_str())
                || lower.starts_with("--conditions=")
                || lower.starts_with("-c=")
        })
    })
}
