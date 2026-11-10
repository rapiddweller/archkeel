// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the declared-dependency edge. The text is a real `Cargo.toml` shape.

use super::*;

#[test]
fn the_line_of_a_dependency_is_its_key_its_table_header_or_the_first_line() {
    let text = "[package]\nname = \"a\"\n[dependencies]\nfirst = \"1\"\n  second.workspace = true\n\
                [dev_dependencies.third]\nversion = \"1\"\n[build-dependencies]\n\"quoted\" = \"1\"\n";
    let index = LineIndex::new(text);
    assert_eq!(index.find(Kind::Normal, "first").0, 4);
    assert_eq!(index.find(Kind::Normal, "second").0, 5);
    assert_eq!(index.find(Kind::Dev, "third").0, 6);
    assert_eq!(index.find(Kind::Build, "quoted").0, 9);
    // A key of another section, and a key that is not there, give the first line.
    assert_eq!(index.find(Kind::Dev, "first"), (1, "[package]".to_owned()));
}

#[test]
fn a_target_table_and_a_table_header_win_over_a_key_line() {
    let text =
        "[target.'cfg(unix)'.dependencies]\na = \"1\"\n[dependencies.\"b-c\"]\nversion = \"1\"\n";
    let index = LineIndex::new(text);
    assert_eq!(index.find(Kind::Normal, "a").0, 2);
    assert_eq!(index.find(Kind::Normal, "b-c").0, 3);
}
