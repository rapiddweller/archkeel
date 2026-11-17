// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

// Consumer: the one validation of the store (AD-450). The planted claims of a real survey and the
// registered sets of its validation table (AD-688) are in `native/collect/src/python_tests.rs`,
// which links the collector and the store.

use super::*;

#[test]
fn the_first_part_names_the_package() {
    assert_eq!(first_part("os.path"), "os");
    assert_eq!(first_part("app"), "app");
}
