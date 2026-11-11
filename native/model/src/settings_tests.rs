// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The settings of the shell are bound to the reply by a check (AD-372, review of #1058).

use super::{Settings, STANDARD_LIBRARY_LIMIT, STANDARD_NAME_LIMIT};
use crate::reason::Refusal;

fn settings(namespace: &str, names: &[&str]) -> Settings {
    let names = names.iter().map(|name| (*name).to_owned()).collect();
    Settings::new(namespace.to_owned(), "p".to_owned(), names)
}

#[test]
fn a_profile_that_is_not_the_profile_of_the_reply_is_refused() {
    assert_eq!(settings("shop", &[]).check("p"), Ok(()));
    assert_eq!(
        settings("shop", &[]).check("q"),
        Err(Refusal::ProfileMismatch)
    );
}

#[test]
fn a_standard_library_with_a_duplicate_a_nul_or_too_many_names_is_refused() {
    assert_eq!(settings("shop", &["alpha", "beta"]).check("p"), Ok(()));
    let refused = |names: &[&str]| {
        matches!(
            settings("shop", names).check("p"),
            Err(Refusal::StandardLibrary(_))
        )
    };
    assert!(refused(&["alpha", "beta", "alpha"]));
    assert!(refused(&["al\0pha"]));
    assert!(refused(&[""]));
    let long = "a".repeat(STANDARD_NAME_LIMIT + 1);
    assert!(refused(&[long.as_str()]));
    let many: Vec<String> = (0..=STANDARD_LIBRARY_LIMIT)
        .map(|n| format!("n{n}"))
        .collect();
    let many: Vec<&str> = many.iter().map(String::as_str).collect();
    assert!(refused(&many));
    assert!(!refused(&many[..STANDARD_LIBRARY_LIMIT]));
}

#[test]
fn a_module_outside_the_namespace_is_refused_as_the_reference_engine_refuses_it() {
    let admits = |namespace: &str, module: &str, package: &str| {
        settings(namespace, &[]).admits(module, package).is_ok()
    };
    assert!(admits("shop", "shop.src.a", "shop.src"));
    // A package above the namespace holds a module inside it.
    assert!(admits("shop.src", "shop.src.a", "shop"));
    assert!(!admits("", "shop.src.a", "shop.src"));
    assert!(!admits("nothing", "shop.src.a", "shop.src"));
    assert!(!admits("sho", "shop.src.a", "shop.src"));
    assert!(!admits("shop", "shop.src.a", "shop.other"));
}
