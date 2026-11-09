// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Record the provenance of a collector binary when it is built.
//!
//! The `build.rs` of each collector crate calls `emit`, so that one script owns the digest (AD-335).
//!
//! `ARCHKEEL_CODE_DIGEST` is SHA-256 over each source input of the native workspace, as
//! `analyzer/runtime.collector_provenance` digests the Python collector: the relative path, a NUL,
//! the bytes, a NUL. It is the same on every platform.
//!
//! The inputs come from the workspace tree, not from a list: every `.rs` file and every
//! `Cargo.toml` under `native/`, plus `Cargo.lock` and `rust-toolchain.toml`. A new crate or a
//! new directory of a crate therefore changes the digest. Each input and each directory under
//! `native/` is a `rerun-if-changed` path, so cargo runs this script again when an input changes
//! or a file or directory appears. The root directory is not a rerun path: it holds `target/`,
//! and cargo would scan that for changes.
//!
//! Walk rules:
//! - A directory named `target` is skipped at any depth. It holds build output, not sources.
//! - A hidden directory (name starts with `.`) is skipped.
//! - A hidden file is hashed when its name matches the rules above. Extra input only causes a
//!   rebuild, which is safe.
//! - A symbolic link is ignored. It is neither followed nor hashed.
//!
//! Not part of the digest: `RUSTFLAGS`, cargo features and the profile. The digest identifies the
//! source, not the build options.

// A build script that fails stops the build, not a scan, so it may expect.
#![allow(clippy::expect_used)]
#![forbid(unsafe_code)]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

/// Print the `cargo:` lines of one collector crate. Run it from the `build.rs` of that crate.
pub fn emit() {
    // The build script of a collector runs in its crate directory, one below `native/`.
    let manifest = std::env::var("CARGO_MANIFEST_DIR").expect("cargo sets the manifest directory");
    let native = Path::new(&manifest)
        .parent()
        .expect("the crate is in native/")
        .to_path_buf();
    let mut inputs = Vec::new();
    let mut directories = Vec::new();
    walk(&native, &mut inputs, &mut directories);
    inputs.sort();
    directories.sort();
    let mut digest = Sha256::new();
    for path in &inputs {
        println!("cargo:rerun-if-changed={}", path.display());
        let relative = path.strip_prefix(&native).expect("an input is in native/");
        let name: Vec<String> = relative
            .components()
            .map(|part| part.as_os_str().to_string_lossy().into_owned())
            .collect();
        digest.update(name.join("/").as_bytes());
        digest.update(b"\0");
        digest.update(fs::read(path).expect("an input file is readable"));
        digest.update(b"\0");
    }
    for directory in directories.iter().filter(|directory| **directory != native) {
        println!("cargo:rerun-if-changed={}", directory.display());
    }
    let hex: String = digest
        .finalize()
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect();
    println!("cargo:rustc-env=ARCHKEEL_CODE_DIGEST={hex}");
    println!("cargo:rustc-env=ARCHKEEL_RUSTC_VERSION={}", rustc_version());
    // The wheel build sets the Archkeel version; a local build reports an unknown version.
    println!("cargo:rerun-if-env-changed=ARCHKEEL_VERSION");
    let version = std::env::var("ARCHKEEL_VERSION").unwrap_or_else(|_| "0+unknown".to_owned());
    println!("cargo:rustc-env=ARCHKEEL_VERSION={version}");
}

/// Collect the inputs and the directories below `directory`, which starts at the root `native`.
fn walk(directory: &Path, inputs: &mut Vec<PathBuf>, directories: &mut Vec<PathBuf>) {
    directories.push(directory.to_path_buf());
    let entries = fs::read_dir(directory).expect("a source directory is readable");
    for entry in entries {
        let entry = entry.expect("a directory entry is readable");
        let path = entry.path();
        let file_type = entry.file_type().expect("a directory entry has a type");
        let name = entry.file_name();
        if file_type.is_dir() {
            // `DirEntry::file_type` does not follow a symbolic link, so a link is not walked.
            let hidden = name.to_string_lossy().starts_with('.');
            if !hidden && name != "target" {
                walk(&path, inputs, directories);
            }
        } else if file_type.is_file() && is_input(&name.to_string_lossy()) {
            inputs.push(path);
        }
    }
}

fn is_input(name: &str) -> bool {
    name.ends_with(".rs") || matches!(name, "Cargo.toml" | "Cargo.lock" | "rust-toolchain.toml")
}

// `rustc 1.88.0 (6b00bc388 2025-06-23)` gives `1.88.0`.
fn rustc_version() -> String {
    let rustc = std::env::var("RUSTC").unwrap_or_else(|_| "rustc".to_owned());
    let output = Command::new(rustc)
        .arg("--version")
        .output()
        .expect("rustc reports its version");
    let text = String::from_utf8_lossy(&output.stdout);
    text.split_whitespace()
        .nth(1)
        .expect("rustc version text has a version")
        .to_owned()
}
