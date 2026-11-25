// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `closure`: its destructor runs when the closure drops it.

use crate::api;

pub struct D;

impl Drop for D {
    fn drop(&mut self) {
        api::hit(10);
    }
}
