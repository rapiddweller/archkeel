// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `foreach`: `sort_by` of `std` calls the methods of boxed values.

use crate::api::Tr;

pub fn run() {
    let mut values = crate::foreach_c::make();
    values.sort_by(|left, right| {
        left.hit();
        right.hit();
        std::cmp::Ordering::Equal
    });
}
