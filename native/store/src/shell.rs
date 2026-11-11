// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The compact form of the shell's record sections in the `W` frame (AD-346).
//!
//! The frame is `{"texts": [...], "fields": {section: [...]}, "model": {...}}`. In `model`, a record
//! of the shell in a record section is a row: the record fields without `data`, then the values
//! of the section's shell data fields in the order of `fields`. In a row, a number is the index of
//! a text in `texts`. Any other number is `{"n": value}`, a bool `{"b": value}`, an object
//! `{"o": {...}}` and an absent data field `{"m": true}`.
//!
//! The store reads the frame from the stream into flat buffers: the texts into one arena, and the
//! cells of all rows into one stream of `u32` (a text index, a marker for null, a list with its
//! length, or a tagged object by its index). A row is a range of that stream. It builds the record
//! object of one row only while it reads it (`canonical.rs:with_record`), so the bytes are those
//! of the plain record.

use std::collections::{HashMap, HashSet};
use std::fmt;

use serde::de::{self, DeserializeSeed, Deserializer, MapAccess, SeqAccess, Visitor};
use serde::Deserialize;
use serde_json::{Map, Value};

/// The cell markers; a smaller value is a text index.
const NULL: u32 = u32::MAX;
const LIST: u32 = u32::MAX - 1;
const TAGGED: u32 = u32::MAX - 2;
const MARKERS: u32 = u32::MAX - 2;

const UNKNOWN_FORM: &str = "a shell cell has an unknown form";
const NO_TEXT: &str = "a shell cell names no text";

/// Any seed visitor as a `DeserializeSeed`: the stream is JSON, so it says each value's shape.
struct Any<V>(V);

impl<'de, V: Visitor<'de>> DeserializeSeed<'de> for Any<V> {
    type Value = V::Value;
    fn deserialize<D: Deserializer<'de>>(self, deserializer: D) -> Result<V::Value, D::Error> {
        deserializer.deserialize_any(self.0)
    }
}

/// The texts, the data fields and the cells of the shell rows of one `W` frame.
#[derive(Default)]
pub(crate) struct Shell {
    text: String,
    ends: Vec<usize>,
    pub(crate) fields: HashMap<String, Vec<String>>,
    cells: Vec<u32>,
    tagged: Vec<Map<String, Value>>,
}

/// A record or an evidence entry of the observation: held by the store (its id), sent by the
/// shell as an object, or, in a record section, as a row (a range of the cell stream).
pub(crate) enum Entry {
    Stored(String),
    Shell(Box<Map<String, Value>>),
    Row(u32, u32),
}

/// A top-level value of the model: a list of entries (a record section or the evidence) or a
/// plain value. No other top-level value of an observation is a list.
pub(crate) enum Top {
    Entries(Vec<Entry>),
    Plain(Value),
}

/// Read a `W` frame into the shell and the model. `sections` names the record sections that a
/// shell field list may name.
pub(crate) fn frame(
    reader: impl std::io::Read,
    sections: &[&str],
) -> Result<(Shell, HashMap<String, Top>), String> {
    let mut shell = Shell::default();
    let mut deserializer = serde_json::Deserializer::from_reader(reader);
    let model = Any(FrameSeed(&mut shell))
        .deserialize(&mut deserializer)
        .and_then(|model| deserializer.end().map(|()| model))
        .map_err(|error| error.to_string())?;
    for (section, names) in &shell.fields {
        if !sections.contains(&section.as_str()) {
            return Err(format!("the shell names no record section {section}"));
        }
        if names.iter().collect::<HashSet<_>>().len() != names.len() {
            return Err(format!("the shell fields of {section} repeat a name"));
        }
    }
    Ok((shell, model))
}

struct FrameSeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for FrameSeed<'_> {
    type Value = HashMap<String, Top>;
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("an observation frame")
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        let mut model = None;
        let mut seen = HashSet::new();
        while let Some(key) = map.next_key::<String>()? {
            if !seen.insert(key.clone()) {
                return Err(de::Error::custom(format!("duplicate field `{key}`")));
            }
            match key.as_str() {
                "texts" => map.next_value_seed(Any(TextsSeed(&mut *self.0)))?,
                "fields" => self.0.fields = map.next_value()?,
                "model" => model = Some(map.next_value_seed(Any(ModelSeed(&mut *self.0)))?),
                other => return Err(de::Error::custom(format!("unknown field `{other}`"))),
            }
        }
        if seen.len() != 3 {
            return Err(de::Error::custom("the frame needs texts, fields and model"));
        }
        model.ok_or_else(|| de::Error::custom("the frame needs a model"))
    }
}

struct TextsSeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for TextsSeed<'_> {
    type Value = ();
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a list of texts")
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<(), A::Error> {
        while let Some(text) = seq.next_element::<std::borrow::Cow<'de, str>>()? {
            self.0.text.push_str(&text);
            self.0.ends.push(self.0.text.len());
        }
        Ok(())
    }
}

struct ModelSeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for ModelSeed<'_> {
    type Value = HashMap<String, Top>;
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("an observation")
    }
    fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
        let mut model = HashMap::new();
        while let Some(key) = map.next_key::<String>()? {
            let value = map.next_value_seed(Any(TopSeed(&mut *self.0)))?;
            model.insert(key, value);
        }
        Ok(model)
    }
}

/// A top-level value: a list is a list of entries; any other value stays JSON.
struct TopSeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for TopSeed<'_> {
    type Value = Top;
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("an observation value")
    }
    fn visit_unit<E: de::Error>(self) -> Result<Top, E> {
        Ok(Top::Plain(Value::Null))
    }
    fn visit_bool<E: de::Error>(self, value: bool) -> Result<Top, E> {
        Ok(Top::Plain(Value::Bool(value)))
    }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<Top, E> {
        Ok(Top::Plain(Value::from(value)))
    }
    fn visit_i64<E: de::Error>(self, value: i64) -> Result<Top, E> {
        Ok(Top::Plain(Value::from(value)))
    }
    fn visit_f64<E: de::Error>(self, value: f64) -> Result<Top, E> {
        Ok(Top::Plain(Value::from(value)))
    }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Top, E> {
        Ok(Top::Plain(Value::from(value)))
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Top, A::Error> {
        let mut entries = Vec::with_capacity(seq.size_hint().unwrap_or(0));
        while let Some(entry) = seq.next_element_seed(Any(EntrySeed(&mut *self.0)))? {
            entries.push(entry);
        }
        Ok(Top::Entries(entries))
    }
    fn visit_map<A: MapAccess<'de>>(self, map: A) -> Result<Top, A::Error> {
        Ok(Top::Plain(Value::Object(object(map)?)))
    }
}

fn object<'de, A: MapAccess<'de>>(map: A) -> Result<Map<String, Value>, A::Error> {
    Map::deserialize(de::value::MapAccessDeserializer::new(map))
}

fn position<E: de::Error, T>(cells: &[T]) -> Result<u32, E> {
    u32::try_from(cells.len()).map_err(|_| E::custom("the shell rows are too long"))
}

/// An entry of a section: a stored id, a shell object, or a row of cells.
struct EntrySeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for EntrySeed<'_> {
    type Value = Entry;
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a stored id, a shell object or a shell row")
    }
    fn visit_str<E: de::Error>(self, value: &str) -> Result<Entry, E> {
        Ok(Entry::Stored(value.to_owned()))
    }
    fn visit_string<E: de::Error>(self, value: String) -> Result<Entry, E> {
        Ok(Entry::Stored(value))
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<Entry, A::Error> {
        let start = position(&self.0.cells)?;
        while seq
            .next_element_seed(Any(CellSeed(&mut *self.0)))?
            .is_some()
        {}
        Ok(Entry::Row(start, position(&self.0.cells)?))
    }
    fn visit_map<A: MapAccess<'de>>(self, map: A) -> Result<Entry, A::Error> {
        Ok(Entry::Shell(Box::new(object(map)?)))
    }
}

/// One cell of a row, appended to the cell stream.
struct CellSeed<'s>(&'s mut Shell);

impl<'de> Visitor<'de> for CellSeed<'_> {
    type Value = ();
    fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.write_str("a shell cell")
    }
    fn visit_u64<E: de::Error>(self, value: u64) -> Result<(), E> {
        let index = u32::try_from(value).ok().filter(|index| *index < MARKERS);
        self.0.cells.push(index.ok_or_else(|| E::custom(NO_TEXT))?);
        Ok(())
    }
    fn visit_unit<E: de::Error>(self) -> Result<(), E> {
        self.0.cells.push(NULL);
        Ok(())
    }
    fn visit_seq<A: SeqAccess<'de>>(self, mut seq: A) -> Result<(), A::Error> {
        self.0.cells.extend([LIST, 0]);
        let at = self.0.cells.len() - 1;
        let mut count = 0u32;
        while seq
            .next_element_seed(Any(CellSeed(&mut *self.0)))?
            .is_some()
        {
            count += 1;
        }
        self.0.cells[at] = count;
        Ok(())
    }
    fn visit_map<A: MapAccess<'de>>(self, map: A) -> Result<(), A::Error> {
        let index = position(&self.0.tagged)?;
        self.0.tagged.push(object(map)?);
        self.0.cells.extend([TAGGED, index]);
        Ok(())
    }
}

impl Shell {
    fn texts(&self) -> usize {
        self.ends.len()
    }

    /// The text of index `index`, if the frame has it.
    pub(crate) fn text(&self, index: usize) -> Option<&str> {
        let end = *self.ends.get(index)?;
        let start = if index == 0 { 0 } else { self.ends[index - 1] };
        self.text.get(start..end)
    }

    /// Every text of the frame with its index.
    pub(crate) fn all_texts(&self) -> impl Iterator<Item = &str> {
        (0..self.texts()).filter_map(|index| self.text(index))
    }

    /// The data fields of the shell rows of `section`.
    pub(crate) fn fields(&self, section: &str) -> &[String] {
        self.fields.get(section).map_or(&[], Vec::as_slice)
    }

    /// The position after the cell at `at`.
    fn skip(&self, at: usize) -> usize {
        match self.cells.get(at) {
            Some(&LIST) => {
                let count = self.cells.get(at + 1).copied().unwrap_or(0);
                (0..count).fold(at + 2, |next, _| self.skip(next))
            }
            Some(&TAGGED) => at + 2,
            _ => at + 1,
        }
    }

    /// The positions of the top-level cells of the row `start..end`.
    pub(crate) fn row(&self, start: u32, end: u32) -> Vec<usize> {
        let (mut at, end) = (start as usize, end as usize);
        let mut cells = Vec::new();
        while at < end {
            cells.push(at);
            at = self.skip(at);
        }
        cells
    }

    /// Whether the cell at `at` is the marker of an absent data field.
    pub(crate) fn missing(&self, at: usize) -> bool {
        self.cells.get(at) == Some(&TAGGED)
            && self
                .cells
                .get(at + 1)
                .and_then(|index| self.tagged.get(*index as usize))
                .is_some_and(|tag| tag.len() == 1 && tag.get("m") == Some(&Value::Bool(true)))
    }

    /// Call `each` with the index of every text of the cell at `at`, nested ones included.
    pub(crate) fn texts_of(&self, at: usize, each: &mut impl FnMut(usize)) {
        match self.cells.get(at) {
            Some(&LIST) => {
                let count = self.cells.get(at + 1).copied().unwrap_or(0);
                (0..count).fold(at + 2, |next, _| {
                    self.texts_of(next, each);
                    self.skip(next)
                });
            }
            Some(&TAGGED) => {
                let tag = self
                    .cells
                    .get(at + 1)
                    .and_then(|i| self.tagged.get(*i as usize));
                if let Some(Value::Object(map)) = tag.and_then(|tag| tag.get("o")) {
                    map.values().for_each(|item| Self::references(item, each));
                }
            }
            Some(&NULL) | None => {}
            Some(index) => each(*index as usize),
        }
    }

    fn references(value: &Value, each: &mut impl FnMut(usize)) {
        match value {
            Value::Number(index) => {
                if let Some(index) = index.as_u64() {
                    each(usize::try_from(index).unwrap_or(usize::MAX));
                }
            }
            Value::Array(items) => items.iter().for_each(|item| Self::references(item, each)),
            Value::Object(tag) => {
                if let Some(Value::Object(map)) = tag.get("o") {
                    map.values().for_each(|item| Self::references(item, each));
                }
            }
            _ => {}
        }
    }

    fn string(&self, index: usize) -> Result<Value, String> {
        self.text(index)
            .map(|text| Value::String(text.to_owned()))
            .ok_or_else(|| NO_TEXT.to_owned())
    }

    /// A cell inside a tagged object, which stays JSON: a number names a text.
    fn value(&self, cell: &Value) -> Result<Value, String> {
        match cell {
            Value::Null => Ok(Value::Null),
            Value::Number(index) => {
                let index = index.as_u64().and_then(|i| usize::try_from(i).ok());
                self.string(index.unwrap_or(usize::MAX))
            }
            Value::Array(items) => items
                .iter()
                .map(|item| self.value(item))
                .collect::<Result<Vec<_>, _>>()
                .map(Value::Array),
            Value::Object(tag) => self.tagged(tag),
            _ => Err(UNKNOWN_FORM.to_owned()),
        }
    }

    fn tagged(&self, tag: &Map<String, Value>) -> Result<Value, String> {
        match (tag.len(), tag.iter().next()) {
            (1, Some((key, value @ Value::Number(_)))) if key == "n" => Ok(value.clone()),
            (1, Some((key, value @ Value::Bool(_)))) if key == "b" => Ok(value.clone()),
            (1, Some((key, Value::Object(map)))) if key == "o" => map
                .iter()
                .map(|(name, item)| Ok((name.clone(), self.value(item)?)))
                .collect::<Result<Map<_, _>, String>>()
                .map(Value::Object),
            _ => Err("a shell cell has an unknown tag".to_owned()),
        }
    }

    /// The value of the cell at `at`.
    fn cell(&self, at: usize) -> Result<Value, String> {
        match self.cells.get(at) {
            Some(&NULL) => Ok(Value::Null),
            Some(&LIST) => {
                let count = self.cells.get(at + 1).copied().unwrap_or(0);
                let mut items = Vec::with_capacity(count as usize);
                let mut next = at + 2;
                for _ in 0..count {
                    items.push(self.cell(next)?);
                    next = self.skip(next);
                }
                Ok(Value::Array(items))
            }
            Some(&TAGGED) => {
                let tag = self
                    .cells
                    .get(at + 1)
                    .and_then(|i| self.tagged.get(*i as usize));
                tag.ok_or_else(|| UNKNOWN_FORM.to_owned())
                    .and_then(|tag| self.tagged(tag))
            }
            Some(index) => self.string(*index as usize),
            None => Err(UNKNOWN_FORM.to_owned()),
        }
    }

    /// The record object of the row `start..end`; `head` names the record fields before `data`.
    pub(crate) fn record(
        &self,
        start: u32,
        end: u32,
        head: &[&str],
        fields: &[String],
    ) -> Result<Map<String, Value>, String> {
        let row = self.row(start, end);
        if row.len() != head.len() + fields.len() {
            return Err("a shell row does not match its fields".to_owned());
        }
        let mut item = Map::new();
        for (key, at) in head.iter().zip(&row) {
            item.insert((*key).to_owned(), self.cell(*at)?);
        }
        let mut data = Map::new();
        for (key, at) in fields.iter().zip(&row[head.len()..]) {
            if !self.missing(*at) {
                data.insert(key.clone(), self.cell(*at)?);
            }
        }
        item.insert("data".to_owned(), Value::Object(data));
        Ok(item)
    }
}

#[cfg(test)]
#[path = "shell_tests.rs"]
pub(crate) mod tests;
