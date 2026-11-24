// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module that erases the type in the case `h1`.

use crate::api::Tr;

pub fn get() -> &'static dyn Tr {
    crate::h1_g::erase(&crate::h1_b::X_VALUE)
}
