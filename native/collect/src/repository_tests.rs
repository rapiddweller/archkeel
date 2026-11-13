// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// The contained reads and the work budget of the survey (AD-406, #1099).

use std::path::PathBuf;

use super::*;

/// A fresh directory below the temporary directory, canonical.
pub(crate) fn scratch(name: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let next = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let path = std::env::temp_dir().join(format!(
        "archkeel-collect-{name}-{}-{next}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&path);
    fs::create_dir_all(&path).unwrap();
    fs::canonicalize(path).unwrap()
}

#[test]
fn a_root_must_be_absolute_canonical_and_a_directory() {
    let base = scratch("root");
    assert!(Root::of(base.to_str().unwrap()).is_ok());
    assert!(Root::of("relative")
        .unwrap_err()
        .contains("not an absolute path"));
    let dotted = format!("{}/.", base.display());
    assert!(Root::of(&dotted).unwrap_err().contains("not canonical"));
    fs::write(base.join("file"), "x").unwrap();
    let file = base.join("file");
    assert!(Root::of(file.to_str().unwrap())
        .unwrap_err()
        .contains("not a directory"));
}

#[test]
fn a_read_outside_the_root_gives_no_bytes() {
    let base = scratch("outside");
    let root_path = base.join("repo");
    fs::create_dir_all(root_path.join("sub")).unwrap();
    fs::write(base.join("secret.json"), "{}").unwrap();
    fs::write(root_path.join("sub/in.json"), "{\"a\":1}").unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink(base.join("secret.json"), root_path.join("link.json")).unwrap();
    let root = Root::of(root_path.to_str().unwrap()).unwrap();
    assert_eq!(root.read("../secret.json", 100), Ok(None));
    assert_eq!(
        root.read(base.join("secret.json").to_str().unwrap(), 100),
        Ok(None)
    );
    #[cfg(unix)]
    assert_eq!(root.read("link.json", 100), Ok(None));
    assert_eq!(root.read("sub", 100), Ok(None));
    assert_eq!(
        root.read("sub/../sub/in.json", 100),
        Ok(Some(("sub/in.json".to_owned(), b"{\"a\":1}".to_vec())))
    );
    assert_eq!(
        root.read("sub/in.json", 3),
        Err(Over("sub/in.json".to_owned()))
    );
}

#[test]
fn the_survey_refuses_more_entries_than_the_budget() {
    let base = scratch("entries");
    for directory in 0..=(MAX_ENTRIES / 1000) {
        let path = base.join(format!("d{directory}"));
        fs::create_dir_all(&path).unwrap();
        for file in 0..1000 {
            fs::write(path.join(format!("f{file}.ts")), "").unwrap();
        }
    }
    let root = Root::of(base.to_str().unwrap()).unwrap();
    let started = std::time::Instant::now();
    let refusal = survey(&root).unwrap_err();
    assert!(refusal.contains("more than 100000 entries"), "{refusal}");
    assert!(started.elapsed().as_secs() < 30);
    let _ = fs::remove_dir_all(base);
}

#[test]
fn the_survey_refuses_a_deep_nest_and_follows_no_symlink_loop() {
    let base = scratch("deep");
    let mut path = base.clone();
    for _ in 0..=MAX_DEPTH {
        path = path.join("d");
    }
    fs::create_dir_all(&path).unwrap();
    let root = Root::of(base.to_str().unwrap()).unwrap();
    assert!(survey(&root).unwrap_err().contains("deeper than 256"));
    let looped = scratch("loop");
    fs::create_dir_all(looped.join("src")).unwrap();
    #[cfg(unix)]
    std::os::unix::fs::symlink("..", looped.join("src/up")).unwrap();
    let root = Root::of(looped.to_str().unwrap()).unwrap();
    assert_eq!(survey(&root), Ok(()));
}
