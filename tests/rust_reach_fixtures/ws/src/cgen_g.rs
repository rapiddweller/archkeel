// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The generic code of the case `cgen`: it runs for the type that the closure passes on.

use crate::api::Tr;

pub fn inner<T: Tr + Default>() {
    T::default().hit();
}
