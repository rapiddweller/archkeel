// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `rcrefcell`.

pub struct X;

impl crate::api::Tr for X {
    fn hit(&self) {
        crate::api::hit(28);
    }
}
