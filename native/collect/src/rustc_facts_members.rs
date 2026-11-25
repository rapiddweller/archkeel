// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The workspace members and the configurations of the matrix (AD-1047).

use archkeel_facts::type_reach::{matrix, Config, Unavailable, MAX_FEATURES};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;
use std::process::Command;

/// The workspace members that `cargo metadata` names: only these crates are workspace code. A path
/// dependency is no member, wherever its directory is.
pub(crate) struct Members {
    /// The `Cargo.toml` path of each member.
    pub(crate) manifests: BTreeSet<String>,
    /// For each member, its canonical manifest directory and the canonical root source files of its targets.
    /// A member run of the driver must match one pair: the directory and a root file of the same member.
    pub(crate) roots: BTreeMap<String, BTreeSet<String>>,
    /// The directory of each member, relative to the scan root, with a closing slash.
    pub(crate) dirs: Vec<String>,
    /// The features of the members, `default` excluded: each one alone is a configuration.
    features: Vec<(String, String)>,
}

/// The members of a workspace, from the JSON that `cargo metadata --no-deps` printed.
pub(crate) fn members(metadata: &[u8], scan_root: &Path) -> Result<Members, Unavailable> {
    let meta: Value = serde_json::from_slice(metadata).map_err(|_| Unavailable::MetadataFailed)?;
    let ids: BTreeSet<&str> = meta
        .get("workspace_members")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .collect();
    let mut found = Members {
        manifests: BTreeSet::new(),
        roots: BTreeMap::new(),
        dirs: Vec::new(),
        features: Vec::new(),
    };
    let text =
        |value: &Value, key: &str| value.get(key).and_then(Value::as_str).map(str::to_string);
    for package in meta
        .get("packages")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        let (Some(id), Some(name), Some(path)) = (
            text(package, "id"),
            text(package, "name"),
            text(package, "manifest_path"),
        ) else {
            continue;
        };
        if !ids.contains(id.as_str()) {
            continue;
        }
        let dir = Path::new(&path).parent().unwrap_or(Path::new(&path));
        let real_dir = std::fs::canonicalize(dir)
            .map_err(|_| Unavailable::MetadataFailed)?
            .to_string_lossy()
            .replace('\\', "/");
        if let Ok(relative) = dir.strip_prefix(scan_root) {
            found.dirs.push(
                format!("{}/", relative.display())
                    .trim_start_matches('/')
                    .to_string(),
            );
        }
        found.manifests.insert(path);

        for target in package
            .get("targets")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
        {
            let src = text(target, "src_path").and_then(|p| std::fs::canonicalize(p).ok());
            found
                .roots
                .entry(real_dir.clone())
                .or_default()
                .extend(src.map(|p| p.to_string_lossy().replace('\\', "/")));
        }
        let features = package.get("features").and_then(Value::as_object);
        for feature in features
            .into_iter()
            .flat_map(|f| f.keys())
            .filter(|f| *f != "default")
        {
            found.features.push((name.clone(), feature.clone()));
        }
    }
    if found.manifests.is_empty() {
        return Err(Unavailable::MetadataFailed);
    }
    found.features.sort();
    Ok(found)
}

/// The matrix: the three fixed configurations and each feature of a member alone. More features than the
/// cap give no facts; no configuration is dropped silently.
pub(crate) fn configs(members: &Members) -> Result<Vec<Config>, Unavailable> {
    if members.features.len() > MAX_FEATURES {
        return Err(Unavailable::TooManyFeatures(members.features.len()));
    }
    let alone = members
        .features
        .iter()
        .map(|(package, feature)| Config::Feature {
            package: package.clone(),
            feature: feature.clone(),
        });
    Ok(matrix().into_iter().chain(alone).collect())
}

/// The Cargo flags of one configuration.
pub(crate) fn flags(config: &Config) -> Vec<String> {
    match config {
        Config::Default => Vec::new(),
        Config::NoDefaultFeatures => vec!["--no-default-features".to_string()],
        Config::AllFeatures => vec!["--all-features".to_string()],
        Config::Feature { package, feature } => vec![
            "--no-default-features".to_string(),
            "--features".to_string(),
            format!("{package}/{feature}"),
        ],
    }
}

/// Give `cmd` the variables of the driver. A `[env]` table with `force = true` in a config file of the
/// repository would beat a plain variable, so each one also goes through `--config`, which beats every
/// config file. The member list and the registry directory are made in `base`; an existing registry stays. `None` when that fails.
pub(crate) fn set_driver_vars(
    cmd: &mut Command,
    base: &Path,
    members: &Members,
    vars: &[(&str, String)],
) -> Option<()> {
    let list = base.join("members.tsv");
    let pairs: Vec<String> = (members.roots.iter())
        .flat_map(|(dir, roots)| roots.iter().map(move |root| format!("{dir}\t{root}")))
        .collect();
    if pairs
        .iter()
        .any(|pair| pair.matches('\t').count() != 1 || pair.contains('\n'))
    {
        return None;
    }
    std::fs::write(&list, pairs.join("\n")).ok()?;
    // The registry persists with the work directory: Cargo keeps an unchanged member fresh, the driver does not
    // run for it, and a dependent must still find its crate id. A change of members resets the directory.
    let registry = base.join("registry");
    std::fs::create_dir_all(&registry).ok()?;
    let own = [
        ("AK_FACTS_MEMBERS", list.display().to_string()),
        ("AK_FACTS_REGISTRY", registry.display().to_string()),
    ];
    for (name, value) in vars
        .iter()
        .map(|(n, v)| (*n, v))
        .chain(own.iter().map(|(n, v)| (*n, v)))
    {
        let text = serde_json::to_string(value).ok()?;
        cmd.env(name, value).args([
            "--config".to_string(),
            format!("env.{name}.value={text}"),
            "--config".to_string(),
            format!("env.{name}.force=true"),
        ]);
    }
    Some(())
}
