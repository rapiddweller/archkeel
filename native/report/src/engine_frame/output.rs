// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The output of the frame writer. The renderer needs only the input JSON.

/// The canonical bytes of one engine frame. Only `Ruling::frame` makes one.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct EngineFrame {
    bytes: Vec<u8>,
}

pub(super) fn frame(bytes: Vec<u8>) -> EngineFrame {
    EngineFrame { bytes }
}

impl EngineFrame {
    /// The bytes, to be written one time.
    pub fn into_bytes(self) -> Vec<u8> {
        self.bytes
    }
}

/// Why the parts of the core give no frame.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum FrameError {
    /// The parts are not a JSON object.
    NotAnObject,
    /// A part has a key that only the ruling writes.
    RulingKey(String),
    /// The bytes cannot be written.
    Encode(String),
}

impl std::fmt::Display for FrameError {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            FrameError::NotAnObject => formatter.write_str("the parts of the frame are no object"),
            FrameError::RulingKey(key) => {
                write!(
                    formatter,
                    "the part {key} is a key that only the ruling writes"
                )
            }
            FrameError::Encode(error) => formatter.write_str(error),
        }
    }
}
