// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The reader of the standard decorators of one module (AD-782): the decorator by its qualified
//! name, the signature of a function, and the form that the decorators of a function give. See
//! `wrapped` for the forms.

use std::collections::HashSet;

use archkeel_facts::standard::{Wrapped, WrappedSlot};
use archkeel_facts::type_shape::{Binding, TypeShape, Unproven};
use archkeel_facts::vocab::MethodKind;
use ruff_python_ast::{Expr, ExprCall, Stmt, StmtFunctionDef};
use ruff_text_size::Ranged;

use super::found::Source;
use super::shape_names::{Hidden, Names};
use super::shape_text::render;
use super::shapes::Shaper;
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::bound::Bound;
use crate::survey::class_writes::ClassWrites;
use crate::survey::standard::changed;

/// The builtins among the modeled decorators.
const BUILTINS: [&str; 3] = ["property", "staticmethod", "classmethod"];
/// The heads of the return annotation of a context manager factory, by kind.
const SYNC_YIELDS: [&str; 4] = [
    "typing.Iterator",
    "typing.Generator",
    "collections.abc.Iterator",
    "collections.abc.Generator",
];
const ASYNC_YIELDS: [&str; 4] = [
    "typing.AsyncIterator",
    "typing.AsyncGenerator",
    "collections.abc.AsyncIterator",
    "collections.abc.AsyncGenerator",
];
/// A decorator that the survey models.
#[derive(Clone, Copy, PartialEq)]
pub(super) enum Decorator<'e> {
    Context,
    AsyncContext,
    Cache,
    Property,
    Static,
    Class,
    Wraps(&'e Expr),
    Dataclass(Option<&'e ExprCall>),
}

pub(super) struct Reader<'a> {
    pub(super) shaper: &'a Shaper<'a>,
    pub(super) names: &'a Names<'a>,
    pub(super) binders: &'a Binders,
    pub(super) writes: &'a ClassWrites,
    pub(super) module: &'a Module,
}

pub(super) fn unread(text: &str) -> Wrapped {
    Wrapped::Unread(text.to_owned())
}

/// The qualified name of a decorator, or of the head of an annotation, as the imports prove it.
pub(super) fn proven_target(
    reader: &Reader<'_>,
    expr: &Expr,
    hidden: &Hidden<'_>,
) -> Option<String> {
    match reader.names.binding(expr, hidden) {
        Binding::Imported { target } | Binding::Builtin { target } => Some(target),
        Binding::Unproven {
            cause: Unproven::Unbound,
        } => match expr {
            Expr::Name(name)
                if BUILTINS.contains(&name.id.as_str())
                    && reader.binders.builtin_visible(name.id.as_str()) =>
            {
                Some(name.id.to_string())
            }
            _ => None,
        },
        _ => None,
    }
}

/// The standard decorator of `expr`, or the reason that the survey does not read it.
pub(super) fn decorator<'e>(
    reader: &Reader<'_>,
    expr: &'e Expr,
    hidden: &Hidden<'_>,
) -> Result<Decorator<'e>, String> {
    let text = render(expr).unwrap_or_default();
    let (func, call) = match expr {
        Expr::Call(node) => (&*node.func, Some(node)),
        other => (other, None),
    };
    let Some(target) = proven_target(reader, func, hidden) else {
        return Err(format!(
            "the decorator {text} is no standard decorator that ArchKeel models"
        ));
    };
    if let Some(reason) = changed(reader.writes, &target) {
        return Err(format!(
            "the repository may change the standard decorator {target} ({reason})"
        ));
    }
    let plain = call.is_none();
    Ok(match target.as_str() {
        "contextlib.contextmanager" if plain => Decorator::Context,
        "contextlib.asynccontextmanager" if plain => Decorator::AsyncContext,
        "functools.cache" if plain => Decorator::Cache,
        "functools.lru_cache" if call.is_none_or(literal_arguments) => Decorator::Cache,
        "functools.cached_property" | "property" if plain => Decorator::Property,
        "staticmethod" if plain => Decorator::Static,
        "classmethod" if plain => Decorator::Class,
        "functools.wraps" => match call.map(|node| &node.arguments) {
            Some(arguments) if arguments.keywords.is_empty() => match &*arguments.args {
                [original] => Decorator::Wraps(original),
                _ => {
                    return Err(format!(
                        "the decorator {text} names more than the wrapped function"
                    ))
                }
            },
            _ => {
                return Err(format!(
                    "the decorator {text} is called in a form that ArchKeel does not model"
                ))
            }
        },
        "dataclasses.dataclass" => Decorator::Dataclass(call),
        _ => {
            return Err(format!(
                "the decorator {text} is called in a form that ArchKeel does not model"
            ))
        }
    })
}

/// The parameters of `node` with their written types, in the order of the signature.
pub(super) fn signature(
    reader: &Reader<'_>,
    node: &StmtFunctionDef,
    (qualname, class): (&str, Option<&HashSet<String>>),
    slots: Option<HashSet<String>>,
) -> (Vec<WrappedSlot>, TypeShape) {
    let source = Source {
        node,
        qualname: qualname.to_owned(),
        id: String::new(),
        class_names: class.cloned(),
        slots,
    };
    let (shapes, returns) = reader.shaper.signature(&source);
    let params = &node.parameters;
    let mut words: Vec<(String, &str)> = Vec::new();
    for (index, item) in params.posonlyargs.iter().chain(&params.args).enumerate() {
        let kind = if index < params.posonlyargs.len() {
            "positional_only"
        } else {
            "positional"
        };
        words.push((item.parameter.name.to_string(), kind));
    }
    words.extend(
        params
            .vararg
            .iter()
            .map(|p| (format!("*{}", p.name), "varargs")),
    );
    let keyword = params.kwonlyargs.iter();
    words.extend(keyword.map(|item| (item.parameter.name.to_string(), "keyword_only")));
    words.extend(
        params
            .kwarg
            .iter()
            .map(|p| (format!("**{}", p.name), "kwargs")),
    );
    let slot = |((name, kind), shape): ((String, &str), TypeShape)| WrappedSlot {
        name,
        kind: kind.to_owned(),
        shape: Some(shape),
    };
    (words.into_iter().zip(shapes).map(slot).collect(), returns)
}

/// The form of a decorated function or method.
pub(super) fn function(
    reader: &Reader<'_>,
    node: &StmtFunctionDef,
    (qualname, class): (&str, Option<&HashSet<String>>),
    slots: Option<HashSet<String>>,
    evidence: &str,
) -> Wrapped {
    // A decorator of a method is evaluated in the class body: its names hide the module.
    let hidden = Hidden {
        names: class.cloned().unwrap_or_default(),
        lazy: None,
    };
    let (params, returns) = signature(reader, node, (qualname, class), slots);
    let mut state = State {
        params,
        returns,
        method: class.map(|_| default_kind(node.name.as_str())),
        attribute: false,
    };
    let mut words = Vec::new();
    let innermost = node.decorator_list.len().saturating_sub(1);
    for (index, item) in node.decorator_list.iter().enumerate().rev() {
        let found = decorator(reader, &item.expression, &hidden);
        let applied = found.and_then(|found| {
            let place = (node, index == innermost, class.is_some());
            apply(reader, found, place, &hidden, &mut state)
        });
        if let Err(reason) = applied {
            return Wrapped::Unread(reason);
        }
        words.push(render(&item.expression).unwrap_or_default());
    }
    // A property keeps the receiver alone: the attribute takes no argument.
    if state.attribute {
        state.params.truncate(1);
    }
    words.reverse();
    Wrapped::Callable {
        method: state.method,
        slots: state.params,
        returns: state.returns,
        decorators: words,
        evidence: vec![evidence.to_owned()],
    }
}

/// Apply one decorator to the form; `place` is the function, whether the decorator is the
/// innermost one, and whether the function is in a class body.
fn apply(
    reader: &Reader<'_>,
    found: Decorator<'_>,
    (node, innermost, in_class): (&StmtFunctionDef, bool, bool),
    hidden: &Hidden<'_>,
    state: &mut State,
) -> Result<(), String> {
    let fail = |text: &str| Err(text.to_owned());
    if state.attribute {
        return fail("a decorator above a property is not modeled");
    }
    match found {
        Decorator::Context | Decorator::AsyncContext => {
            let wanted = found == Decorator::AsyncContext;
            if !innermost || node.is_async != wanted {
                return fail("a context manager decorator is modeled only on the function itself, with the matching async form");
            }
            state.returns = yields(reader, node.returns.as_deref(), wanted, hidden)?;
        }
        Decorator::Cache => {}
        Decorator::Static | Decorator::Class | Decorator::Property if !in_class => {
            return fail("staticmethod, classmethod and property are modeled only in a class body");
        }
        Decorator::Static => state.method = Some(MethodKind::Static),
        Decorator::Class => state.method = Some(MethodKind::Class),
        Decorator::Property => {
            let alone = state.method == Some(MethodKind::Instance) && state.params.len() == 1;
            if !alone {
                return fail(
                    "a property is modeled only on an instance method of the receiver alone",
                );
            }
            state.attribute = true;
        }
        Decorator::Wraps(original) => {
            let Some((theirs, their_returns)) = original_signature(reader, original) else {
                return fail("the wrapped function is no undecorated function of this module");
            };
            if theirs != state.params || their_returns != state.returns {
                return fail("the wrapper and the wrapped function expose different signatures");
            }
        }
        Decorator::Dataclass(_) => return fail("dataclass is modeled only on a class"),
    }
    Ok(())
}

/// The yield type of the return annotation of a context manager factory.
fn yields(
    reader: &Reader<'_>,
    annotation: Option<&Expr>,
    wanted: bool,
    hidden: &Hidden<'_>,
) -> Result<TypeShape, String> {
    let missing = "the return annotation names no iterator or generator of a yield type";
    let Some(Expr::Subscript(node)) = annotation else {
        return Err(missing.to_owned());
    };
    let Some(head) = proven_target(reader, &node.value, hidden) else {
        return Err(missing.to_owned());
    };
    let heads = if wanted { ASYNC_YIELDS } else { SYNC_YIELDS };
    if !heads.contains(&head.as_str()) {
        return Err(missing.to_owned());
    }
    if let Some(reason) = changed(reader.writes, &head) {
        return Err(format!("the repository may change {head} ({reason})"));
    }
    let first = match &*node.slice {
        Expr::Tuple(items) if head.ends_with("Generator") => items.elts.first(),
        Expr::Tuple(_) => None,
        other => Some(other),
    };
    let Some(first) = first else {
        return Err(missing.to_owned());
    };
    Ok(reader.shaper.position(Some(first), hidden))
}

/// The signature of the undecorated function of this module that `expr` names.
fn original_signature(reader: &Reader<'_>, expr: &Expr) -> Option<(Vec<WrappedSlot>, TypeShape)> {
    let Binding::Defined { target } = reader.names.binding(expr, &Hidden::default()) else {
        return None;
    };
    let name = target.strip_prefix(&format!("{}.", reader.module.name))?;
    let body = &reader.module.tree.body;
    let bound = Bound::of(body);
    let node = body.iter().find_map(|statement| match statement {
        Stmt::FunctionDef(node)
            if node.name.as_str() == name
                && node.decorator_list.is_empty()
                && bound.sole(name, statement.range().start()) =>
        {
            Some(node)
        }
        _ => None,
    })?;
    Some(signature(
        reader,
        node,
        (&target, None),
        Some(HashSet::new()),
    ))
}

/// The form of a decorated function while its decorators are applied.
struct State {
    params: Vec<WrappedSlot>,
    returns: TypeShape,
    method: Option<MethodKind>,
    attribute: bool,
}

/// The method kind of a method that no decorator changes.
fn default_kind(name: &str) -> MethodKind {
    match name {
        "__init__" => MethodKind::Constructor,
        "__new__" => MethodKind::Static,
        "__init_subclass__" | "__class_getitem__" => MethodKind::Class,
        _ => MethodKind::Instance,
    }
}

/// True for a call whose arguments are literals: `lru_cache(maxsize=128, typed=False)`.
fn literal_arguments(call: &ExprCall) -> bool {
    let literal = |expr: &Expr| {
        matches!(
            expr,
            Expr::NumberLiteral(_) | Expr::BooleanLiteral(_) | Expr::NoneLiteral(_)
        )
    };
    call.arguments.args.iter().all(literal)
        && call
            .arguments
            .keywords
            .iter()
            .all(|k| k.arg.is_some() && literal(&k.value))
}
