// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The maker of the case `send`.

pub fn make() -> Box<dyn Send> {
    regdep::keep_send(crate::send_b::X)
}
