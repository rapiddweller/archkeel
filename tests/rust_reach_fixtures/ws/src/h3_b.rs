// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `h3`.

use crate::api::{self, Tr};

pub struct Y;

impl Tr for Y {
    fn hit(&self) {
        api::hit(3);
    }
}
