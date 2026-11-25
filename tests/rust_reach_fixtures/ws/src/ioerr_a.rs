// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `ioerr`: it prints an `io::Error` whose payload dispatches into `b`.

pub fn run() -> usize {
    let error = crate::ioerr_c::fail();
    error.to_string().len()
}
