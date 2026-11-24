// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `opaque`.

use crate::api::{self, Tr};

pub struct X;

impl Tr for X {
    fn hit(&self) {
        api::hit(8);
    }
}
