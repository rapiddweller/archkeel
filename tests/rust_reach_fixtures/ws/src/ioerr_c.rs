// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `ioerr`: it hands the error to `io::Error::other`.

pub fn fail() -> std::io::Error {
    std::io::Error::other(crate::ioerr_b::X)
}
