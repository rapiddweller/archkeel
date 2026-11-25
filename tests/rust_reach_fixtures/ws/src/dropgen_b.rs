// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `dropgen`: it runs when the guard drops it.

use crate::api::{self, Tr};

pub struct D;

impl Tr for D {
    fn hit(&self) {
        api::hit(5);
    }
}
