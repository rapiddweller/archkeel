// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `deref`.

pub struct X;

impl crate::api::Tr for X {
    fn hit(&self) {
        crate::api::hit(35);
    }
}
