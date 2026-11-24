// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The module of the case `upcast` that makes a `dyn Sub`.

use crate::api::Sub;

pub fn make() -> &'static dyn Sub {
    &crate::upcast_b::X_VALUE
}
