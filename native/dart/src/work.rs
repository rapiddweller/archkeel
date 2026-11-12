// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared count of bounded record work. Each layer names its own stop and limit.

use std::cell::Cell;

#[derive(Default)]
pub(crate) struct Counter<const LIMIT: usize>(Cell<usize>);

pub(crate) struct WorkLimit;

impl<const LIMIT: usize> Counter<LIMIT> {
    pub(crate) fn charge(&self, amount: usize) -> Result<(), WorkLimit> {
        let spent = self.0.get().saturating_add(amount);
        self.0.set(spent);
        if spent > LIMIT {
            Err(WorkLimit)
        } else {
            Ok(())
        }
    }

    pub(crate) fn spent(&self) -> usize {
        self.0.get()
    }
}
