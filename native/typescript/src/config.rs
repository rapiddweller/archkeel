// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The files a TSConfig selects, as `config.load_config` lists them.
//!
//! This reader follows `extends`, `files`, `include`, `exclude`, `allowJs`, `checkJs`, `outDir`
//! and `declarationDir`. It also reads the options of module resolution (`options.rs`) and
//! reports each value that it does not understand as a problem.

use std::cell::Cell;
use std::collections::{BTreeMap, BTreeSet};

use serde_json::{Map, Value};

use crate::discover::discover;
use crate::options::{self, Options};
use crate::paths::{dirname, is_outside, join, within};
use crate::snapshot::Snapshot;
use crate::source_input::{classify_file, Suffix};

const CONFIG_DIRECTORY: &str = "${configDir}";

/// The settings of one TSConfig with what it inherits, its paths relative to the snapshot.
#[derive(Clone, Debug, Default)]
pub struct Layer {
    pub compiler: Map<String, Value>,
    /// `files`, `include` and `exclude` of the nearest config that sets each.
    pub specs: BTreeMap<&'static str, Vec<String>>,
    /// `outDir` and `declarationDir`, which exclude by default.
    pub outputs: BTreeMap<&'static str, Option<String>>,
    /// The directory of `baseUrl`, and of the config that sets `paths`.
    pub base_url: Option<String>,
    pub paths_directory: String,
    /// A setting that changes resolution could not be read.
    pub partial: bool,
}

/// What the resolver and the collector need from one TSConfig.
pub struct Config {
    pub options: Options,
    /// The snapshot-relative files that the config selects inside the requested roots, sorted.
    pub files: Vec<String>,
    pub partial: bool,
}

impl Layer {
    /// A layer that could not be read: it sets nothing and makes the settings partial.
    fn unread(directory: &str) -> Layer {
        Layer {
            paths_directory: directory.to_owned(),
            partial: true,
            ..Layer::default()
        }
    }

    /// `config._overlay`: `high` wins key by key; `paths` keeps the directory of its config.
    fn overlay(mut self, high: Layer) -> Layer {
        if high.compiler.contains_key("baseUrl") {
            self.base_url = high.base_url;
        }
        if high.compiler.contains_key("paths") {
            self.paths_directory = high.paths_directory;
        }
        self.compiler.extend(high.compiler);
        self.specs.extend(high.specs);
        self.outputs.extend(high.outputs);
        self.partial |= high.partial;
        self
    }

    /// `allowJs`, or `checkJs` when `allowJs` is absent.
    pub fn allow_js(&self) -> bool {
        let flag = match self.compiler.get("allowJs") {
            Some(Value::Null) | None => self.compiler.get("checkJs"),
            found => found,
        };
        flag == Some(&Value::Bool(true))
    }
}

/// `config.load_config`: the settings and the selected files of the TSConfig.
pub fn load_config(snapshot: &mut Snapshot, tsconfig: &str, roots: &[String]) -> Config {
    let mut problems = Vec::new();
    let own = match dirname(tsconfig) {
        "" => ".",
        directory => directory,
    };
    let layer = read_layer(snapshot, tsconfig, own, &mut problems, &[]);
    let raw = read_json(snapshot, tsconfig).0;
    let references = raw
        .as_ref()
        .is_some_and(|raw| raw.contains_key("references"));
    if references {
        problems.push("Project references require separately observed projects".to_owned());
    }
    let options_before = problems.len();
    let options = options::build(&layer, &mut problems);
    options::script_environment(raw.as_ref(), &mut problems);
    let options_partial = problems.len() > options_before;
    let listed = discover(snapshot, &layer, own, &mut problems);
    if listed.is_empty() && !references {
        problems.push("No inputs were found in config file.".to_owned());
    }
    for root in roots {
        if snapshot.real(root).is_none() {
            problems.push("Missing or unsafe source root".to_owned());
        } else if snapshot.installed(root) {
            problems.push("Installed dependency cannot be a selected source root".to_owned());
        }
    }
    let mut candidates = listed;
    for root in roots {
        if snapshot.is_file(root) {
            candidates.push(root.clone());
        }
    }
    let mut chosen = BTreeSet::new();
    for rel in candidates {
        if !is_outside(&rel)
            && !snapshot.installed(&rel)
            && roots.iter().any(|root| within(root, &rel))
        {
            chosen.insert(rel);
        }
    }
    if chosen.is_empty() {
        problems.push("No selected source files".to_owned());
    }
    snapshot.problems.extend(problems);
    Config {
        options,
        files: chosen.into_iter().collect(),
        partial: layer.partial || options_partial,
    }
}

/// The file text without its byte order mark, then without JSONC comments and trailing commas.
fn read_json(snapshot: &mut Snapshot, rel: &str) -> (Option<Map<String, Value>>, String) {
    let Some(raw) = snapshot.read(rel) else {
        let reason = snapshot.size_gap(rel);
        return (
            None,
            reason.unwrap_or_else(|| format!("Cannot read file '{rel}'.")),
        );
    };
    let text = String::from_utf8_lossy(&raw);
    let plain = strip_jsonc(text.trim_start_matches('\u{feff}'));
    match serde_json::from_str::<Value>(&plain) {
        Ok(Value::Object(map)) => (Some(map), String::new()),
        Ok(_) => (None, format!("'{rel}' is not an object.")),
        Err(_) => (None, format!("Cannot parse '{rel}' as JSON.")),
    }
}

/// `config._strip`: replace each comment with a space, then drop each trailing comma.
///
/// Each look-ahead starts only at a comment or a comma, so the work grows linearly with the text.
pub fn strip_jsonc(text: &str) -> String {
    // After one unclosed `/*`, no later `/*` can close either.
    let unclosed = Cell::new(false);
    let plain = scan(text, |rest| {
        if rest.starts_with(&['/', '/']) {
            Some(rest.iter().position(|c| *c == '\n').unwrap_or(rest.len()))
        } else if rest.starts_with(&['/', '*']) && !unclosed.get() {
            let end = block_comment_end(rest);
            unclosed.set(end.is_none());
            end
        } else {
            None
        }
        .map(|end| (end, " "))
    });
    scan(&plain, |rest| {
        if rest[0] != ',' {
            return None;
        }
        let next = rest[1..].iter().find(|c| !c.is_whitespace());
        matches!(next, Some('}' | ']')).then_some((1, ""))
    })
}

// Copy strings unchanged; `replace` returns the length and the replacement of a match.
fn scan(text: &str, replace: impl Fn(&[char]) -> Option<(usize, &'static str)>) -> String {
    let characters: Vec<char> = text.chars().collect();
    let mut out = String::new();
    let mut index = 0;
    while index < characters.len() {
        let rest = &characters[index..];
        let string = (rest[0] == '"').then(|| string_end(rest)).flatten();
        if let Some(end) = string {
            out.extend(&rest[..end]);
            index += end;
        } else if let Some((end, replacement)) = replace(rest) {
            out.push_str(replacement);
            index += end;
        } else {
            out.push(rest[0]);
            index += 1;
        }
    }
    out
}

// The end of a complete string, or `None` when the quote never closes.
fn string_end(rest: &[char]) -> Option<usize> {
    let mut index = 1;
    while index < rest.len() {
        match rest[index] {
            // As in the Python pattern, `\\.` does not match a line break.
            '\\' if index + 1 < rest.len() && rest[index + 1] != '\n' => index += 2,
            '\\' => return None,
            '"' => return Some(index + 1),
            _ => index += 1,
        }
    }
    None
}

fn block_comment_end(rest: &[char]) -> Option<usize> {
    (2..rest.len().saturating_sub(1))
        .find(|index| rest[*index] == '*' && rest[index + 1] == '/')
        .map(|index| index + 2)
}

/// `config._under`: a spec of a config in `directory`; `${configDir}` names the root config.
fn under(value: &str, directory: &str, own: &str) -> String {
    match value.strip_prefix(CONFIG_DIRECTORY) {
        Some(tail) => match tail.trim_start_matches('/') {
            "" => join(own, "."),
            tail => join(own, tail),
        },
        None => join(directory, value),
    }
}

fn read_layer(
    snapshot: &mut Snapshot,
    rel: &str,
    own: &str,
    problems: &mut Vec<String>,
    stack: &[String],
) -> Layer {
    let (raw, error) = read_json(snapshot, rel);
    let directory = match dirname(rel) {
        "" => ".",
        directory => directory,
    }
    .to_owned();
    let Some(raw) = raw else {
        problems.push(error);
        return Layer::unread(&directory);
    };
    let mut layer = Layer {
        paths_directory: directory.clone(),
        ..Layer::default()
    };
    match raw.get("compilerOptions") {
        Some(Value::Object(options)) => layer.compiler = options.clone(),
        None | Some(Value::Null) => {}
        Some(_) => {
            layer.partial = true;
            problems.push("Compiler option 5024: 'compilerOptions' must be an object.".to_owned())
        }
    }
    let refused = options::invalid(&layer.compiler);
    layer.partial |= !refused.is_empty();
    problems.extend(refused);
    let before_paths = problems.len();
    options::paths(&layer.compiler, problems);
    layer.partial |= problems.len() > before_paths;
    for key in ["files", "include", "exclude"] {
        match raw.get(key) {
            Some(Value::Array(items)) if items.iter().all(Value::is_string) => {
                let items: Vec<String> = items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(|item| item.replace('\\', "/"))
                    .collect();
                layer.partial |= items.iter().any(|item| item.starts_with('/'));
                let specs = items
                    .iter()
                    .filter(|item| !item.starts_with('/'))
                    .map(|item| under(item, &directory, own))
                    .collect();
                layer.specs.insert(key, specs);
            }
            None | Some(Value::Null) => {}
            Some(_) => {
                layer.partial = true;
                problems.push(format!(
                    "Compiler option 5024: '{key}' must be a list of strings."
                ));
            }
        }
    }
    if let Some(Value::String(base)) = layer.compiler.get("baseUrl") {
        layer.base_url = Some(under(base, &directory, own));
    }
    for name in ["outDir", "declarationDir"] {
        if let Some(value) = layer.compiler.get(name) {
            let output = value.as_str().map(|text| under(text, &directory, own));
            layer.outputs.insert(name, output);
        }
    }
    let entries: Vec<Value> = match raw.get("extends") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items.clone(),
        Some(other) => vec![other.clone()],
    };
    let mut inherited = Layer {
        paths_directory: directory.clone(),
        ..Layer::default()
    };
    let mut chain = vec![rel.to_owned()];
    chain.extend_from_slice(stack);
    for entry in entries {
        // An entry that cannot be followed leaves the inherited settings unknown.
        let Some(entry) = entry.as_str() else {
            problems.push(
                "Compiler option 5024: 'extends' must be a string or a list of strings.".to_owned(),
            );
            inherited = inherited.overlay(Layer::unread(&directory));
            continue;
        };
        let Some(path) = extended(snapshot, entry, &directory, problems) else {
            inherited = inherited.overlay(Layer::unread(&directory));
            continue;
        };
        if chain.contains(&path) {
            problems.push(format!(
                "Circularity detected while resolving configuration: {path}"
            ));
            inherited = inherited.overlay(Layer::unread(&directory));
            continue;
        }
        inherited = inherited.overlay(read_layer(snapshot, &path, own, problems, &chain));
    }
    inherited.overlay(layer)
}

/// `config._extended`: the TSConfig file an `extends` entry names; a package is not looked up.
fn extended(
    snapshot: &mut Snapshot,
    entry: &str,
    directory: &str,
    problems: &mut Vec<String>,
) -> Option<String> {
    let named = entry.replace('\\', "/");
    if !(named.starts_with("./") || named.starts_with("../")) {
        problems.push(format!(
            "TSConfig extends through a package is not observed: {named}"
        ));
        return None;
    }
    let mut path = join(directory, &named);
    if !snapshot.is_file(&path) && classify_file(&path) != Some(Suffix::Json) {
        path.push_str(".json");
    }
    if snapshot.is_file(&path) {
        Some(path)
    } else {
        problems.push(format!("File '{named}' not found."));
        None
    }
}

#[cfg(test)]
#[path = "config_tests.rs"]
mod tests;
