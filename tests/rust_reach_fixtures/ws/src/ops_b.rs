// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The impl of the case `ops`: the operator.

pub struct X;

impl std::ops::Add for X {
    type Output = X;
    fn add(self, _other: X) -> X {
        crate::api::hit(34);
        X
    }
}
