// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `blanket`: its method runs through the associated type of a blanket impl.

use crate::api::{self, Tr};

pub struct Y;

impl Tr for Y {
    fn hit(&self) {
        api::hit(73);
    }
}
