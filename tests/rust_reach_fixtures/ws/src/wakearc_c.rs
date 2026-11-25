// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `wakearc`.

use std::sync::Arc;
use std::task::Waker;

pub fn make() -> Waker {
    Waker::from(Arc::new(crate::wakearc_b::X))
}
