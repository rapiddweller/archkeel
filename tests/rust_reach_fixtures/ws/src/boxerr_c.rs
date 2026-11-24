// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `boxerr`: `?` converts the error with `From` inside `std`.

pub fn make() -> Result<(), Box<dyn std::error::Error>> {
    Err(crate::boxerr_b::X)?;
    Ok(())
}
