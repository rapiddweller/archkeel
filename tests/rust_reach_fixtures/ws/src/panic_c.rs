// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `panic`: `panic_any` boxes the payload inside `std`.

pub fn boom() {
    std::panic::panic_any(crate::panic_b::X)
}
