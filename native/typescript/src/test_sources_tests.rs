// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the host refuses a 9.0.0 reply that selects a test source. Each row was printed by
// `is_test_source(path, Language.TYPESCRIPT)` of `ir/profiles.py` (AD-313).

use super::*;

#[test]
fn test_sources_are_the_ones_python_recognizes() {
    let cases = [
        ("src/a.test.ts", true),
        ("src/a.spec.tsx", true),
        ("src/tests/a.ts", true),
        ("src/__tests__/a.ts", true),
        ("test/a.ts", true),
        ("src/latest.ts", false),
        ("src/test.ts", false),
        ("src/a.test.", false),
        ("src/a.test.d.ts", false),
        ("src/contest/a.ts", false),
        ("tests", false),
        ("src/a.testx.ts", false),
        ("src/.test.ts", true),
        ("src/a.spec.ts.map", false),
    ];
    for (path, expected) in cases {
        assert_eq!(is_test_source(path), expected, "{path}");
    }
}
