// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::quoted_after;

const IMPORTS: [&str; 3] = ["from", "import", "require"];

#[test]
fn a_repaired_file_gives_each_quoted_specifier() {
    let text = "import a from './a';\nexport * from \"../b\";\nimport './c';\n\
                const d = import('./d');\nconst e = require( '../../src/e' );\n";
    let mut found = quoted_after(text, &IMPORTS);
    found.sort();
    assert_eq!(found, ["../../src/e", "../b", "./a", "./c", "./d"]);
}

#[test]
fn a_member_or_a_longer_name_is_no_keyword() {
    let text = "x.import('./a');\nimported('./b');\nconst fromage = 'c';\nre.require('./d');\n";
    assert!(quoted_after(text, &IMPORTS).is_empty());
}

#[test]
fn a_path_directive_and_an_augmentation_give_their_name() {
    let text = "/// <reference path=\"global.d.ts\" />\ndeclare module '../../src/b' {}\n";
    assert_eq!(quoted_after(text, &["path="]), ["global.d.ts"]);
    assert_eq!(quoted_after(text, &["module"]), ["../../src/b"]);
}
