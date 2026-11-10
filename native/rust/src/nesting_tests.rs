// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the walk of the module tree. Each case is a text that the check must read right.

use super::*;

fn nested(open: &str, close: &str, depth: usize) -> String {
    format!(
        "fn f() {{ let x = {}1{}; }}",
        open.repeat(depth),
        close.repeat(depth)
    )
}

#[test]
fn a_depth_at_the_limit_passes_and_one_more_is_too_deep() {
    assert!(!too_deep(&nested("(", ")", MAX_NESTING - 2)));
    assert!(too_deep(&nested("(", ")", MAX_NESTING)));
    assert!(too_deep(&format!(
        "{}{}",
        "mod a {".repeat(MAX_NESTING + 1),
        "}".repeat(MAX_NESTING + 1)
    )));
}

#[test]
fn brackets_in_comments_strings_and_characters_do_not_count() {
    let noise = "(".repeat(MAX_NESTING + 5);
    for text in [
        format!("// {noise}\nfn f() {{}}"),
        format!("/* {noise} /* {noise} */ {noise} */ fn f() {{}}"),
        format!("fn f() {{ let s = \"{noise} \\\" {noise}\"; }}"),
        format!("fn f() {{ let s = r#\"{noise} \" {noise}\"#; }}"),
        format!("fn f() {{ let c = '('; let d = '\\''; let e = b'['; fn g<'a>(x: &'a str) {{}} }} // {noise}"),
    ] {
        assert!(!too_deep(&text), "{}", &text[..40]);
    }
}

#[test]
fn closing_brackets_lower_the_depth_again() {
    let text = nested("(", ")", MAX_NESTING - 2).repeat(10);
    assert!(!too_deep(&text));
}
