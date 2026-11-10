// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host refuses a reply that selects a file in a test directory.

use super::*;

#[test]
fn a_test_bench_or_example_directory_is_test_scope() {
    for rel in [
        "a/tests/it.rs",
        "tests/common/mod.rs",
        "x/benches/b.rs",
        "examples/e.rs",
        "src/__tests__/m.rs",
        "./test/m.rs",
    ] {
        assert!(in_test_directory(rel), "{rel}");
    }
}

#[test]
fn a_file_name_alone_is_no_test_scope() {
    for rel in [
        "src/lib.rs",
        "src/walk_tests.rs",
        "src/tests.rs",
        "tests",
        "a/examples",
    ] {
        assert!(!in_test_directory(rel), "{rel}");
    }
}
