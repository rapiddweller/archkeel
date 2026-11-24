// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the control `dyn`: the type is never coerced to `dyn Tr`.

use crate::api::{self, Tr};

pub struct X;

impl Tr for X {
    fn hit(&self) {
        api::hit(12);
    }
}
