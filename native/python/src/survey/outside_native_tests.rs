// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the outside writer search (#1522). A dotted word reaches the module that is its
// longest prefix, each module below it and each package above it.

use std::collections::HashSet;

use super::reached;

#[test]
fn a_word_reaches_its_module_the_modules_below_and_the_packages_above() {
    let names: HashSet<String> = ["app", "app.lib", "app.lib.pub", "app.other"]
        .iter()
        .map(ToString::to_string)
        .collect();
    let mut found = reached("app.lib.value", &names);
    found.sort();
    assert_eq!(found, ["app", "app.lib", "app.lib.pub"]);
    assert!(reached("apple.lib", &names).is_empty());
}
