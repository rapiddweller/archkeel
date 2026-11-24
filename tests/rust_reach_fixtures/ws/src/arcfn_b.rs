// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `arcfn`: the destructor of a value that a closure holds.

pub struct X;

impl Drop for X {
    fn drop(&mut self) {
        crate::api::hit(29);
    }
}
