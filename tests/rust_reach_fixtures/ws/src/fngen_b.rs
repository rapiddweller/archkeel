// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `fngen`: its destructor runs when a closure that holds it drops.

use crate::api;

pub struct D;

impl Drop for D {
    fn drop(&mut self) {
        api::hit(77);
    }
}
