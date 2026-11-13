// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A temporary source tree for the unit tests; it is removed when it goes out of scope.

use std::fs;
use std::path::PathBuf;
use std::sync::atomic::{AtomicUsize, Ordering};

static NEXT: AtomicUsize = AtomicUsize::new(0);

/// The actual input charge of the active scan, for resource measurements only.
pub fn charged_bytes() -> Option<u64> {
    crate::work::charged_bytes()
}

pub struct Tree {
    pub root: PathBuf,
}

impl Tree {
    pub fn new(files: &[(&str, &str)]) -> Self {
        let name = format!(
            "archkeel-native-{}-{}",
            std::process::id(),
            NEXT.fetch_add(1, Ordering::SeqCst)
        );
        let root = std::env::temp_dir().join(name);
        for (path, text) in files {
            let file = root.join(path);
            fs::create_dir_all(file.parent().unwrap()).unwrap();
            fs::write(file, text).unwrap();
        }
        fs::create_dir_all(&root).unwrap();
        Self { root }
    }

    pub fn path(&self) -> String {
        self.root.to_string_lossy().into_owned()
    }
}

impl Drop for Tree {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.root);
    }
}
