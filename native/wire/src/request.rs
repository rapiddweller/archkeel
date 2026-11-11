// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The framing of a collection request: JSON bytes in, a typed request out. The types and their
//! rules are in `archkeel_facts::request`.

use archkeel_facts::request::{
    DartRequest, PythonRequest, Request, RustRequest, TypeScriptRequest,
};

/// Decode a TypeScript request. The error text names the first field that is not valid.
pub fn decode(payload: &[u8]) -> Result<TypeScriptRequest, String> {
    parse(payload)?.typescript()
}

/// Decode a Rust request. Its resolver is `{"language": "rust"}`.
pub fn decode_rust(payload: &[u8]) -> Result<RustRequest, String> {
    parse(payload)?.rust()
}

/// Decode a Python request: protocol 10.0.0 with the interpreter block (AD-334).
pub fn decode_python(payload: &[u8]) -> Result<PythonRequest, String> {
    parse(payload)?.python()
}

/// Decode a Dart request. Its resolver is `{"language": "dart"}` (3.0.0, 8.0.0 or 9.0.0).
pub fn decode_dart(payload: &[u8]) -> Result<DartRequest, String> {
    parse(payload)?.dart()
}

fn parse(payload: &[u8]) -> Result<Request, String> {
    let request: Request = serde_json::from_slice(payload)
        .map_err(|error| format!("invalid collection request: {error}"))?;
    request.validate()?;
    Ok(request)
}

#[cfg(test)]
#[path = "request_tests.rs"]
mod tests;
