// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The canonical bytes of a contract, equal to Python `contract_bytes`
//! (`json.dumps(asdict(contract), indent=2, ensure_ascii=False) + "\n"`).
//!
//! Each type serializes its fields in the order of its Python dataclass. Its serde attributes leave
//! out what `_without_none` and `contract_bytes` leave out; the UML Target keeps its `null` values.
//! A rule writes `id` and `kind` first and its head fields at the place of its dataclass.

use serde_json::{Map, Value};

use crate::contract::digest_of;
use crate::document::Contract;
use crate::model::{ContractDigest, RuleKind};
use crate::rule::{body_of, head_of, kind_of, Rule};
use crate::version::version_text;
use crate::words::spelling;

/// The canonical bytes of a contract.
pub fn canonical_bytes(contract: &Contract) -> Vec<u8> {
    let mut root = Map::new();
    if let Some(schema) = &contract.schema {
        root.insert("$schema".to_owned(), Value::String(schema.clone()));
    }
    root.insert(
        "schema_version".to_owned(),
        Value::String(version_text(contract.version)),
    );
    root.insert("components".to_owned(), value(&contract.components));
    let rules = contract.rules.iter().map(rule).collect();
    root.insert("rules".to_owned(), Value::Array(rules));
    if let Some(declarations) = &contract.declarations {
        root.insert("declarations".to_owned(), value(declarations));
    }
    let mut written = String::new();
    write(&mut written, &Value::Object(root), 0);
    written.push('\n');
    written.into_bytes()
}

/// The digest that an amendment binds to: the SHA-256 of the canonical bytes (AD-61).
pub fn canonical_digest(contract: &Contract) -> ContractDigest {
    digest_of(&canonical_bytes(contract))
}

/// The serde value of a type of this crate. It holds no map with a key that is not text, so it
/// cannot fail.
fn value<T: serde::Serialize>(item: &T) -> Value {
    serde_json::to_value(item).unwrap_or_default()
}

/// The number of fields of a kind before `rationale`, `provenance` and `decided_by`.
fn head_position(kind: RuleKind) -> usize {
    use RuleKind as K;
    match kind {
        K::CompleteRequires | K::NoComponentCycles | K::InterfaceBoundary => 0,
        K::CompleteAssignment
        | K::CompleteExternalScope
        | K::LayerOrder
        | K::SiblingIsolation
        | K::BoundaryTypes => 1,
        K::AllowedDependency
        | K::ForbiddenConstruct
        | K::ExternalDependencyScope
        | K::RootLayout
        | K::SymbolPlacement
        | K::CallOwner => 2,
        K::ForbiddenDependency
        | K::SourceOwnership
        | K::ProtocolDeclarations
        | K::ForbiddenCallArgument
        | K::CatalogUse
        | K::ForbiddenEffectUnderCondition => 3,
        K::BoundedNumericOperand => 4,
        K::CatalogArgument => 5,
    }
}

fn rule(rule: &Rule) -> Value {
    let head = head_of(rule);
    let kind = kind_of(rule);
    let Value::Object(body) = body_of(rule) else {
        return Value::Null;
    };
    let mut fields = body.into_iter().filter(|(key, _)| key != "head");
    let mut out = Map::new();
    out.insert("id".to_owned(), Value::String(head.id.0.clone()));
    out.insert("kind".to_owned(), Value::String(spelling(&kind)));
    out.extend(fields.by_ref().take(head_position(kind)));
    out.insert(
        "rationale".to_owned(),
        Value::String(head.rationale.clone()),
    );
    out.insert("provenance".to_owned(), value(&head.provenance));
    out.insert("decided_by".to_owned(), value(&head.decided_by));
    out.extend(fields);
    Value::Object(out)
}

/// A JSON string as Python `json.dumps` writes it with `ensure_ascii=False`.
fn write_text(out: &mut String, value: &str) {
    out.push('"');
    for character in value.chars() {
        match character {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            control if u32::from(control) < 0x20 => {
                out.push_str(&format!("\\u{:04x}", u32::from(control)));
            }
            other => out.push(other),
        }
    }
    out.push('"');
}

fn indent(out: &mut String, level: usize) {
    out.push('\n');
    out.push_str(&"  ".repeat(level));
}

/// The `indent=2` layout: an empty list is `[]`, an item has its own line.
fn write(out: &mut String, value: &Value, level: usize) {
    match value {
        Value::Null => out.push_str("null"),
        Value::Bool(flag) => out.push_str(if *flag { "true" } else { "false" }),
        Value::Number(number) => out.push_str(&number.to_string()),
        Value::String(text) => write_text(out, text),
        Value::Array(items) if items.is_empty() => out.push_str("[]"),
        Value::Object(entries) if entries.is_empty() => out.push_str("{}"),
        Value::Array(items) => {
            out.push('[');
            for (index, item) in items.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                write(out, item, level + 1);
            }
            indent(out, level);
            out.push(']');
        }
        Value::Object(entries) => {
            out.push('{');
            for (index, (key, item)) in entries.iter().enumerate() {
                if index > 0 {
                    out.push(',');
                }
                indent(out, level + 1);
                write_text(out, key);
                out.push_str(": ");
                write(out, item, level + 1);
            }
            indent(out, level);
            out.push('}');
        }
    }
}
