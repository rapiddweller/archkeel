// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The part of TOML that a `Cargo.toml` needs: tables, arrays of tables, dotted keys, strings,
//! inline tables and arrays. A number, a date or a boolean is `Value::Other`, because the
//! collector never reads one. A file that this reader cannot read gives an error, and the
//! collector reports it as UNKNOWN: it never guesses.

use std::collections::BTreeMap;

pub type Table = BTreeMap<String, Value>;

#[derive(Clone, Debug, PartialEq)]
pub enum Value {
    Text(String),
    Table(Table),
    Array(Vec<Value>),
    Other,
}

/// The deepest nesting of arrays and inline tables that the reader follows.
const MAX_DEPTH: usize = 64;

pub fn parse(text: &str) -> Result<Table, String> {
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
                Some(b'\\') if quote == b'"' => {
                    self.at += 1;
                    out.push(match self.peek() {
                        Some(b'n') => b'\n',
                        Some(b't') => b'\t',
                        Some(other) => other,
                        None => return self.fail("a string does not end"),
                    });
                }
                Some(byte) => out.push(byte),
            }
            self.at += 1;
        }
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
                while !matches!(
                    self.peek(),
                    None | Some(b'\n' | b'\r' | b',' | b'}' | b']' | b'#')
                ) {
                    self.at += 1;
                }
                Ok(Value::Other)
            }
        }
    }

    fn multiline(&mut self, fence: &[u8; 3]) -> Result<Value, String> {
        self.at += 3;
        while !self.bytes[self.at.min(self.bytes.len())..].starts_with(fence) {
            if self.at >= self.bytes.len() {
                return self.fail("a multi-line string does not end");
            }
            self.at += 1;
        }
        self.at += 3;
        Ok(Value::Other)
    }

    fn inline_table(&mut self, depth: usize) -> Result<Value, String> {
        self.at += 1;
        let mut table = Table::new();
        loop {
            self.skip_blank();
            if self.peek() == Some(b'}') {
                self.at += 1;
                return Ok(Value::Table(table));
            }
            let keys = self.key_path()?;
            self.expect(b'=')?;
            let value = self.value(depth + 1)?;
            insert(&mut table, &keys, value)?;
            self.skip_blank();
            if self.peek() == Some(b',') {
                self.at += 1;
            } else if self.peek() != Some(b'}') {
                return self.fail("expected `,` or `}`");
            }
        }
    }

    fn array(&mut self, depth: usize) -> Result<Value, String> {
        self.at += 1;
        let mut items = Vec::new();
        loop {
            self.skip_blank();
            if self.peek() == Some(b']') {
                self.at += 1;
                return Ok(Value::Array(items));
            }
            items.push(self.value(depth + 1)?);
            self.skip_blank();
            if self.peek() == Some(b',') {
                self.at += 1;
            } else if self.peek() != Some(b']') {
                return self.fail("expected `,` or `]`");
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
    pub fn text(&self) -> Option<&str> {
        match self {
            Value::Text(text) => Some(text),
            _ => None,
        }
    }

    pub fn table(&self) -> Option<&Table> {
        match self {
            Value::Table(table) => Some(table),
            _ => None,
        }
    }
}

#[cfg(test)]
#[path = "toml_tests.rs"]
mod tests;
