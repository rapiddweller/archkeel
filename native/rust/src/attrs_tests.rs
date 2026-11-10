// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the scan of `mod` and `use` items. One fixture for each reason of UNKNOWN.

use super::*;

fn attrs(text: &str) -> Vec<Attribute> {
    let item: syn::ItemMod = syn::parse_str(&format!("{text}\nmod m;")).unwrap();
    item.attrs
}

fn hidden(text: &str, what: &str) -> Option<String> {
    let features = BTreeSet::from(["dump".to_owned()]);
    hidden_by(&attrs(text), what, &features)
}

#[test]
fn cfg_test_and_a_declared_feature_are_read() {
    assert_eq!(hidden("#[cfg(test)]", "module"), None);
    assert_eq!(hidden("#[cfg(feature = \"dump\")]", "use"), None);
    // `any` and `all` of conditions that the scan knows.
    assert_eq!(hidden("#[cfg(any(test, feature = \"dump\"))]", "use"), None);
    assert_eq!(
        hidden("#[cfg(all(test, feature = \"dump\"))]", "module"),
        None
    );
    assert!(hidden("#[cfg(any(test, unix))]", "use").is_some());
    assert!(hidden("#[cfg(any(test, feature = \"other\"))]", "use").is_some());
    assert!(hidden("#[cfg(any())]", "use").is_some());
    assert!(hidden("#[cfg(any(not(test)))]", "use").is_some());
}

#[test]
fn another_cfg_gates_the_item() {
    for text in [
        "#[cfg(unix)]",
        "#[cfg(feature = \"other\")]",
        "#[cfg(not(test))]",
        "#[cfg(all(test, unix))]",
    ] {
        let reason = hidden(text, "module").unwrap();
        assert!(
            reason.starts_with("A cfg condition gates a module: cfg("),
            "{reason}"
        );
    }
}

#[test]
fn a_cfg_attr_with_a_lint_changes_nothing_and_any_other_may_add_a_path() {
    assert_eq!(
        hidden("#[cfg_attr(unix, allow(dead_code))]", "module"),
        None
    );
    let reason = hidden("#[cfg_attr(unix, path = \"x.rs\")]", "module").unwrap();
    assert!(reason.starts_with("A cfg_attr gates a module"), "{reason}");
    assert!(hidden("#[cfg_attr(unix, path = \"x.rs\")]", "use").is_some());
}

#[test]
fn an_attribute_macro_on_a_module_hides_its_content() {
    assert_eq!(
        hidden("#[tool::rewrite]", "module").unwrap(),
        "An attribute macro is applied to a module: a path attribute"
    );
    assert_eq!(
        hidden("#[tool::rewrite_a]", "module").unwrap(),
        "An attribute macro is applied to a module: a path attribute"
    );
    for text in [
        // `macro_use` only widens the scope of the macros of the module.
        "#[macro_use]",
        "#[path = \"x.rs\"]",
        "#[allow(dead_code)]",
        "#[clippy::x]",
        "/// doc",
    ] {
        assert_eq!(hidden(text, "module"), None, "{text}");
    }
}

#[test]
fn a_path_attribute_needs_a_string_literal() {
    assert_eq!(
        path_literal(&attrs("#[path = \"a/b.rs\"]")),
        Ok(Some("a/b.rs".to_owned()))
    );
    assert_eq!(path_literal(&attrs("#[allow(x)]")), Ok(None));
    assert_eq!(
        path_literal(&attrs("#[path = concat!(\"a\", \".rs\")]")),
        Err("A path attribute is not a string literal".to_owned())
    );
}
