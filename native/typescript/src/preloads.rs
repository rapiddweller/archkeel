// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The preloads that the repository names in its data files (#1750, AD-845).
//!
//! A tool can load an installed package before the code of the scan runs, with no import of the
//! scan: `node --require preload`, `NODE_OPTIONS`, a test setup file. Such a package can replace a
//! global with project code, or patch the module loader and redirect any import. The collector
//! reads each preload that a data file of the repository names: the flags `-r`, `--require`,
//! `--import`, `--loader` and `--experimental-loader` in a `package.json` script, `NODE_OPTIONS` in
//! a script, `.npmrc` or `.env` file, the jest keys `setupFiles`, `setupFilesAfterEnv`,
//! `setupFilesAfterEach` and `globalSetup`, the mocha key `require`, and the vitest key
//! `setupFiles`. The closure of each installed preload (AD-798) goes to the writer guard of AD-788.
//! A closure file that patches the module loader withholds the routes of every scanned module, and
//! a preload name that names no installed package is a gap with its name.

use serde_json::Value;

use crate::source_input::{classify_file, ModuleFormat, SourceKind};

#[path = "preloads_conditions.rs"]
mod conditions;
#[path = "preloads_dynamic.rs"]
mod dynamic;
#[path = "preloads_options.rs"]
mod options_reader;
#[path = "preloads_script_context.rs"]
mod script_context;
pub(super) use script_context::script_cwd_unknown;
use script_context::script_names;

/// Whether a repository data filename can name a tool preload.
pub(super) fn preload_file(name: &str) -> bool {
    const CONFIGS: [&str; 5] = [
        "vitest.config.",
        "vite.config.",
        "vitest.workspace.",
        "jest.config.",
        "mocha.config.",
    ];
    matches!(
        name,
        "package.json"
            | "jest.config.json"
            | ".mocharc.json"
            | ".mocharc.yml"
            | ".mocharc.yaml"
            | ".npmrc"
            | ".env"
    ) || name.starts_with(".env.")
        || CONFIGS.iter().any(|prefix| name.starts_with(prefix))
}

/// A preload name and the data file and line that name it.
pub(super) struct Named {
    pub(super) name: String,
    pub(super) file: String,
    pub(super) line: usize,
    pub(super) mode: Option<ModuleFormat>,
    pub(super) resolution_unknown: bool,
}

/// Whether this repository config can add an unmodeled Node condition.
pub(super) fn has_custom_conditions(base: &str, text: &str) -> bool {
    if !(base == "package.json" || base == ".npmrc" || base == ".env" || base.starts_with(".env."))
    {
        return false;
    }
    conditions::has_conditions_flag(text)
}

/// Whether env-file inputs or package scripts leave Node's resolution context unknown.
pub(super) fn node_context_unknown(
    base: &str,
    text: &str,
    mut source_exists: impl FnMut(&str) -> bool,
) -> bool {
    if base != "package.json" {
        return text
            .split_whitespace()
            .any(|token| token.starts_with("--env-file"));
    }
    let mut unknown = false;
    let mut found = false;
    let mut tokens = text
        .split_whitespace()
        .map(|token| token.trim_matches(['\'', '"']));
    while let Some(token) = tokens.next() {
        if token == "--env-file-if-exists" {
            found = true;
            match tokens
                .next()
                .map(|path| path.trim_matches(['\'', '"', '\\']))
            {
                Some(path) if !path.is_empty() && !path.starts_with('-') => {
                    unknown |= source_exists(path);
                }
                _ => unknown = true,
            }
        } else if let Some(path) = token.strip_prefix("--env-file-if-exists=") {
            found = true;
            let path = path.trim_matches(['\'', '"', '\\']);
            if path.is_empty() {
                unknown = true;
            } else {
                unknown |= source_exists(path);
            }
        } else if token.starts_with("--env-file") {
            found = true;
            unknown = true;
        }
    }
    if found && (text.contains('$') || text.contains('`') || text.contains('\\')) {
        unknown = true;
    }
    unknown || script_cwd_unknown(base, text)
}

/// Whether a resolved file can be executable runtime source.
pub(super) fn runtime_source(path: &str) -> bool {
    classify_file(path)
        .and_then(|suffix| suffix.source_kind())
        .is_some_and(|kind| kind != SourceKind::Declaration)
}

/// The jest keys that name a module that runs before the tests.
const JEST_KEYS: [&str; 4] = [
    "setupFiles",
    "setupFilesAfterEnv",
    "setupFilesAfterEach",
    "globalSetup",
];

/// The texts of a write to the module loader through `require`: each can redirect any import.
const REQUIRE_PATCHES: [&str; 2] = ["require.cache", ".prototype.require"];

/// The members of the module object that redirect an import when they are written. They count
/// only in a closure that reaches the module object (`MODULE_OBJECT`): `this._cache` of another
/// class is no patch.
const MODULE_PATCHES: [&str; 3] = ["._load", "._resolveFilename", "._cache"];

/// The texts that reach the module object of Node.
const MODULE_OBJECT: [&str; 7] = [
    "require('module')",
    "require(\"module\")",
    "require('node:module')",
    "require(\"node:module\")",
    "module.constructor",
    "mainModule",
    "require.main",
];

/// A malformed JSON config can hide any static preload name.
pub(super) fn malformed_config(base: &str, text: &str) -> bool {
    matches!(base, "package.json" | "jest.config.json" | ".mocharc.json")
        && serde_json::from_str::<Value>(text).is_err()
}

/// The preload names of one data file.
pub(super) fn names_of(base: &str, text: &str) -> Vec<String> {
    match base {
        "package.json" => {
            let Ok(json) = serde_json::from_str::<Value>(text) else {
                return Vec::new();
            };
            let mut names = script_names(Value::get(&json, "scripts"));
            if let Some(jest) = Value::get(&json, "jest") {
                Vec::extend(&mut names, jest_names(jest));
            }
            if let Some(mocha) = Value::get(&json, "mocha") {
                Vec::extend(&mut names, strings(Value::get(mocha, "require")));
            }
            names
        }
        "jest.config.json" => serde_json::from_str::<Value>(text)
            .map(|json| jest_names(&json))
            .unwrap_or_default(),
        ".mocharc.json" => serde_json::from_str::<Value>(text)
            .map(|json| strings(Value::get(&json, "require")))
            .unwrap_or_default(),
        ".mocharc.yml" | ".mocharc.yaml" => yaml_list(text, "require"),
        _ if base == ".npmrc" || base == ".env" || base.starts_with(".env.") => text
            .lines()
            .filter_map(node_options)
            .flat_map(|value| {
                let mut names = options_reader::option_names(&value);
                if conditions::has_opaque_options(&value) {
                    names.push("<dynamic preload target>".to_owned());
                }
                names
            })
            .collect(),
        _ => {
            let mut found = quoted_list(text, "setupFiles");
            if text.contains("setupFiles") && dynamic::list(text, "setupFiles") {
                found.push("<dynamic setupFiles target>".to_owned());
            }
            found
        }
    }
}

/// The Node loader mode of a preload, when a command line establishes it.
pub(super) fn mode_of(base: &str, text: &str, name: &str) -> Option<ModuleFormat> {
    let commands: Vec<String> = if base == "package.json" {
        serde_json::from_str::<Value>(text)
            .ok()?
            .get("scripts")?
            .as_object()?
            .values()
            .filter_map(Value::as_str)
            .map(str::to_owned)
            .collect()
    } else if base == ".npmrc" || base == ".env" || base.starts_with(".env.") {
        text.lines().filter_map(node_options).collect()
    } else {
        Vec::new()
    };
    let mut modes = commands
        .iter()
        .filter_map(|command| option_mode(command, name));
    let mode = modes.next()?;
    modes.all(|next| next == mode).then_some(mode)
}

fn option_mode(command: &str, name: &str) -> Option<ModuleFormat> {
    let tokens: Vec<&str> = command
        .split_whitespace()
        .map(|token| token.trim_matches(['\'', '"']))
        .collect();
    let mut found = None;
    let mut index = 0;
    while index < tokens.len() {
        let token = tokens[index];
        let (flag, target) = token
            .split_once('=')
            .map_or((token, None), |(flag, target)| (flag, Some(target)));
        let mode = match flag {
            "--require" | "-r" => Some(ModuleFormat::Cjs),
            "--import" | "--loader" | "--experimental-loader" => Some(ModuleFormat::Esm),
            _ => None,
        };
        if let Some(mode) = mode {
            let value = target.or_else(|| tokens.get(index + 1).copied());
            if value == Some(name) && found.is_some_and(|previous| previous != mode) {
                return None;
            }
            if value == Some(name) {
                found = Some(mode);
            }
            if target.is_none() {
                index += 1;
            }
        }
        index += 1;
    }
    found
}

/// The modules that the jest keys of a configuration name.
fn jest_names(jest: &Value) -> Vec<String> {
    JEST_KEYS
        .iter()
        .flat_map(|key| strings(Value::get(jest, key)))
        .collect()
}

/// A string, or each string of an array.
fn strings(value: Option<&Value>) -> Vec<String> {
    match value {
        Some(Value::String(text)) => vec![text.clone()],
        Some(Value::Array(items)) => items
            .iter()
            .filter_map(Value::as_str)
            .map(str::to_owned)
            .collect(),
        _ => Vec::new(),
    }
}

/// The value of a `NODE_OPTIONS` (or `node-options`) line of an `.npmrc` or `.env` file.
fn node_options(line: &str) -> Option<String> {
    let line = line.trim();
    let line = line.strip_prefix("export ").unwrap_or(line);
    let (key, value) = line.split_once('=')?;
    let key = str::to_ascii_lowercase(key.trim());
    matches!(String::as_str(&key), "node_options" | "node-options").then(|| value.trim().to_owned())
}

/// The items of a YAML key: a scalar on its line, or the `- item` lines that follow it.
fn yaml_list(text: &str, key: &str) -> Vec<String> {
    let mut names = Vec::new();
    let mut lines = text.lines().peekable();
    while let Some(line) = lines.next() {
        let Some(value) = line.trim().strip_prefix(&format!("{key}:")) else {
            continue;
        };
        let value = value.trim().trim_matches(|c| matches!(c, '"' | '\''));
        if !str::is_empty(value) {
            Vec::push(&mut names, value.to_owned());
            continue;
        }
        while let Some(item) = lines.peek().and_then(|next| next.trim().strip_prefix('-')) {
            let item = item.trim().trim_matches(|c| matches!(c, '"' | '\''));
            Vec::push(&mut names, item.to_owned());
            lines.next();
        }
    }
    names
}

/// The quoted texts after a key of a code file, up to the end of its array or of its value.
fn quoted_list(text: &str, key: &str) -> Vec<String> {
    let mut names = Vec::new();
    for (at, _) in text.match_indices(key) {
        let rest = text.get(at + str::len(key)..).unwrap_or_default();
        let end = rest
            .find(']')
            .unwrap_or_else(|| rest.find('\n').unwrap_or(str::len(rest)));
        let part = rest.get(..end).unwrap_or_default();
        let quoted = part.split(['"', '\'', '`']).skip(1).step_by(2);
        Vec::extend(&mut names, quoted.map(str::to_owned));
    }
    names
}

/// The first line of a text that holds a name, or 1.
pub(super) fn line_of(text: &str, name: &str) -> usize {
    text.lines()
        .position(|line| line.contains(name))
        .map_or(1, |index| index + 1)
}

/// The first line of a text that writes to the module loader; the members of the module object
/// count when the closure reaches it.
pub(super) fn patch_line(text: &str, module: bool) -> Option<usize> {
    text.lines()
        .position(|line| patches_loader(line, module))
        .map(|index| index + 1)
}

/// Whether code reaches Node's module object.
pub(super) fn reaches_module(text: &str) -> bool {
    let compact: String = text
        .chars()
        .filter(|character| !character.is_whitespace())
        .collect();
    MODULE_OBJECT.iter().any(|form| compact.contains(form))
        || [
            "from'module'",
            "from\"module\"",
            "from'node:module'",
            "from\"node:module\"",
        ]
        .iter()
        .any(|form| compact.contains(form))
}

/// The line holds a text of `REQUIRE_PATCHES` (or of `MODULE_PATCHES`, with `module`) that no
/// letter, digit, `_` or `$` continues.
fn patches_loader(line: &str, module: bool) -> bool {
    let patches = REQUIRE_PATCHES
        .iter()
        .chain(MODULE_PATCHES.iter().filter(|_| module));
    patches.into_iter().any(|patch| {
        line.match_indices(patch).any(|(at, _)| {
            let next = line.as_bytes().get(at + str::len(patch));
            !next.is_some_and(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'$'))
        })
    })
}

#[cfg(test)]
#[path = "preloads_tests.rs"]
mod tests;
