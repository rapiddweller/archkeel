// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the control `none`: nothing in `none_a` holds the type.

use crate::api::{self, Tr};

pub struct X;

impl Tr for X {
    fn hit(&self) {
        api::hit(11);
    }
}

    pub fn number() -> u32 {
        1
    }
