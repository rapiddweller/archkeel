// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `iter`: it runs an iterator adaptor over boxed values.

use crate::api::Tr;

pub fn run() {
    let _ = crate::iter_c::items().map(|value| value.hit()).count();
}
