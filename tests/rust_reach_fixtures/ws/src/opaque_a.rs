// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `opaque`: it holds the opaque type.

use crate::api::Tr;

pub fn run() {
    crate::opaque_c::make().hit();
}
