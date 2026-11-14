// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The part of TOML that a `Cargo.toml` needs: tables, arrays of tables, dotted keys, strings,
//! inline tables, arrays, booleans and unsigned integers. Other numbers and dates are `Value::Other`, because the
//! collector never reads one. A file that this reader cannot read gives an error, and the
//! collector reports it as UNKNOWN: it never guesses.

use std::collections::BTreeMap;

pub(crate) type Table = BTreeMap<String, Value>;

#[derive(Clone, Debug, PartialEq)]
pub(crate) enum Value {
    Text(String),
    Table(Table),
    Array(Vec<Value>),
    Boolean(bool),
    Integer(u64),
    Other,
}

/// The deepest nesting of arrays and inline tables that the reader follows.
const MAX_DEPTH: usize = 64;

/// Read a manifest. A UTF-8 byte order mark at the start is no part of the text, as for Cargo.
pub(crate) fn parse(text: &str) -> Result<Table, String> {
    let text = text.strip_prefix('\u{feff}').unwrap_or(text);
    let mut reader = Reader {
        bytes: text.as_bytes(),
        at: 0,
    };
    let mut root = Table::new();
    let mut current: Vec<String> = Vec::new();
    loop {
        reader.skip_blank();
        match reader.peek() {
            None => return Ok(root),
            Some(b'[') => current = reader.header(&mut root)?,
            Some(_) => {
                let keys = reader.key_path()?;
                reader.expect(b'=')?;
                let value = reader.value(0)?;
                reader.end_of_line()?;
                insert(descend(&mut root, &current)?, &keys, value)?;
            }
        }
    }
}

struct Reader<'a> {
    bytes: &'a [u8],
    at: usize,
}

impl Reader<'_> {
    fn peek(&self) -> Option<u8> {
        self.bytes.get(self.at).copied()
    }

    fn fail<T>(&self, what: &str) -> Result<T, String> {
        let line = self.bytes[..self.at.min(self.bytes.len())]
            .iter()
            .filter(|byte| **byte == b'\n')
            .count()
            + 1;
        Err(format!("{what} at line {line}"))
    }

    fn expect(&mut self, byte: u8) -> Result<(), String> {
        self.skip_space();
        if self.peek() == Some(byte) {
            self.at += 1;
            Ok(())
        } else {
            self.fail(&format!("expected `{}`", char::from(byte)))
        }
    }

    fn skip_space(&mut self) {
        while matches!(self.peek(), Some(b' ' | b'\t')) {
            self.at += 1;
        }
    }

    fn skip_comment(&mut self) {
        if self.peek() == Some(b'#') {
            while !matches!(self.peek(), None | Some(b'\n')) {
                self.at += 1;
            }
        }
    }

    /// Skip spaces, comments and line breaks.
    fn skip_blank(&mut self) {
        loop {
            self.skip_space();
            self.skip_comment();
            if matches!(self.peek(), Some(b'\n' | b'\r')) {
                self.at += 1;
            } else {
                return;
            }
        }
    }

    fn end_of_line(&mut self) -> Result<(), String> {
        self.skip_space();
        self.skip_comment();
        match self.peek() {
            None | Some(b'\n' | b'\r') => Ok(()),
            Some(_) => self.fail("unexpected text after a value"),
        }
    }

    /// Read `[a.b]` or `[[a.b]]`; an array of tables gets a new table.
    fn header(&mut self, root: &mut Table) -> Result<Vec<String>, String> {
        let array = self.bytes.get(self.at + 1) == Some(&b'[');
        self.at += if array { 2 } else { 1 };
        let keys = self.key_path()?;
        self.expect(b']')?;
        if array {
            self.expect(b']')?;
        }
        self.end_of_line()?;
        if array {
            let (last, parents) = keys.split_last().ok_or("empty table name")?;
            let slot = descend(root, parents)?
                .entry(last.clone())
                .or_insert_with(|| Value::Array(Vec::new()));
            match slot {
                Value::Array(items) => items.push(Value::Table(Table::new())),
                _ => return self.fail("a table name is used twice"),
            }
        } else {
            descend(root, &keys)?;
        }
        Ok(keys)
    }

    fn key_path(&mut self) -> Result<Vec<String>, String> {
        let mut keys = vec![self.key()?];
        loop {
            self.skip_space();
            if self.peek() != Some(b'.') {
                return Ok(keys);
            }
            self.at += 1;
            keys.push(self.key()?);
        }
    }

    fn key(&mut self) -> Result<String, String> {
        self.skip_space();
        match self.peek() {
            Some(quote @ (b'"' | b'\'')) => self.quoted(quote),
            _ => {
                let start = self.at;
                while matches!(self.peek(), Some(b) if b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
                {
                    self.at += 1;
                }
                if start == self.at {
                    return self.fail("expected a key");
                }
                Ok(String::from_utf8_lossy(&self.bytes[start..self.at]).into_owned())
            }
        }
    }

    /// A string on one line. A basic string decodes the escapes of TOML exactly; an escape that
    /// TOML does not define is an error, so the crate is UNKNOWN and never misread.
    fn quoted(&mut self, quote: u8) -> Result<String, String> {
        self.at += 1;
        let mut out = Vec::new();
        loop {
            match self.peek() {
                None | Some(b'\n') => return self.fail("a string does not end"),
                Some(byte) if byte == quote => {
                    self.at += 1;
                    return Ok(String::from_utf8_lossy(&out).into_owned());
                }
                Some(b'\\') if quote == b'"' => self.escape(&mut out)?,
                Some(byte) => {
                    out.push(byte);
                    self.at += 1;
                }
            }
        }
    }

    /// Decode one escape (the next byte is the backslash) and push its bytes.
    fn escape(&mut self, out: &mut Vec<u8>) -> Result<(), String> {
        self.at += 1;
        let digits = match self.peek() {
            Some(b'u') => 4,
            Some(b'U') => 8,
            Some(byte) => {
                let decoded = match byte {
                    b'b' => 8,
                    b't' => b'\t',
                    b'n' => b'\n',
                    b'f' => 12,
                    b'r' => b'\r',
                    b'"' | b'\\' => byte,
                    _ => return self.fail("an escape that TOML does not define"),
                };
                out.push(decoded);
                self.at += 1;
                return Ok(());
            }
            None => return self.fail("a string does not end"),
        };
        let hex = self
            .bytes
            .get(self.at + 1..self.at + 1 + digits)
            .unwrap_or(&[]);
        let code = std::str::from_utf8(hex)
            .ok()
            .filter(|text| text.len() == digits && text.bytes().all(|b| b.is_ascii_hexdigit()))
            .and_then(|text| u32::from_str_radix(text, 16).ok())
            .and_then(char::from_u32);
        let Some(code) = code else {
            return self.fail("a unicode escape that is not a scalar value");
        };
        out.extend_from_slice(code.encode_utf8(&mut [0; 4]).as_bytes());
        self.at += 1 + digits;
        Ok(())
    }

    fn value(&mut self, depth: usize) -> Result<Value, String> {
        if depth > MAX_DEPTH {
            return self.fail("values are nested too deep");
        }
        self.skip_space();
        match self.peek() {
            Some(quote @ (b'"' | b'\'')) => {
                let triple = [quote; 3];
                if self.bytes[self.at..].starts_with(&triple) {
                    return self.multiline(&triple);
                }
                self.quoted(quote).map(Value::Text)
            }
            Some(b'{') => self.inline_table(depth),
            Some(b'[') => self.array(depth),
            _ => {
                let start = self.at;
                while !matches!(
                    self.peek(),
                    None | Some(b'\n' | b'\r' | b',' | b'}' | b']' | b'#')
                ) {
                    self.at += 1;
                }
                Ok(match self.bytes[start..self.at].trim_ascii() {
                    b"true" => Value::Boolean(true),
                    b"false" => Value::Boolean(false),
                    raw => std::str::from_utf8(raw)
                        .ok()
                        .and_then(|s| s.parse::<u64>().ok())
                        .filter(|n| n.to_string().as_bytes() == raw)
                        .map_or(Value::Other, Value::Integer),
                })
            }
        }
    }

    /// A string over several lines: the first line break is dropped, a basic string decodes its
    /// escapes, and a backslash before a line break joins the lines.
    fn multiline(&mut self, fence: &[u8; 3]) -> Result<Value, String> {
        let quote = fence[0];
        self.at += 3;
        if self.peek() == Some(b'\r') && self.bytes.get(self.at + 1) == Some(&b'\n') {
            self.at += 1;
        }
        if self.peek() == Some(b'\n') {
            self.at += 1;
        }
        let mut out = Vec::new();
        loop {
            match self.peek() {
                None => return self.fail("a multi-line string does not end"),
                Some(byte) if byte == quote && self.bytes[self.at..].starts_with(fence) => {
                    self.close_multiline(quote, &mut out)?;
                    return Ok(Value::Text(String::from_utf8_lossy(&out).into_owned()));
                }
                // The guard skips a continuation; any other backslash is an escape.
                Some(b'\\') if quote == b'"' && self.line_continuation() => {}
                Some(b'\\') if quote == b'"' => self.escape(&mut out)?,
                Some(byte) => {
                    out.push(byte);
                    self.at += 1;
                }
            }
        }
    }

    /// The closing fence; one or two more quotes before it belong to the text.
    fn close_multiline(&mut self, quote: u8, out: &mut Vec<u8>) -> Result<(), String> {
        let run = self.bytes[self.at..]
            .iter()
            .take_while(|b| **b == quote)
            .count();
        if run > 5 {
            return self.fail("too many quotes in a multi-line string");
        }
        out.extend(std::iter::repeat_n(quote, run - 3));
        self.at += run;
        Ok(())
    }

    /// A backslash, then spaces and a line break: skip it and all the white space that follows.
    fn line_continuation(&mut self) -> bool {
        let blank = |at: usize, more: &[u8]| self.bytes.get(at).is_some_and(|b| more.contains(b));
        let mut ahead = self.at + 1;
        while blank(ahead, b" \t") {
            ahead += 1;
        }
        if !blank(ahead, b"\r\n") {
            return false;
        }
        while blank(ahead, b" \t\r\n") {
            ahead += 1;
        }
        self.at = ahead;
        true
    }

    fn inline_table(&mut self, depth: usize) -> Result<Value, String> {
        let mut table = Table::new();
        self.sequence(b'}', |this| {
            let keys = this.key_path()?;
            this.expect(b'=')?;
            let value = this.value(depth + 1)?;
            insert(&mut table, &keys, value)
        })?;
        Ok(Value::Table(table))
    }

    fn array(&mut self, depth: usize) -> Result<Value, String> {
        let mut items = Vec::new();
        self.sequence(b']', |this| {
            items.push(this.value(depth + 1)?);
            Ok(())
        })?;
        Ok(Value::Array(items))
    }

    /// The elements between an opening bracket (the next byte) and `close`, separated by commas.
    fn sequence(
        &mut self,
        close: u8,
        mut element: impl FnMut(&mut Self) -> Result<(), String>,
    ) -> Result<(), String> {
        self.at += 1;
        loop {
            self.skip_blank();
            if self.peek() == Some(close) {
                self.at += 1;
                return Ok(());
            }
            element(self)?;
            self.skip_blank();
            if self.peek() == Some(b',') {
                self.at += 1;
            } else if self.peek() != Some(close) {
                return self.fail(&format!("expected `,` or `{}`", char::from(close)));
            }
        }
    }
}

/// Go to the table at `path`; an array of tables gives its last table.
fn descend<'a>(mut table: &'a mut Table, path: &[String]) -> Result<&'a mut Table, String> {
    for key in path {
        let entry = table
            .entry(key.clone())
            .or_insert_with(|| Value::Table(Table::new()));
        table = match entry {
            Value::Table(next) => next,
            Value::Array(items) => match items.last_mut() {
                Some(Value::Table(next)) => next,
                _ => return Err(format!("`{key}` is not a table")),
            },
            _ => return Err(format!("`{key}` is not a table")),
        };
    }
    Ok(table)
}

fn insert(table: &mut Table, keys: &[String], value: Value) -> Result<(), String> {
    let (last, parents) = keys.split_last().ok_or("empty key")?;
    let slot = descend(table, parents)?;
    if slot.insert(last.clone(), value).is_some() {
        return Err(format!("the key `{last}` is set twice"));
    }
    Ok(())
}

impl Value {
    pub(crate) fn text(&self) -> Option<&str> {
        match self {
            Value::Text(text) => Some(text),
            _ => None,
        }
    }

    pub(crate) fn table(&self) -> Option<&Table> {
        match self {
            Value::Table(table) => Some(table),
            _ => None,
        }
    }
}

#[cfg(test)]
#[path = "toml_tests.rs"]
mod tests;
