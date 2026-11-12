// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Bounded work, including serialization scans and reserved string copies and comparisons.

use crate::work::Counter as WorkCounter;
use serde::Serialize;
use std::io::{self, Write};

const LIMIT: usize = 1 << 34;

pub(crate) enum Stop {
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

pub(crate) type Work = WorkCounter<LIMIT>;

impl From<crate::work::WorkLimit> for Stop {
    fn from(_: crate::work::WorkLimit) -> Self {
        Self::Work
    }
}

impl WorkCounter<LIMIT> {
    /// Reserve 64 scans for all copies and ordered-index comparisons of this text.
    /// The fixed ceiling bounds the number of ordered-index comparisons.
    pub(crate) fn text(&self, text: &str) -> Result<(), Stop> {
        self.charge(text.len().saturating_mul(64))
            .map_err(Stop::from)
    }

    /// Charge each serialized byte before the writer consumes it; never allocate a copy.
    pub(crate) fn input(&self, value: &impl Serialize) -> Result<(), Stop> {
        self.copies(value)?;
        self.limit_to((1usize << 20).saturating_add(self.spent().saturating_mul(128)))?;
        Ok(())
    }

    pub(crate) fn copies(&self, value: &impl Serialize) -> Result<(), Stop> {
        serde_json::to_writer(Counter(self), value).map_err(|_| Stop::Work)
    }
}

struct Counter<'a>(&'a Work);

impl Write for Counter<'_> {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.0
            .charge(bytes.len())
            .map_err(|_| io::Error::other("DeclarationWorkLimit"))?;
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}
