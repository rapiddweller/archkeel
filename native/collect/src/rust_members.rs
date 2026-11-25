// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The Cargo workspace members of a Rust scan, for the worker (#1989, AD-1047).
//!
//! A crate below a scan root that is no member of the workspace is foreign code, wherever its directory is. The
//! Rust worker starts no process (AD-316), so the core asks `cargo metadata` and gives the answer to the worker
//! as JSON text: `{"roots": [...], "members": [...]}`, or `{"unavailable": "<reason>"}`. The members reader is the
//! one of the type-reach producer.

use crate::rustc_facts::KEPT_ENV;
use crate::rustc_facts_members::members;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::Command;

/// The members of the workspace of each scan root that has a `Cargo.toml` at or above it. `roots` lists those scan roots and
/// `members` the directory of each member, relative to the repository root, without a closing slash.
pub(crate) fn of(repository: &Path, scan_roots: &[String]) -> String {
    read(repository, scan_roots)
        .unwrap_or_else(|why| json!({ "unavailable": why }))
        .to_string()
}

fn read(repository: &Path, scan_roots: &[String]) -> Result<Value, String> {
    let real = repository
        .canonicalize()
        .map_err(|why| format!("cannot read the repository root: {why}"))?;
    let (mut roots, mut found) = (Vec::new(), Vec::new());
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
        roots.push(root.trim_end_matches('/').to_owned());
        found.extend(all.dirs.iter().map(|d| d.trim_end_matches('/').to_owned()));
    }
    found.sort();
    found.dedup();
    Ok(json!({ "roots": roots, "members": found }))
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
