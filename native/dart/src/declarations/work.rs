// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded work, including serialization scans and reserved string copies and comparisons.

use serde::Serialize;
use std::cell::Cell;
use std::io::{self, Write};

const LIMIT: usize = 1 << 24;

pub(super) enum Stop {
    Work,
    Input,
}

impl Stop {
    pub(super) fn message(self) -> &'static str {
        match self {
            Self::Work => "DeclarationWorkLimit: Dart declaration assembly passes the work limit",
            Self::Input => {
                "DeclarationInputGap: Dart declaration inputs are inconsistent or incomplete"
            }
        }
    }
}

#[derive(Default)]
pub(super) struct Work(Cell<usize>);

impl Work {
    pub(super) fn charge(&self, amount: usize) -> Result<(), Stop> {
        let spent = self.0.get().saturating_add(amount);
        self.0.set(spent);
        if spent > LIMIT {
            Err(Stop::Work)
        } else {
            Ok(())
        }
    }

    pub(super) fn spent(&self) -> usize {
        self.0.get()
    }

    /// Reserve 64 scans for all copies and ordered-index comparisons of this text.
    /// The work limit holds fewer than 2^24 entries, so a key needs at most 24 comparisons.
    pub(super) fn text(&self, text: &str) -> Result<(), Stop> {
        self.charge(text.len().saturating_mul(64))
    }

    /// Charge each serialized byte before the writer consumes it; never allocate a copy.
    pub(super) fn value(&self, value: &impl Serialize) -> Result<(), Stop> {
        serde_json::to_writer(Counter(self, 1), value).map_err(|_| Stop::Work)
    }

    pub(super) fn copies(&self, value: &impl Serialize) -> Result<(), Stop> {
        serde_json::to_writer(Counter(self, 64), value).map_err(|_| Stop::Work)
    }
}

struct Counter<'a>(&'a Work, usize);

impl Write for Counter<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0
            .charge(bytes.len().saturating_mul(self.1))
            .map_err(|_| io::Error::other("DeclarationWorkLimit"))?;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
