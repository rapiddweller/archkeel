// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use std::fs;
use std::path::Path;

/// The core finds its workers next to its own executable, and a test executable lives in `deps/`. `make
/// native-test` builds the workers and links them there; a plain `cargo test -p archkeel-core` does not, and
/// every scan test then fails with "No such file" (#2151). Build and link them once when they are missing.
pub(super) fn ensure() {
    static ONCE: std::sync::Once = std::sync::Once::new();
    ONCE.call_once(|| {
        let exe = std::env::current_exe().unwrap();
        let deps = exe.parent().unwrap();
        let profile = deps.parent().unwrap();
        let names = ["archkeel-rust-collector", "archkeel-typescript-collector"]
            .map(|name| format!("{name}{}", std::env::consts::EXE_SUFFIX));
        if names.iter().all(|name| deps.join(name).exists()) {
            return;
        }
        let mut build = std::process::Command::new("cargo");
        build.args(["build", "--locked", "-p", "archkeel-rust-collector"]);
        build.args(["-p", "archkeel-typescript-collector", "--target-dir"]);
        build.arg(profile.parent().unwrap());
        build.current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join(".."));
        if profile.file_name().is_some_and(|dir| dir == "release") {
            build.arg("--release");
        }
        assert!(
            build.status().unwrap().success(),
            "cargo build of the workers failed"
        );
        for name in &names {
            let _ = fs::remove_file(deps.join(name));
            #[cfg(unix)]
            std::os::unix::fs::symlink(profile.join(name), deps.join(name)).unwrap();
            #[cfg(not(unix))]
            fs::copy(profile.join(name), deps.join(name)).unwrap();
        }
    });
}
