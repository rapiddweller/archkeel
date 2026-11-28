// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

use super::*;

#[test]
fn an_ini_value_reads_words_and_continuation_lines() {
    let text = "[pytest]\naddopts = -q\ntestpaths = tests_ce\n    docs/tests ./more/\n[other]\ntestpaths = no\n";
    assert_eq!(
        literal(&ini_value(text, "pytest")),
        vec!["tests_ce", "docs/tests", "more"]
    );
}

#[test]
fn a_glob_an_absolute_entry_and_a_parent_entry_name_no_path() {
    let entries: Vec<String> = ["tests/*", "/abs", "../up", "ok", ".", "a?b"]
        .iter()
        .map(|entry| (*entry).to_owned())
        .collect();
    assert_eq!(literal(&entries), vec!["ok"]);
}

#[test]
fn a_conftest_and_a_testpath_are_test_source_outside_the_roots() {
    let paths = vec!["tests_ce".to_owned()];
    assert!(is_outside_test_source("tests_ce/helpers.py", &paths));
    assert!(is_outside_test_source("elsewhere/conftest.py", &paths));
    assert!(is_outside_test_source("tests/a.py", &paths));
    assert!(!is_outside_test_source("tests_ce_other/a.py", &paths));
    assert!(!is_outside_test_source("scripts/patch.py", &paths));
}

#[test]
fn a_section_is_found_by_its_exact_header() {
    assert!(has_section("[tool:pytest]\nx=1\n", "tool:pytest"));
    assert!(!has_section("[tool:pytester]\n", "tool:pytest"));
}
