// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `feach`: `for_each` of `std` calls through `dyn Tr`, which module `c` coerced.

use crate::api::Tr;

pub fn run() {
    crate::feach_c::make().iter().for_each(|value| value.hit());
}
