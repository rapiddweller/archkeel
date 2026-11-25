// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `wakearc`: it wakes a `Waker` that `std` made from an `Arc`.

pub fn run() {
    crate::wakearc_c::make().wake();
}
