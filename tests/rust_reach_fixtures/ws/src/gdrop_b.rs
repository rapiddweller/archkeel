// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `gdrop`: its method runs from the guard.

use crate::api::{self, Tr};

pub struct D;

impl Tr for D {
    fn hit(&self) {
        api::hit(71);
    }
}
