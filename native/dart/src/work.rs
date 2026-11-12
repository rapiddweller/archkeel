// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shared count of bounded record work. Each layer names its own stop and limit.

use std::cell::Cell;

pub(crate) struct Counter<const LIMIT: usize> {
    spent: Cell<usize>,
    limit: Cell<usize>,
}

impl<const LIMIT: usize> Default for Counter<LIMIT> {
    fn default() -> Self {
        Self {
            spent: Cell::new(0),
            limit: Cell::new(LIMIT),
        }
    }
}

pub(crate) struct WorkLimit;

impl<const LIMIT: usize> Counter<LIMIT> {
    pub(crate) fn charge(&self, amount: usize) -> Result<(), WorkLimit> {
        let spent = self.spent.get().saturating_add(amount);
        self.spent.set(spent);
        if spent > self.limit.get() {
            Err(WorkLimit)
        } else {
            Ok(())
        }
    }

    pub(crate) fn spent(&self) -> usize {
        self.spent.get()
    }

    pub(crate) fn limit_to(&self, limit: usize) -> Result<(), WorkLimit> {
        self.limit.set(limit.min(LIMIT));
        self.charge(0)
    }
}
