// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! `_function_signature` and `_python_visibility` (`symbols.py`): the parameters of a function as
//! text, and the visibility that its name gives. The definition table (AD-377) and the
//! declarations (AD-514) read them from here, each with its own writer of text.

use ruff_python_ast::{Expr, Parameter, StmtFunctionDef};
use serde_json::{json, Map, Value};

/// The text of an optional expression, or the error of a text that the reader cannot write.
type Text<'t, E> = &'t dyn Fn(Option<&Expr>) -> Result<Option<String>, E>;

/// `_function_signature`: the parameters, the receiver, the return annotation and `async`.
pub(crate) fn signature<E>(
    text: Text<'_, E>,
    node: &StmtFunctionDef,
    data: &mut Map<String, Value>,
) -> Result<(), E> {
    let params = &node.parameters;
    let positional: Vec<_> = params.posonlyargs.iter().chain(&params.args).collect();
    let mut parameters = Vec::new();
    for (index, item) in positional.iter().enumerate() {
        let kind = if index < params.posonlyargs.len() {
            "positional_only"
        } else {
            "positional"
        };
        parameters.push(parameter(
            text,
            &item.parameter,
            kind,
            item.default.as_deref(),
            "",
        )?);
    }
    if let Some(vararg) = &params.vararg {
        parameters.push(parameter(text, vararg, "varargs", None, "*")?);
    }
    for item in &params.kwonlyargs {
        parameters.push(parameter(
            text,
            &item.parameter,
            "keyword_only",
            item.default.as_deref(),
            "",
        )?);
    }
    if let Some(kwarg) = &params.kwarg {
        parameters.push(parameter(text, kwarg, "kwargs", None, "**")?);
    }
    let receiver = positional.first().map(|item| item.parameter.name.as_str());
    data.insert("parameters".into(), Value::Array(parameters));
    data.insert("receiver_parameter".into(), json!(receiver));
    data.insert("returns".into(), json!(text(node.returns.as_deref())?));
    data.insert("async".into(), json!(node.is_async));
    Ok(())
}

fn parameter<E>(
    text: Text<'_, E>,
    param: &Parameter,
    kind: &str,
    default: Option<&Expr>,
    prefix: &str,
) -> Result<Value, E> {
    Ok(json!({
        "name": format!("{prefix}{}", param.name.as_str()),
        "annotation": text(param.annotation.as_deref())?,
        "kind": kind,
        "default": text(default)?,
        "default_known": true,
    }))
}

/// `_python_visibility`: private by the leading underscore, except a special name.
pub(crate) fn visibility(name: &str) -> Value {
    let special = name.starts_with("__") && name.ends_with("__") && name.chars().count() > 4;
    let kind = if name.starts_with('_') && !special {
        "private"
    } else {
        "public"
    };
    json!({"kind": kind, "basis": "convention", "spelling": name})
}
