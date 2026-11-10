// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the script dependencies. The expected sets are what `config.standard_globals` gives
// (`tests/test_collector_native_script_deps.py` compares them on options read from real configs).

use serde_json::json;

use super::*;
use crate::options::{ModuleKind, Options};

fn globals(options: &Options) -> HashSet<String> {
    standard_globals(options)
}

#[test]
fn the_default_libs_of_the_target_give_the_globals_of_the_browser_and_the_language() {
    let names = globals(&Options::default());
    assert!(["Array", "document", "window", "undefined"]
        .iter()
        .all(|name| names.contains(*name)));
    assert!(!names.contains("Promise.allSettled"));
}

#[test]
fn a_replaced_or_missing_lib_leaves_no_standard_global() {
    for options in [
        Options {
            no_lib: true,
            ..Options::default()
        },
        Options {
            lib_unmodeled: true,
            ..Options::default()
        },
        Options {
            unmodeled: vec!["rootDirs".into()],
            ..Options::default()
        },
    ] {
        assert!(globals(&options).is_empty());
    }
}

#[test]
fn the_target_and_the_module_choose_the_default_libs() {
    let old = globals(&Options {
        target: Some(Target::Es5),
        ..Options::default()
    });
    let new = globals(&Options {
        target: Some(Target::Es2022),
        ..Options::default()
    });
    assert!(new.contains("Map") && new.len() > old.len());
    let by_module = Options {
        module: Some(ModuleKind::NodeNext),
        ..Options::default()
    };
    assert_eq!(by_module.module_default_target(), Target::EsNext);
    let none = Options {
        target: Some(Target::Es3),
        ..Options::default()
    };
    assert_eq!(default_target(&none), Target::Es5);
}

#[test]
fn an_explicit_lib_list_replaces_the_default() {
    let options = Options {
        libs: Some(vec!["es5".into()]),
        ..Options::default()
    };
    let names = globals(&options);
    assert!(names.contains("Array") && !names.contains("document"));
}

#[test]
fn a_lib_value_is_lower_cased_deduplicated_and_checked_against_the_catalog() {
    let raw = json!({"lib": ["ES2020", "es2020", "DOM", "nonsense"]});
    let (found, unsupported) = libraries(raw.as_object().unwrap_or(&Map::new()));
    assert_eq!(found, Some(vec!["es2020".to_owned(), "dom".to_owned()]));
    assert!(unsupported);
    let (found, unsupported) = libraries(json!({"lib": "dom"}).as_object().unwrap_or(&Map::new()));
    assert_eq!((found, unsupported), (Some(Vec::new()), true));
    assert_eq!(libraries(&Map::new()), (None, false));
}
