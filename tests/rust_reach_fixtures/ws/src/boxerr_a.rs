// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `boxerr`: it prints the error that `?` boxed.

pub fn run() {
    let error = crate::boxerr_c::make().unwrap_err();
    let _ = error.to_string();
}
