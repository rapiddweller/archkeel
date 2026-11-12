// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The settings of the shell are bound to the reply by a check (AD-372, review of #1058).

use super::{Producer, Settings, STANDARD_LIBRARY_LIMIT, STANDARD_NAME_LIMIT};
use crate::reason::Refusal;

fn settings(namespace: &str, names: &[&str]) -> Settings {
    let names = names.iter().map(|name| (*name).to_owned()).collect();
    Settings::new(namespace.to_owned(), "p".to_owned(), names)
}

#[test]
fn a_profile_that_is_not_the_profile_of_the_reply_is_refused() {
    assert_eq!(settings("shop", &[]).check("p", &[]), Ok(()));
    assert_eq!(
        settings("shop", &[]).check("q", &[]),
        Err(Refusal::ProfileMismatch)
    );
}

#[test]
fn a_standard_library_with_a_duplicate_a_nul_or_too_many_names_is_refused() {
    assert_eq!(
        settings("shop", &["alpha", "beta"]).check("p", &["alpha", "beta"]),
        Ok(())
    );
    // Each name is in the pinned list here, so only the bounds refuse.
    let refused = |names: &[&str]| {
        matches!(
            settings("shop", names).check("p", names),
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

fn labels(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| (*item).to_owned()).collect()
}

#[test]
fn the_scan_roots_must_be_the_scope_labels_of_the_reply_in_their_order() {
    let rooted = |roots: &[&str]| settings("shop", &[]).with_roots(labels(roots));
    let scope = labels(&["src/**", "lib.rs"]);
    assert_eq!(rooted(&["src", "lib.rs"]).bind_roots(&scope), Ok(()));
    // A caller cannot widen a root, add one, drop one, reorder them or send an empty one.
    for wrong in [
        &["."][..],
        &[""][..],
        &["src"][..],
        &["src", "lib.rs", "extra"][..],
        &["lib.rs", "src"][..],
        &["src/**", "lib.rs"][..],
        &["sr", "lib.rs"][..],
    ] {
        assert_eq!(
            rooted(wrong).bind_roots(&scope),
            Err(Refusal::ScanRoots),
            "{wrong:?}"
        );
    }
    // Settings without roots bind nothing; a receipt that needs them names the part.
    assert_eq!(settings("shop", &[]).bind_roots(&scope), Ok(()));
    assert_eq!(settings("shop", &[]).roots(), None);
}

/// #1073 item 5, AD-388: a hostile request cannot widen the standard library by word. A name
/// outside the pinned list of the profile refuses the settings; a shorter list holds.
#[test]
fn a_standard_library_name_outside_the_pinned_list_is_refused() {
    let pinned = ["os", "sys"];
    assert_eq!(settings("shop", &["os"]).check("p", &pinned), Ok(()));
    assert_eq!(settings("shop", &[]).check("p", &pinned), Ok(()));
    assert!(matches!(
        settings("shop", &["os", "requests"]).check("p", &pinned),
        Err(Refusal::StandardLibrary(_))
    ));
}

/// #1073 item 5, AD-388: a hostile request cannot make the reply of another adapter trusted. The
/// claim of the shell holds only when the adapter of the reply is the collector of its profile;
/// a claim of an external producer stays external.
#[test]
fn a_trusted_claim_holds_only_for_the_collector_of_the_profile() {
    let claimed = settings("shop", &[]).with_producer(Producer::Trusted);
    assert_eq!(
        claimed.clone().bound("p", "p").producer(),
        Producer::Trusted
    );
    assert_eq!(claimed.bound("evil", "p").producer(), Producer::External);
    let external = settings("shop", &[]);
    assert_eq!(external.bound("p", "p").producer(), Producer::External);
}
