// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `rcrefcell`.

use std::cell::RefCell;
use std::rc::Rc;

pub fn make() -> Rc<RefCell<dyn crate::api::Tr>> {
    Rc::new(RefCell::new(crate::rcrefcell_b::X))
}
