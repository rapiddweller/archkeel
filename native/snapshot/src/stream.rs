// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! A read of a file of any size in parts (#1522, AD-770).
//!
//! A collector that only searches a file for words, and does not parse it, need not hold it in
//! memory: a C source of a parser table can be larger than `MAX_FILE_BYTES`. The file is digested
//! as it is read, so it is an input of the scan like a file that `read` gives.

use std::fs::File;
use std::io::Read;

use sha2::{Digest, Sha256};

use super::Snapshot;

/// The bytes of one part.
const PART: usize = 1 << 16;

impl Snapshot {
    /// Read the regular file `rel` in parts, in order, and digest it. `each` gets each part.
    ///
    /// `false` when the file is absent or not a regular file, or when a read fails: a failed read
    /// is a problem. The file keeps the input role that it has, else it is a resolution input.
    pub fn read_parts(&mut self, rel: &str, each: &mut dyn FnMut(&[u8])) -> bool {
        if !self.is_file(rel) {
            return false;
        }
        let Ok(mut file) = File::open(self.absolute(rel)) else {
            self.problems
                .insert(format!("Unreadable resolver input: {rel}"));
            return false;
        };
        let mut digest = Sha256::new();
        let mut buffer = vec![0_u8; PART];
        loop {
            match file.read(&mut buffer) {
                Ok(0) => break,
                Ok(count) => {
                    digest.update(&buffer[..count]);
                    each(&buffer[..count]);
                }
                Err(_) => {
                    self.problems
                        .insert(format!("Unreadable resolver input: {rel}"));
                    return false;
                }
            }
        }
        let selected = self.inputs.get(rel).is_some_and(|(_, selected)| *selected);
        self.inputs.insert(
            rel.to_owned(),
            (format!("{:x}", digest.finalize()), selected),
        );
        true
    }
}

#[cfg(test)]
#[path = "stream_tests.rs"]
mod tests;
