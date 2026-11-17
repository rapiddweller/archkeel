// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The keys of a `pubspec.yaml` that the package survey reads (AD-454, AD-500).

use super::keys;

fn words(text: &str) -> (bool, bool, bool) {
    let found = keys(text);
    (found.workspace, found.path, found.escape)
}

#[test]
fn each_yaml_form_of_a_key_is_a_word_and_an_escape_is_a_gap() {
    for text in [
        "a:\n  b:\n    path: x",
        "a: {\"b\": {\"path\": x}}",
        "a:\n  'path': x",
        "a:\n  ? path\n  : x",
        "a:\n  ? \"path\"\n  : x",
        "a: {b: {path : x}}",
    ] {
        assert_eq!(words(text), (false, true, false), "{text}");
    }
    assert_eq!(words("\"workspace\":\n  - x"), (true, false, false));
    assert_eq!(words("'resolution': workspace"), (true, false, false));
    // The key alone is a gap: the value need not be the word `workspace`.
    assert_eq!(words("\"resolution\": x"), (true, false, false));
    assert_eq!(words("a:\n  \"pa\\x74h\": x"), (false, false, true));
}

#[test]
fn a_comment_line_and_a_longer_word_are_no_key() {
    assert_eq!(words("  # path: x\nclasspath: x"), (false, false, false));
    assert_eq!(words("description: a pathway"), (false, false, false));
    assert_eq!(words("name: x # path"), (false, false, false));
}

#[test]
fn path_in_package_metadata_is_not_a_dependency_key() {
    assert_eq!(
        words("name: path\ndescription: A path library\nrepository: https://example.org/path\n"),
        (false, false, false)
    );
}

#[test]
fn a_hosted_dependency_named_path_is_not_a_path_dependency() {
    assert_eq!(
        words("name: shop\ndependencies:\n  path: ^1.9.0\n"),
        (false, false, false)
    );
    assert!(keys("name: shop\ndependencies:\n  path:\n    path: ../local\n").path);
}

#[test]
fn path_keys_and_unreadable_yaml_keep_a_gap() {
    for text in [
        "dependencies:\n  other:\n    path: ../other\n",
        "dependency_overrides: {other: {path: ../other}}",
        "dependencies:\n  other:\n    'path': ../other",
        "dependencies:\n  other:\n    \"pa\\x74h\": ../other",
        "name: path\nname: other\n",
        "name: path\nx: [\n",
        "name: path\nx: &a {path: ../other}\ny: *a\n",
    ] {
        let found = keys(text);
        assert!(found.path || found.escape, "{text:?}: {found:?}");
    }
}
