// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The shape of each written type of a signature (AD-550): the annotation of a parameter and the
//! return annotation of each function and method that has a record.
//!
//! The shape is read from the syntax. It keeps no text that the model must parse, and it states a
//! binding only when `shape_names` proves it. A form that the collector does not model (a call, a
//! callable type, a list of types) is `Unreadable` and a user generic is `Applied`: the model reads
//! both as a named gap and never as a plain type.

use std::collections::{HashMap, HashSet};

use archkeel_facts::type_shape::{Binding, Family, TypeShape, Unreadable};
use archkeel_facts::{ImportFact, Record, SymbolFact};
use ruff_python_ast::{Expr, Number, Operator, UnaryOp};

use super::found::{Found, Source};
use super::scope::type_names;
use super::shape_names::Names;
use super::shape_text::render;
use crate::module::Module;
use crate::survey::binders::Binders;

/// The deepest type expression that the reader follows.
const MAX_DEPTH: u32 = 24;

/// The primitives among the builtin classes.
const PRIMITIVES: [&str; 6] = ["int", "str", "bytes", "bool", "float", "complex"];

/// The collections of the language and of its standard library, by qualified name.
const COLLECTIONS: &[(&str, Family)] = &[
    ("list", Family::Sequence),
    ("set", Family::Sequence),
    ("frozenset", Family::Sequence),
    ("tuple", Family::Sequence),
    ("dict", Family::Mapping),
    ("typing.List", Family::Sequence),
    ("typing.Set", Family::Sequence),
    ("typing.FrozenSet", Family::Sequence),
    ("typing.Tuple", Family::Sequence),
    ("typing.Sequence", Family::Sequence),
    ("typing.MutableSequence", Family::Sequence),
    ("typing.Iterable", Family::Sequence),
    ("typing.Iterator", Family::Sequence),
    ("typing.Collection", Family::Sequence),
    ("typing.AbstractSet", Family::Sequence),
    ("typing.MutableSet", Family::Sequence),
    ("typing.Deque", Family::Sequence),
    ("typing.Dict", Family::Mapping),
    ("typing.Mapping", Family::Mapping),
    ("typing.MutableMapping", Family::Mapping),
    ("typing.DefaultDict", Family::Mapping),
    ("typing.OrderedDict", Family::Mapping),
    ("typing_extensions.OrderedDict", Family::Mapping),
    ("collections.abc.Sequence", Family::Sequence),
    ("collections.abc.MutableSequence", Family::Sequence),
    ("collections.abc.Iterable", Family::Sequence),
    ("collections.abc.Iterator", Family::Sequence),
    ("collections.abc.Collection", Family::Sequence),
    ("collections.abc.Set", Family::Sequence),
    ("collections.abc.MutableSet", Family::Sequence),
    ("collections.abc.Mapping", Family::Mapping),
    ("collections.abc.MutableMapping", Family::Mapping),
    ("collections.deque", Family::Sequence),
    ("collections.defaultdict", Family::Mapping),
    ("collections.OrderedDict", Family::Mapping),
    ("typing_extensions.List", Family::Sequence),
    ("typing_extensions.Dict", Family::Mapping),
    ("typing_extensions.Sequence", Family::Sequence),
    ("typing_extensions.Mapping", Family::Mapping),
    ("typing_extensions.Iterable", Family::Sequence),
];

/// The special forms of `typing` that the shape normalizes.
#[derive(Clone, Copy, PartialEq, Eq)]
enum Form {
    Optional,
    Union,
    Annotated,
    Literal,
    Any,
}

fn form(target: &str) -> Option<Form> {
    let (module, name) = target.rsplit_once('.')?;
    if module != "typing" && module != "typing_extensions" {
        return None;
    }
    Some(match name {
        "Optional" => Form::Optional,
        "Union" => Form::Union,
        "Annotated" => Form::Annotated,
        "Literal" => Form::Literal,
        "Any" => Form::Any,
        _ => return None,
    })
}

/// The reader of the written types of one module.
pub(super) struct Shaper<'a> {
    pub(super) names: &'a Names<'a>,
}

impl Shaper<'_> {
    /// The shapes of the positions of `source`: one for each parameter in the order of the
    /// signature, and the return.
    pub(super) fn signature(&self, source: &Source<'_>) -> (Vec<TypeShape>, TypeShape) {
        let mut hidden: HashSet<String> = source.class_names.clone().unwrap_or_default();
        hidden.extend(type_names(source.node));
        let params = &source.node.parameters;
        let positional = params.posonlyargs.iter().chain(&params.args);
        let mut found: Vec<TypeShape> = positional
            .map(|item| self.position(item.parameter.annotation.as_deref(), &hidden))
            .collect();
        found.extend(
            params
                .vararg
                .iter()
                .map(|item| self.position(item.annotation.as_deref(), &hidden)),
        );
        found.extend(
            params
                .kwonlyargs
                .iter()
                .map(|item| self.position(item.parameter.annotation.as_deref(), &hidden)),
        );
        found.extend(
            params
                .kwarg
                .iter()
                .map(|item| self.position(item.annotation.as_deref(), &hidden)),
        );
        let returns = self.position(source.node.returns.as_deref(), &hidden);
        (found, returns)
    }

    fn position(&self, annotation: Option<&Expr>, hidden: &HashSet<String>) -> TypeShape {
        annotation.map_or(TypeShape::Unannotated {}, |expr| {
            self.shape(expr, hidden, 0)
        })
    }

    fn shape(&self, expr: &Expr, hidden: &HashSet<String>, depth: u32) -> TypeShape {
        if depth > MAX_DEPTH {
            return unreadable(String::new(), Unreadable::TooDeep);
        }
        let Some(text) = render(expr) else {
            return unreadable(String::new(), Unreadable::TextUnwritable);
        };
        match expr {
            Expr::NoneLiteral(_) => TypeShape::Nothing {},
            Expr::StringLiteral(node) => self.quoted(node.value.to_str(), text, hidden),
            Expr::Name(_) | Expr::Attribute(_) => self.named(expr, text, hidden),
            Expr::Subscript(node) => self.applied(&node.value, &node.slice, text, hidden, depth),
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                let mut arms = Vec::new();
                self.arms(expr, hidden, depth, &mut arms);
                TypeShape::Union { text, arms }
            }
            _ => unreadable(text, Unreadable::NotATypeForm),
        }
    }

    /// The arms of a chain `A | B | C`, flattened.
    fn arms(&self, expr: &Expr, hidden: &HashSet<String>, depth: u32, out: &mut Vec<TypeShape>) {
        match expr {
            Expr::BinOp(node) if node.op == Operator::BitOr => {
                self.arms(&node.left, hidden, depth + 1, out);
                self.arms(&node.right, hidden, depth + 1, out);
            }
            other => out.push(self.shape(other, hidden, depth + 1)),
        }
    }

    /// A string annotation. Only a builtin that no statement hides reads as itself, as in
    /// release 4.0.1; any other string is a forward reference that nothing here resolves.
    fn quoted(&self, value: &str, text: String, hidden: &HashSet<String>) -> TypeShape {
        let word = value.trim();
        if (word == "str" || word == "object")
            && matches!(self.names.name(word, hidden), Binding::Builtin { .. })
        {
            return builtin(word, word.to_owned());
        }
        TypeShape::Forward { text }
    }

    fn named(&self, expr: &Expr, text: String, hidden: &HashSet<String>) -> TypeShape {
        let binding = self.names.binding(expr, hidden);
        match &binding {
            Binding::Builtin { target } if PRIMITIVES.contains(&target.as_str()) => {
                TypeShape::Primitive {
                    name: target.clone(),
                    text,
                }
            }
            Binding::Builtin { target } if target == "object" => TypeShape::Dynamic {
                name: target.clone(),
                text,
            },
            Binding::Builtin { target } | Binding::Imported { target } => {
                if form(target) == Some(Form::Any) {
                    return TypeShape::Dynamic {
                        name: "Any".to_owned(),
                        text,
                    };
                }
                match collection(target) {
                    Some((family, name)) => TypeShape::Collection {
                        text,
                        family,
                        name,
                        args: Vec::new(),
                        open_end: false,
                    },
                    None => TypeShape::Named { text, binding },
                }
            }
            _ => TypeShape::Named { text, binding },
        }
    }

    fn applied(
        &self,
        head: &Expr,
        slice: &Expr,
        text: String,
        hidden: &HashSet<String>,
        depth: u32,
    ) -> TypeShape {
        let args: Vec<&Expr> = match slice {
            Expr::Tuple(node) => node.elts.iter().collect(),
            other => vec![other],
        };
        let binding = match head {
            Expr::Name(_) | Expr::Attribute(_) => Some(self.names.binding(head, hidden)),
            _ => None,
        };
        let target = match &binding {
            Some(Binding::Builtin { target } | Binding::Imported { target }) => Some(target),
            _ => None,
        };
        let shapes = |items: &[&Expr]| -> Vec<TypeShape> {
            items
                .iter()
                .map(|item| self.shape(item, hidden, depth + 1))
                .collect()
        };
        if let Some(found) = target.and_then(|target| form(target)) {
            match (found, args.as_slice()) {
                (Form::Optional, [one]) => {
                    let arms = vec![self.shape(one, hidden, depth + 1), TypeShape::Nothing {}];
                    return TypeShape::Union { text, arms };
                }
                (Form::Union, items) if !items.is_empty() => {
                    return TypeShape::Union {
                        text,
                        arms: shapes(items),
                    };
                }
                (Form::Annotated, [first, _, ..]) => {
                    return TypeShape::Annotated {
                        text,
                        inner: Box::new(self.shape(first, hidden, depth + 1)),
                    };
                }
                (Form::Literal, items) if !items.is_empty() => {
                    let plain = items.iter().all(|item| plain_constant(item));
                    return TypeShape::Literal { text, plain };
                }
                _ => {}
            }
        }
        if let Some((family, name)) = target.and_then(|target| collection(target)) {
            return collection_shape(text, (family, name), &args, &shapes);
        }
        let head_shape = self.shape(head, hidden, depth + 1);
        TypeShape::Applied {
            text,
            head: Box::new(head_shape),
            args: shapes(&args),
        }
    }
}

fn collection_shape(
    text: String,
    (family, name): (Family, String),
    args: &[&Expr],
    shapes: &dyn Fn(&[&Expr]) -> Vec<TypeShape>,
) -> TypeShape {
    let open_end = family == Family::Sequence
        && name.eq_ignore_ascii_case("tuple")
        && matches!(args, [_, Expr::EllipsisLiteral(_)]);
    let counted = if open_end { &args[..1] } else { args };
    let empty = args.is_empty();
    if empty
        || args
            .iter()
            .any(|item| matches!(item, Expr::EllipsisLiteral(_)))
            && !open_end
    {
        return unreadable(text, Unreadable::NotATypeForm);
    }
    TypeShape::Collection {
        text,
        family,
        name,
        args: shapes(counted),
        open_end,
    }
}

fn collection(target: &str) -> Option<(Family, String)> {
    let (_, family) = COLLECTIONS.iter().find(|(name, _)| *name == target)?;
    let name = target.rsplit('.').next().unwrap_or(target);
    Some((*family, name.to_owned()))
}

fn plain_constant(expr: &Expr) -> bool {
    match expr {
        Expr::StringLiteral(_)
        | Expr::BytesLiteral(_)
        | Expr::BooleanLiteral(_)
        | Expr::NoneLiteral(_) => true,
        Expr::NumberLiteral(node) => matches!(node.value, Number::Int(_)),
        Expr::UnaryOp(node) => {
            node.op == UnaryOp::USub
                && matches!(&*node.operand, Expr::NumberLiteral(inner) if matches!(inner.value, Number::Int(_)))
        }
        _ => false,
    }
}

fn builtin(name: &str, text: String) -> TypeShape {
    if name == "object" {
        TypeShape::Dynamic {
            text,
            name: name.to_owned(),
        }
    } else {
        TypeShape::Primitive {
            text,
            name: name.to_owned(),
        }
    }
}

fn unreadable(text: String, cause: Unreadable) -> TypeShape {
    TypeShape::Unreadable { text, cause }
}

/// Write the shapes of the signature of each source of each module into its record. A record
/// whose parameters do not match the signature of its source gets none: the model then reads the
/// shapes as not written.
pub(crate) fn attach(
    found: &mut [Found<'_>],
    (modules, binders): (&[Module], &[Binders]),
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
) {
    let mut by_module: HashMap<&str, Vec<&Record<ImportFact>>> = HashMap::new();
    for record in imports {
        by_module
            .entry(record.data.data().source_module.as_str())
            .or_default()
            .push(record);
    }
    for item in found {
        let module = &modules[item.index];
        let own = by_module.get(module.name.as_str());
        let names = Names::of(
            (&module.name, &module.tree),
            &binders[item.index],
            own.map_or(&[][..], Vec::as_slice),
            sets,
        );
        let shaper = Shaper { names: &names };
        let at: HashMap<&str, usize> = item
            .records
            .iter()
            .enumerate()
            .map(|(index, record)| (record.id.as_str(), index))
            .collect();
        let mut written = Vec::new();
        for source in &item.sources {
            if let Some(&index) = at.get(source.id.as_str()) {
                written.push((index, shaper.signature(source)));
            }
        }
        for (index, (shapes, returns)) in written {
            let (SymbolFact::Function(data) | SymbolFact::Method(data)) =
                &mut item.records[index].data
            else {
                continue;
            };
            if shapes.len() != data.parameters.len() {
                continue;
            }
            for (parameter, shape) in data.parameters.iter_mut().zip(shapes) {
                parameter.shape = Some(shape);
            }
            data.returns_shape = Some(returns);
        }
    }
}

#[cfg(test)]
#[path = "shapes_tests.rs"]
mod tests;
