// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Record the provenance of the binary when it is built.
//!
//! `ARCHKEEL_CODE_DIGEST` is SHA-256 over each source file of the native workspace, as
//! `analyzer/runtime.collector_provenance` digests the Python collector: the relative path, a NUL,
//! the bytes, a NUL. It is the same on every platform.

// A build script that fails stops the build, not a scan, so it may expect.
#![allow(clippy::expect_used)]

use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

fn main() {
    let native = Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("the crate is in native/")
        .to_path_buf();
    let mut sources = vec![
        native.join("Cargo.toml"),
        native.join("Cargo.lock"),
        native.join("rust-toolchain.toml"),
        native.join("typescript/Cargo.toml"),
        native.join("typescript/build.rs"),
        native.join("wire/Cargo.toml"),
    ];
    for directory in ["typescript/src", "wire/src"] {
        sources.extend(rust_files(&native.join(directory)));
        println!(
            "cargo:rerun-if-changed={}",
            native.join(directory).display()
        );
    }
    sources.sort();
    let mut digest = Sha256::new();
    for path in &sources {
        println!("cargo:rerun-if-changed={}", path.display());
        let relative = path.strip_prefix(&native).expect("a source is in native/");
        let name: Vec<String> = relative
            .components()
            .map(|part| part.as_os_str().to_string_lossy().into_owned())
            .collect();
        digest.update(name.join("/").as_bytes());
        digest.update(b"\0");
        digest.update(fs::read(path).expect("a source file is readable"));
        digest.update(b"\0");
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

fn rust_files(directory: &Path) -> Vec<PathBuf> {
    let entries = fs::read_dir(directory).expect("a source directory is readable");
    entries
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|extension| extension == "rs"))
        .collect()
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
