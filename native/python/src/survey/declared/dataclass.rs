// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The form that `dataclass` gives a class (AD-782): the fields in order and a generated
//! `__init__`. `init=False`, an own `__init__`, `kw_only`, `field(init=False)`,
//! `field(kw_only=True)` and `KW_ONLY` are respected; `ClassVar` is no field. A base, an `InitVar`,
//! a field order that Python refuses and a body statement that is not modeled are unread.

use std::collections::{BTreeMap, HashSet};

use archkeel_facts::standard::{Wrapped, WrappedSlot};
use ruff_python_ast::{Expr, ExprCall, Identifier, Stmt, StmtAnnAssign, StmtAssign, StmtClassDef};

use super::shape_names::Hidden;
use super::wrapped_read::{decorator, function, proven_target, unread, Decorator, Reader};
use crate::survey::bound::Bound;

/// The keywords of `dataclass` that change no part of the surface.
const DATACLASS_PLAIN: [&str; 8] = [
    "repr",
    "eq",
    "order",
    "unsafe_hash",
    "frozen",
    "match_args",
    "slots",
    "weakref_slot",
];

/// The form of a class with `dataclass`, and the form of each method of its body into `out`.
pub(super) fn class(
    reader: &Reader<'_>,
    node: &StmtClassDef,
    qualname: &str,
    evidence: &str,
    out: &mut BTreeMap<String, Wrapped>,
) -> Wrapped {
    let mut init = true;
    let mut kw_only = false;
    for item in &node.decorator_list {
        match decorator(reader, &item.expression, &Hidden::default()) {
            Ok(Decorator::Dataclass(call)) => match options(call) {
                Ok((own_init, own_kw)) => (init, kw_only) = (own_init, own_kw),
                Err(reason) => return Wrapped::Unread(reason),
            },
            Ok(_) => return unread("a decorator other than dataclass on a class is not modeled"),
            Err(reason) => return Wrapped::Unread(reason),
        }
    }
    if node
        .arguments
        .as_ref()
        .is_some_and(|args| !matches!((&*args.args, &*args.keywords), ([], [])))
    {
        return unread("a base or a metaclass can add fields to the dataclass");
    }
    let body = Bound::of(&node.body).names();
    let hidden = Hidden {
        names: body.clone(),
        lazy: None,
    };
    let fields = match fields(reader, node, &hidden, kw_only) {
        Ok(fields) => fields,
        Err(reason) => return Wrapped::Unread(reason),
    };
    // shortcut: any repository store of a field name blocks the model, including instance stores;
    // use class-targeted mutation facts to recover precision.
    if fields.attributes.iter().any(|name| reader.may_write(name)) {
        return unread("the repository may change a dataclass field");
    }
    let slots = super::members::slots(&node.body);
    for statement in &node.body {
        if let Stmt::FunctionDef(method) = statement {
            let own = format!("{qualname}.{}", method.name);
            let form = function(reader, method, (&own, Some(&body)), slots.clone(), evidence);
            out.insert(own, form);
        }
    }
    let mut members: Vec<String> = body.iter().cloned().collect();
    members.sort();
    let own_init = HashSet::contains(&body, "__init__");
    Wrapped::Class {
        init: (init && !own_init).then_some(fields.init),
        members,
        attributes: fields.attributes,
        bases: Vec::new(),
        evidence: vec![evidence.to_owned()],
    }
}

/// The fields of a dataclass body: each declared name, and the parameters of `__init__`.
fn fields(
    reader: &Reader<'_>,
    node: &StmtClassDef,
    hidden: &Hidden<'_>,
    kw_only: bool,
) -> Result<Fields, String> {
    let mut found = Fields {
        keyword_mode: kw_only,
        ..Fields::default()
    };
    for statement in &node.body {
        match statement {
            Stmt::AnnAssign(item) => annotated(reader, item, hidden, &mut found)?,
            Stmt::Assign(item) => assigned(item, &mut found)?,
            Stmt::FunctionDef(_) | Stmt::Pass(_) => {}
            Stmt::Expr(item) if matches!(&*item.value, Expr::StringLiteral(_)) => {}
            _ => {
                return Err(
                    "the dataclass body holds a statement that ArchKeel does not model".to_owned(),
                )
            }
        }
    }
    let keyword = std::mem::take(&mut found.keyword);
    found.init.extend(keyword);
    Ok(found)
}

/// One annotated statement of a dataclass body: a field, a `ClassVar`, or the `KW_ONLY` mark.
fn annotated(
    reader: &Reader<'_>,
    item: &StmtAnnAssign,
    hidden: &Hidden<'_>,
    found: &mut Fields,
) -> Result<(), String> {
    let Expr::Name(target) = &*item.target else {
        return Err("a field target is not a plain name".to_owned());
    };
    let head = match &*item.annotation {
        Expr::Subscript(node) => &*node.value,
        other => other,
    };
    match proven_target(reader, head, hidden).as_deref() {
        Some("typing.ClassVar") => {
            found.attributes.push(target.id.to_string());
            return Ok(());
        }
        Some("dataclasses.KW_ONLY") => {
            found.keyword_mode = true;
            return Ok(());
        }
        Some("dataclasses.InitVar") => return Err("an InitVar field is not modeled".to_owned()),
        _ => {}
    }
    let field = field(reader, item.value.as_deref())?;
    found.attributes.push(target.id.to_string());
    if !field.init {
        return Ok(());
    }
    let keyword = found.keyword_mode || field.kw_only;
    let slot = WrappedSlot {
        name: target.id.to_string(),
        kind: if keyword {
            "keyword_only"
        } else {
            "positional"
        }
        .to_owned(),
        shape: Some(reader.shaper.position(Some(&item.annotation), hidden)),
    };
    if keyword {
        found.keyword.push(slot);
        return Ok(());
    }
    if found.defaulted && !field.default {
        return Err("a field without a default follows a field with a default".to_owned());
    }
    found.defaulted |= field.default;
    found.init.push(slot);
    Ok(())
}

/// The options of one field: `x: T`, `x: T = v` or `x: T = field(...)`.
fn field(reader: &Reader<'_>, value: Option<&Expr>) -> Result<Field, String> {
    let plain = Field {
        init: true,
        kw_only: false,
        default: value.is_some(),
    };
    let Some(Expr::Call(call)) = value else {
        return Ok(plain);
    };
    if proven_target(reader, &call.func, &Hidden::default()).as_deref() != Some("dataclasses.field")
    {
        return Ok(plain);
    }
    if !matches!(&*call.arguments.args, []) {
        return Err("a field call with positional arguments is not modeled".to_owned());
    }
    let mut found = Field {
        init: true,
        kw_only: false,
        default: false,
    };
    for keyword in &call.arguments.keywords {
        let Some(name) = keyword.arg.as_ref().map(Identifier::as_str) else {
            return Err("a field call with ** arguments is not modeled".to_owned());
        };
        match name {
            "init" => found.init = flag(name, &keyword.value)?,
            "kw_only" => found.kw_only = flag(name, &keyword.value)?,
            "default" | "default_factory" => found.default = true,
            _ => {}
        }
    }
    Ok(found)
}

/// The fields of a dataclass: the declared names and the parameters of its `__init__`.
#[derive(Default)]
struct Fields {
    attributes: Vec<String>,
    init: Vec<WrappedSlot>,
    /// The keyword-only parameters, which follow the positional ones.
    keyword: Vec<WrappedSlot>,
    /// True after `KW_ONLY`, or for `dataclass(kw_only=True)`.
    keyword_mode: bool,
    /// True after a positional field with a default.
    defaulted: bool,
}

/// The options of one field.
struct Field {
    init: bool,
    kw_only: bool,
    default: bool,
}

/// The names of a class attribute statement.
fn assigned(item: &StmtAssign, found: &mut Fields) -> Result<(), String> {
    for target in &item.targets {
        let Expr::Name(name) = target else {
            return Err("a class attribute target is not a plain name".to_owned());
        };
        found.attributes.push(name.id.to_string());
    }
    Ok(())
}

/// The literal Boolean of the field option `name`.
fn flag(name: &str, value: &Expr) -> Result<bool, String> {
    match value {
        Expr::BooleanLiteral(flag) => Ok(flag.value),
        _ => Err(format!("the field option {name} is not a literal")),
    }
}

/// `init` and `kw_only` of a `dataclass(...)` call; each other keyword must be a plain literal.
fn options(call: Option<&ExprCall>) -> Result<(bool, bool), String> {
    let Some(call) = call else {
        return Ok((true, false));
    };
    if !matches!(&*call.arguments.args, []) {
        return Err("a dataclass call with positional arguments is not modeled".to_owned());
    }
    let (mut init, mut kw_only) = (true, false);
    for keyword in &call.arguments.keywords {
        let name = keyword.arg.as_ref().map_or("**", Identifier::as_str);
        let Expr::BooleanLiteral(flag) = &keyword.value else {
            return Err(format!("the dataclass option {name} is not a literal"));
        };
        match name {
            "init" => init = flag.value,
            "kw_only" => kw_only = flag.value,
            other if DATACLASS_PLAIN.contains(&other) => {}
            other => return Err(format!("the dataclass option {other} is not modeled")),
        }
    }
    Ok((init, kw_only))
}
