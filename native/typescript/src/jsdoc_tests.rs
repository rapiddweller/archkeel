// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::types_directive;

#[test]
fn a_types_directive_gives_the_name_and_the_mode() {
    let name = |text: &str| types_directive(text);
    assert_eq!(
        name(r#"/// <reference types="vite/client" />"#),
        Some(("vite/client".to_owned(), false))
    );
    assert_eq!(
        name("///<reference types='@scope/pkg'/>"),
        Some(("@scope/pkg".to_owned(), false))
    );
    assert_eq!(
        name(r#"/// <REFERENCE TYPES="a" />"#),
        Some(("a".to_owned(), false))
    );
    assert_eq!(
        name(r#"/// <reference types="a" resolution-mode="import" />"#),
        Some(("a".to_owned(), true))
    );
    assert_eq!(
        name(r#"/// <reference types="a" lib="b" />"#),
        Some(("a".to_owned(), false))
    );
    // A name to prove, though it can never resolve.
    assert_eq!(
        name(r#"/// <reference types="a b" />"#),
        Some(("a b".to_owned(), false))
    );
    assert_eq!(
        name(r#"/// <reference types="" />"#),
        Some((String::new(), false))
    );
}

#[test]
fn another_form_gives_no_name() {
    for text in [
        r#"/// <reference path="a.d.ts" />"#,
        r#"/// <reference lib="es2020" />"#,
        r#"/// <reference types="./a" />"#,
        r#"/// <reference types="/a" />"#,
        r#"/// <reference types="a" no-default-lib="true" />"#,
        r#"/// <amd-dependency types="a" />"#,
        r#"// <reference types="a" />"#,
        r#"/* /// <reference types="a" /> */"#,
        r#"/// <referencetypes="a" />"#,
    ] {
        assert_eq!(types_directive(text), None, "{text}");
    }
}
