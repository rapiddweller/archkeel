// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `down`: a failed `downcast` hands the value back, and it is dropped.

pub fn run() {
    let value = crate::down_c::make();
    let _ = value.downcast::<u8>();
}
