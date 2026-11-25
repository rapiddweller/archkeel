// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `upcast` that upcasts to the super trait.

use crate::api::{Sub, Tr};

pub fn get() -> &'static dyn Tr {
    let sub: &'static dyn Sub = crate::upcast_m::make();
    sub
}
