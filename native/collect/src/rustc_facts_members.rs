// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The workspace members and the configurations of the matrix (AD-1047).

use crate::outside_reach::{dependents, Runs};
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
pub(crate) fn for_worker(repository: &Path, scan_roots: &[String], build: bool) -> String {
    read(repository, scan_roots, build)
        .unwrap_or_else(|why| json!({ "unavailable": why }))
        .to_string()
}

fn read(repository: &Path, scan_roots: &[String], build: bool) -> Result<Value, String> {
    let real = repository
        .canonicalize()
        .map_err(|why| format!("cannot read the repository root: {why}"))?;
    let (mut roots, mut found, mut names) = (Vec::new(), Vec::new(), BTreeSet::new());
    let mut held = BTreeSet::new();
    // A member below no scan root is not read: the scan treats it as code outside.
    let scanned: Vec<String> = (scan_roots.iter())
        .filter_map(|r| real.join(r).canonicalize().ok())
        .map(|r| r.to_string_lossy().replace('\\', "/"))
        .collect();
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
        let outside = outside_of(&metadata, &all, (&scanned, build));
        held.extend(listed_under_root(&real, root, outside.iter()));
        held.extend(outside.iter().filter_map(|dir| {
            let relative = Path::new(dir).strip_prefix(&real).ok()?;
            Some(relative.to_string_lossy().replace('\\', "/"))
        }));
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
    Ok(json!({ "roots": roots, "members": found, "names": names, "held": held }))
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

/// The members whose edges pass through code that the scan does not read (`outside_reach`).
fn outside_of(
    metadata: &[u8],
    all: &Members,
    (scanned, build): (&[String], bool),
) -> BTreeSet<String> {
    let Ok(meta) = serde_json::from_slice::<Value>(metadata) else {
        return all.roots.keys().cloned().collect();
    };
    let ids: BTreeSet<&str> = (meta
        .get("workspace_members")
        .and_then(Value::as_array)
        .into_iter()
        .flatten())
    .filter_map(Value::as_str)
    .collect();
    let runs = Runs {
        resolve: &resolve_metadata,
        check: &check_json,
        build,
    };
    let below = |dir: &String| {
        scanned
            .iter()
            .any(|r| dir == r || dir.starts_with(&format!("{r}/")))
    };
    let dirs: BTreeMap<String, BTreeSet<String>> = (all.roots.iter())
        .filter(|(dir, _)| below(dir))
        .map(|(dir, files)| (dir.clone(), files.clone()))
        .collect();
    dependents(&meta, &ids, &dirs, &all.names, &runs)
}

/// A Cargo command with a clean environment. The `--config` flags beat every config file, so a config of the
/// repository cannot name the compiler (`build.rustc`, `build.rustc-wrapper`) or the flags, but its `[patch]` stays.
/// `RUSTUP_TOOLCHAIN` is the default toolchain: a `rust-toolchain.toml` of the repository cannot install another one.
fn sealed_cargo(subcommand: &str, cwd: &Path) -> Command {
    let mut cmd = Command::new("cargo");
    cmd.arg(subcommand).args(["--offline", "--locked"]);
    cmd.args([
        "--config",
        "build.rustflags=[]",
        "--config",
        "build.rustc-wrapper=\"\"",
    ]);
    cmd.args(["--config", "build.rustc=\"rustc\""]);
    // Cargo runs the workspace wrapper while it probes rustc, also for `cargo metadata`.
    cmd.args(["--config", "build.rustc-workspace-wrapper=\"\""]);
    cmd.current_dir(cwd).env_clear();
    for name in KEPT_ENV {
        if let Some(value) = std::env::var_os(name) {
            cmd.env(name, value);
        }
    }
    let active = Command::new("rustup")
        .args(["show", "active-toolchain"])
        .current_dir(std::env::temp_dir())
        .output()
        .ok();
    let toolchain = active.map(|o| {
        String::from_utf8_lossy(&o.stdout)
            .split_whitespace()
            .next()
            .unwrap_or("")
            .to_owned()
    });
    if let Some(name) = toolchain.filter(|n| !n.is_empty()) {
        cmd.env("RUSTUP_TOOLCHAIN", name);
    }
    cmd
}

/// The text of each `.cargo/config(.toml)` from `root` upwards.
fn config_texts(root: &Path) -> String {
    let files = root
        .ancestors()
        .flat_map(|d| [d.join(".cargo/config.toml"), d.join(".cargo/config")]);
    files
        .filter_map(|f| std::fs::read_to_string(f).ok())
        .collect()
}

/// `cargo metadata` with the resolve graph, from the workspace root. It runs no build script. `--locked` keeps Cargo from
/// writing a `Cargo.lock` into the scanned repository: without a lock file this gives `None`.
fn resolve_metadata(root: &Path) -> Option<Value> {
    // A config with an `[env]` table can set `PATH`, `RUSTUP_HOME` or a library path for the `rustc` that Cargo starts
    // to probe the host: no flag turns that table off. Such a repository is not resolved here (the fallback holds).
    if config_texts(root).contains("env") {
        return None;
    }
    let mut cmd = sealed_cargo("metadata", root);
    // All features: an optional dependency that a feature enables is a possible edge.
    let out = cmd
        .args(["--format-version", "1", "--all-features"])
        .output()
        .ok()?;
    out.status.success().then_some(())?;
    serde_json::from_slice(&out.stdout).ok()
}

/// `cargo check --message-format=json` of the packages with these ids, into `target`. It runs the build scripts and
/// the procedural macros of their dependencies: the caller needs the permission of the operator (AD-1130).
fn check_json(root: &Path, ids: &[String], target: &Path) -> Option<String> {
    let mut cmd = sealed_cargo("check", root);
    cmd.args(["--message-format=json", "--all-targets"])
        .env("CARGO_TARGET_DIR", target);
    for id in ids {
        cmd.args(["-p", id]);
    }
    let out = cmd.output().ok()?;
    out.status
        .success()
        .then(|| String::from_utf8_lossy(&out.stdout).into_owned())
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
