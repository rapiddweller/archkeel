// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `h3`: generic, it names neither the holder nor the item.

use crate::api::Tr;
use crate::h3_c::Holder;

pub fn run<H: Holder>(holder: &H) {
    holder.item().hit();
}
