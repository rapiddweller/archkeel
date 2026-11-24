// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The type of the case `fielddrop`: its destructor runs with its owner.

use crate::api;

pub struct D;

impl Drop for D {
    fn drop(&mut self) {
        api::hit(9);
    }
}
