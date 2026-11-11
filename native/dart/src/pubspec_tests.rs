// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the package identity and the SDK gaps of the Dart reply. The expected values come
// from `analyzer/dart/snapshot._pubspec_metadata` of the Python collector.

use super::*;

fn check(text: &str, name: Option<&str>, sdk: Option<&str>, state: SdkState) {
    let found = read(text.as_bytes());
    let expected = Pubspec {
        name: name.map(str::to_owned),
        sdk: sdk.map(str::to_owned),
        state,
    };
    assert_eq!(found, expected, "{text:?}");
}

#[test]
fn a_declared_constraint_is_read_with_its_quotes_and_comments_removed() {
    let range = Some(">=3.0.0 <4.0.0");
    check(
        "name: shop\nenvironment:\n  sdk: '>=3.0.0 <4.0.0'\n",
        Some("shop"),
        range,
        SdkState::Declared,
    );
    let text = "name: 'shop' # c\nenvironment:\n  sdk: ^3.2.0 # pinned\n";
    check(text, Some("shop"), Some("^3.2.0"), SdkState::Declared);
    let text = "name: shop\nenvironment:\n  sdk: \"^3.0.0\"\ndependencies:\n  sdk: x\n";
    check(text, Some("shop"), Some("^3.0.0"), SdkState::Declared);
    let text = "# c\n\n  \nname:   \"shop\"  \nenvironment:\n  sdk: ^3.0.0 #x\n";
    check(text, Some("shop"), Some("^3.0.0"), SdkState::Declared);
    let text = "name: shop\renvironment:\r  sdk: ^3.0.0\r";
    check(text, Some("shop"), Some("^3.0.0"), SdkState::Declared);
    // Only ` #` starts a comment in the constraint.
    let text = "name: shop\nenvironment:\n  sdk: ^3.0.0#x\n";
    check(text, Some("shop"), Some("^3.0.0#x"), SdkState::Declared);
}

#[test]
fn the_package_name_needs_one_valid_name_line() {
    check("name: shop\n", Some("shop"), None, SdkState::Missing);
    check("name: shop#x\n", Some("shop"), None, SdkState::Missing);
    check("name: shop\nname: other\n", None, None, SdkState::Missing);
    check("name: 9bad\n", None, None, SdkState::Missing);
    // A byte order mark is part of the first line, so the line is not a name line.
    check("\u{feff}name: shop\n", None, None, SdkState::Missing);
}

#[test]
fn an_unreadable_constraint_is_invalid_and_has_no_value() {
    let cases = [
        "name: shop\nenvironment: {sdk: ^3.0.0}\n",
        "name: shop\nenvironment:\n  sdk: ^3.0.0\n  sdk: ^3.1.0\n",
        "name: shop\nenvironment:\n  flutter: '>=3.0.0'\n   sdk: ^3.0.0\n",
        "name: shop\nenvironment:\n\tsdk: ^3.0.0\n",
        "name: shop\nenvironment:\n  sdk: '*'\n",
        "name: shop\nenvironment:\n  sdk:\n",
        "name: shop\nenvironment:\nenvironment:\n  sdk: ^3.0.0\n",
    ];
    for text in cases {
        check(text, Some("shop"), None, SdkState::Invalid);
    }
    assert_eq!(
        read(b"\xff"),
        Pubspec {
            name: None,
            sdk: None,
            state: SdkState::Invalid
        }
    );
}
