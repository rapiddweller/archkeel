// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A generic function that casts a type parameter to `dyn Tr` (hole H1). It calls nothing outside the workspace.

use crate::api::Tr;

pub fn erase<T: Tr + Sync + 'static>(value: &'static T) -> &'static dyn Tr {
    value as &dyn Tr
}
