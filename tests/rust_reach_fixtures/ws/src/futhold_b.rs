// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `futhold`.

pub struct X;

impl Drop for X {
    fn drop(&mut self) {
        crate::api::hit(61);
    }
}
