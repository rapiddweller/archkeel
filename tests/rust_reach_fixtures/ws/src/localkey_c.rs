// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The thread local of the case `localkey`.

use std::cell::RefCell;

thread_local! {
    pub static KEY: RefCell<Option<Box<dyn std::any::Any>>> = RefCell::new(Some(Box::new(crate::localkey_b::X)));
}
