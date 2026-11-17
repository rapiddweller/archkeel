// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The keys of a `pubspec.yaml` (AD-454, AD-500, AD-800): a bounded YAML parse, the package keys
//! by word for a document that the parse does not read, and the origin of each dependency.

use saphyr::{LoadableYamlNode, Yaml};

use super::package_map::{self, Origin};
use crate::module::is_identifier;

/// The origin of each dependency of a root `pubspec.yaml`; an override replaces the dependency.
/// `None` for a document that the survey does not read key by key.
pub(super) fn declared(document: &Yaml<'_>) -> Option<std::collections::BTreeMap<String, Origin>> {
    let mut found = std::collections::BTreeMap::new();
    for section in ["dependencies", "dev_dependencies", "dependency_overrides"] {
        let Some(deps) = document.as_mapping_get(section) else {
            continue;
        };
        if deps.is_null() {
            continue;
        }
        for (name, dependency) in deps.as_mapping()? {
            let name = Yaml::as_str(name).filter(|name| is_identifier(name))?;
            let origin = origin(dependency)?;
            found.insert(name.to_owned(), origin);
        }
    }
    Some(found)
}

/// The package keys and the marker for an unreadable document.
#[derive(Debug, Default, PartialEq, Eq)]
pub(super) struct PubspecWords {
    pub(super) workspace: bool,
    pub(super) resolution: bool,
    pub(super) path: bool,
    pub(super) escape: bool,
}

/// Parse one bounded YAML document. Other documents retain a conservative gap.
pub(super) fn yaml(text: &str) -> Option<Yaml<'_>> {
    if !text.contains('\\')
        && str::len(text) <= 65_536
        && text
            .lines()
            .all(|line| str::len(line) - str::len(line.trim_start()) <= 128)
        && text
            .bytes()
            .filter(|byte| matches!(byte, b'[' | b'{' | b'-' | b':' | b'?'))
            .count()
            <= 128
    {
        if let Ok(mut documents) = Yaml::load_from_str(text) {
            if Vec::len(&documents) == 1 {
                return documents.pop();
            }
        }
    }
    None
}

pub(super) fn keys(text: &str) -> PubspecWords {
    if let Some(document) = yaml(text) {
        let mut found = PubspecWords::default();
        if yaml_keys(&document, &mut found, 0) {
            return found;
        }
    }
    let mut found = words(text);
    found.escape = true;
    found
}

pub(super) fn yaml_keys(node: &Yaml<'_>, found: &mut PubspecWords, depth: usize) -> bool {
    if depth > 128 {
        return false;
    }
    match node {
        Yaml::Mapping(map) => map.iter().all(|(key, value)| {
            let Some(key) = Yaml::as_str(key) else {
                return false;
            };
            if depth == 0
                && matches!(
                    key,
                    "dependencies" | "dev_dependencies" | "dependency_overrides"
                )
            {
                let Some(deps) = value.as_mapping() else {
                    return false;
                };
                return deps.iter().all(|(name, dependency)| {
                    Yaml::as_str(name).is_some() && yaml_keys(dependency, found, depth + 2)
                });
            }
            match key {
                "path" => found.path = true,
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                "<<" => return false,
                _ => {}
            }
            yaml_keys(value, found, depth + 1)
        }),
        Yaml::Sequence(items) => items.iter().all(|item| yaml_keys(item, found, depth + 1)),
        Yaml::Value(_) => true,
        _ => false,
    }
}

pub(super) fn words(text: &str) -> PubspecWords {
    let mut found = PubspecWords {
        escape: text.contains('\\'),
        ..PubspecWords::default()
    };
    for line in text.split(['\n', '\r']) {
        if line.trim_start_matches([' ', '\t']).starts_with('#') {
            continue;
        }
        for word in line.split(|c: char| !c.is_ascii_alphanumeric()) {
            match word {
                "path" => found.path = true,
                "workspace" => found.workspace = true,
                "resolution" => {
                    found.workspace = true;
                    found.resolution = true;
                }
                _ => {}
            }
        }
    }
    found
}

/// The origin of one dependency value: a version text or null is hosted; a mapping states it.
pub(super) fn origin(dependency: &Yaml<'_>) -> Option<Origin> {
    match dependency {
        Yaml::Value(_) => Some(Origin::Hosted),
        Yaml::Mapping(keys) => {
            let mut pairs = Vec::new();
            for (key, value) in keys {
                let key = Yaml::as_str(key)?;
                let text = if key == "git" && value.is_mapping() {
                    value.as_mapping_get("url").and_then(Yaml::as_str)
                } else {
                    Yaml::as_str(value)
                };
                pairs.push((key, text));
            }
            Some(package_map::origin(&pairs))
        }
        _ => None,
    }
}
