// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The workspace members and the configurations of the matrix (AD-1047).

use archkeel_facts::type_reach::{matrix, Config, Unavailable, MAX_FEATURES};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};
use std::process::Command;

/// The only variables that a Cargo run may inherit. `RUSTC`, `RUSTFLAGS`, `CARGO_BUILD_*` and the like
/// would change the build that the facts claim.
pub(crate) const KEPT_ENV: [&str; 4] = ["PATH", "HOME", "RUSTUP_HOME", "CARGO_HOME"];

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
    /// The package name of each member.
    pub(crate) names: BTreeSet<String>,
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
        names: BTreeSet::new(),
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
        found.names.insert(name.clone());
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

// The members of the scan for the Rust worker (#1989, AD-1097): the answer of `cargo metadata` as JSON text.
/// The members of the workspace of each scan root that has a `Cargo.toml` at or above it. `roots` lists those scan roots and
/// `members` the directory of each member, relative to the repository root, without a closing slash.
pub(crate) fn for_worker(repository: &Path, scan_roots: &[String]) -> String {
    read(repository, scan_roots)
        .unwrap_or_else(|why| json!({ "unavailable": why }))
        .to_string()
}

fn read(repository: &Path, scan_roots: &[String]) -> Result<Value, String> {
    let real = repository
        .canonicalize()
        .map_err(|why| format!("cannot read the repository root: {why}"))?;
    let (mut roots, mut found, mut names) = (Vec::new(), Vec::new(), BTreeSet::new());
    for root in scan_roots {
        let Some(manifest) = nearest_manifest(&real, root) else {
            continue;
        };
        let manifest = manifest
            .canonicalize()
            .map_err(|why| format!("cannot read {}: {why}", manifest.display()))?;
        let metadata = metadata(&manifest)?;
        let all = members(&metadata, &real).map_err(|_| {
            format!(
                "cargo metadata of {} names no workspace member",
                manifest.display()
            )
        })?;
        let root = root.trim_end_matches('/');
        roots.push(root.to_owned());
        names.extend(all.names.iter().cloned());
        // The walk lists a file under the path of its scan root. A scan root that is a symlink has another real path
        // than the member directory has, so each member below the real root is also listed under the root path.
        found.extend(listed_under_root(&real, root, all.roots.keys()));
        // The snapshot lists paths with `/`; the members reader prints the separator of the platform.
        // A member that is a symlink has two paths: Cargo builds the one it names, and the walk lists the real one.
        for real_dir in all.roots.keys() {
            if let Ok(relative) = Path::new(real_dir).strip_prefix(&real) {
                found.push(relative.to_string_lossy().replace('\\', "/"));
            }
        }
        found.extend(
            all.dirs
                .iter()
                .map(|d| d.replace('\\', "/").trim_end_matches('/').to_owned()),
        );
    }
    found.sort();
    found.dedup();
    Ok(json!({ "roots": roots, "members": found, "names": names }))
}

/// The `Cargo.toml` in the scan root, else in the nearest directory above it, up to the repository root. A
/// workspace often sits above the scan root, and `cargo metadata` of any of its members lists them all.
fn nearest_manifest(repository: &Path, root: &str) -> Option<PathBuf> {
    let mut dir = repository.join(root);
    loop {
        let manifest = dir.join("Cargo.toml");
        if manifest.is_file() {
            return Some(manifest);
        }
        if dir == repository || !dir.pop() {
            return None;
        }
    }
}

/// The member directories below the real path of a scan root, under the path of the root.
fn listed_under_root<'a>(
    real: &Path,
    root: &str,
    dirs: impl Iterator<Item = &'a String>,
) -> Vec<String> {
    let Ok(real_root) = real.join(root).canonicalize() else {
        return Vec::new();
    };
    let below = |dir: &String| {
        let relative = Path::new(dir).strip_prefix(&real_root).ok()?;
        let relative = relative.to_string_lossy().replace('\\', "/");
        Some(
            format!("{root}/{relative}")
                .trim_end_matches('/')
                .to_owned(),
        )
    };
    dirs.filter_map(below).collect()
}

/// `cargo metadata --no-deps` from a neutral directory, so that neither a `rust-toolchain.toml` nor a
/// `.cargo/config.toml` of the repository changes the run. It reads manifests only: no build script, no network.
fn metadata(manifest: &Path) -> Result<Vec<u8>, String> {
    let mut cmd = Command::new("cargo");
    cmd.args([
        "metadata",
        "--format-version",
        "1",
        "--no-deps",
        "--offline",
    ])
    .arg("--manifest-path")
    .arg(manifest)
    .current_dir(std::env::temp_dir())
    .env_clear();
    for name in KEPT_ENV {
        if let Some(value) = std::env::var_os(name) {
            cmd.env(name, value);
        }
    }
    let out = cmd
        .output()
        .map_err(|why| format!("cargo metadata did not start: {why}"))?;
    if out.status.success() {
        return Ok(out.stdout);
    }
    let stderr = String::from_utf8_lossy(&out.stderr);
    let first = stderr.lines().find(|l| !l.trim().is_empty()).unwrap_or("");
    Err(format!(
        "cargo metadata of {} failed: {first}",
        manifest.display()
    ))
}
