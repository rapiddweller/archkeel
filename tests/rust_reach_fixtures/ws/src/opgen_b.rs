// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `opgen`: its method runs from the generic function.

use crate::api::{self, Tr};

pub struct X;

impl Tr for X {
    fn hit(&self) {
        api::hit(69);
    }
}
