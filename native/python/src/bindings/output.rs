// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Count serialized bytes without allocating an output buffer.

use std::io::{self, Write};

use serde_json::Value;

pub const MAX_OUTPUT_BYTES: usize = 32 * 1024 * 1024;

pub(super) struct Output {
    left: usize,
}

fn message() -> String {
    format!("binding output limit exceeded ({MAX_OUTPUT_BYTES} bytes)")
}

impl Output {
    pub fn new() -> Self {
        Self {
            left: MAX_OUTPUT_BYTES,
        }
    }

    pub fn room(&self, bytes: usize) -> Result<(), String> {
        if bytes <= self.left {
            Ok(())
        } else {
            Err(message())
        }
    }

    pub fn value(&mut self, value: &Value) -> Result<(), String> {
        serde_json::to_writer(&mut *self, value).map_err(|_| message())
    }
}

impl Write for Output {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        self.left = self
            .left
            .checked_sub(bytes.len())
            .ok_or_else(|| io::Error::other(message()))?;
        Ok(bytes.len())
    }

    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

pub fn check(value: &Value) -> Result<(), String> {
    let mut output = Output::new();
    output.value(value)?;
    output.write_all(b"\n").map_err(|_| message())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_output_limit_counts_json_escapes_and_is_inclusive() {
        let mut output = Output { left: 8 };
        output.value(&serde_json::json!("\n")).expect("four bytes");
        output
            .value(&serde_json::json!("é"))
            .expect("four UTF-8 bytes");
        assert!(output.value(&Value::Null).is_err());
    }
}
