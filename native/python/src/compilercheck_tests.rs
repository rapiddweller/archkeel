// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

#[test]
fn a_compiler_refusal_never_reaches_the_tree_consumer() {
    for source in [
        "x = *a",
        "f(a=1, a=2)",
        "((a) := 1)",
        "try: pass\nexcept: pass\nexcept E: pass",
        "type X = (y := 1)",
    ] {
        assert!(
            crate::parse::parse(source, crate::test_minor(14)).is_err(),
            "{source}"
        );
    }
}
