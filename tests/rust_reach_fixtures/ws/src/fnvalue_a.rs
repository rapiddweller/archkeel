// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The generic code of the case `fnvalue`: it runs for the type that a function value fixes.

use crate::api::Tr;

pub fn call_hit<T: Tr + Default>() {
    T::default().hit();
}
