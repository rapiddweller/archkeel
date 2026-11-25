// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The other implementer of the control `dyn`: it is the type that is coerced.

use crate::api::{self, Tr};

pub struct Z;

impl Tr for Z {
    fn hit(&self) {
        api::hit(15);
    }
}
