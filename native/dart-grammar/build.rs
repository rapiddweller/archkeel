// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Compile the vendored C parser of tree-sitter-dart 0.1.0 (AD-342).
//!
//! The flags are the flags of the `setup.py` of the Python wheel, so both builds compile the same
//! C with the same language standard.

fn main() {
    let source = std::path::Path::new("vendor").join("src");
    let mut build = cc::Build::new();
    build
        .include(&source)
        .flag_if_supported("-std=c11")
        .flag_if_supported("/std:c11")
        .flag_if_supported("/utf-8")
        // The generated parser and the scanner are vendored as is: their warnings are not ours.
        .warnings(false);
    for name in ["parser.c", "scanner.c"] {
        build.file(source.join(name));
    }
    // Cargo watches each file below a directory path, so the headers are covered too.
    println!("cargo:rerun-if-changed={}", source.display());
    build.compile("tree-sitter-dart");
}
