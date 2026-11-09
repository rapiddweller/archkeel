// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Test only: a small source tree in a temporary directory.

use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};

static COUNT: AtomicUsize = AtomicUsize::new(0);

/// Write `files` below a fresh directory. The caller removes it.
pub(crate) fn tree(name: &str, files: &[(&str, &str)]) -> PathBuf {
    let count = COUNT.fetch_add(1, Ordering::Relaxed);
    let process = std::process::id();
    let root = std::env::temp_dir().join(format!("archkeel-rust-{name}-{process}-{count}"));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).unwrap();
    for (path, text) in files {
        let file = root.join(path);
        fs::create_dir_all(file.parent().unwrap()).unwrap();
        fs::write(file, text).unwrap();
    }
    root
}
