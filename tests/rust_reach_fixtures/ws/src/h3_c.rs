// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The holder of the case `h3`: its associated type is the type that runs (hole H3).

use crate::api::Tr;
use crate::h3_b::Y;

pub struct W;

pub trait Holder {
    type Item: Tr;
    fn item(&self) -> Self::Item;
}

impl Holder for W {
    type Item = Y;
    fn item(&self) -> Y {
        Y
    }
}
