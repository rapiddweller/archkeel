// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `boxerr`.

pub struct X;

impl std::fmt::Display for X {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        crate::api::hit(27);
        f.write_str("x")
    }
}
impl std::error::Error for X {}
impl std::fmt::Debug for X {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("x")
    }
}
