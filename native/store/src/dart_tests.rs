// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT
// Consumer: the one validation of the store (AD-468). The planted claims of a real survey are in
// `native/collect/src/dart_tests.rs`, which links the collector and the store.

use super::*;

#[test]
fn the_first_part_names_the_namespace_of_a_module() {
    assert_eq!(first_part("shop.data.repo"), "shop");
    assert_eq!(first_part("shop"), "shop");
}
