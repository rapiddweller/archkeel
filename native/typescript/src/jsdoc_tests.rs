// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::types_directive;

#[test]
fn a_types_directive_with_a_plain_name_gives_the_name() {
    assert_eq!(
        types_directive(r#"/// <reference types="vite/client" />"#).as_deref(),
        Some("vite/client")
    );
    assert_eq!(
        types_directive("///<reference types='@scope/pkg'/>").as_deref(),
        Some("@scope/pkg")
    );
    assert_eq!(
        types_directive(r#"/// <REFERENCE TYPES="a" />"#).as_deref(),
        Some("a")
    );
}

#[test]
fn another_form_gives_no_name() {
    for text in [
        r#"/// <reference path="a.d.ts" />"#,
        r#"/// <reference lib="es2020" />"#,
        r#"/// <reference types="a" resolution-mode="import" />"#,
        r#"/// <reference types="a" lib="b" />"#,
        r#"/// <reference types="./a" />"#,
        r#"/// <reference types="/a" />"#,
        r#"/// <reference types="a b" />"#,
        r#"/// <reference types="a\b" />"#,
        r#"/// <reference types="" />"#,
        r#"/// <amd-dependency types="a" />"#,
        r#"// <reference types="a" />"#,
        r#"/* /// <reference types="a" /> */"#,
        r#"/// <referencetypes="a" />"#,
    ] {
        assert_eq!(types_directive(text), None, "{text}");
    }
}
