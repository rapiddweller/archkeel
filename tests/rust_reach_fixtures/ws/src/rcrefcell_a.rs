// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The code of the case `rcrefcell`: it calls through `Rc<RefCell<dyn Tr>>`.

use crate::api::Tr;

pub fn run() {
    let shared = crate::rcrefcell_c::make();
    shared.borrow().hit();
}
