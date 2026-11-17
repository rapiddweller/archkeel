// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The form that a standard decorator gives a definition (AD-782).
//!
//! A decorator can return any object, so a decorated definition has no record (AD-518). For the
//! premise `standard_library_unchanged` the survey states what a standard decorator returns. It
//! reads the decorator by the qualified name that the import facts prove, never by its spelling,
//! and a decorator that the repository may change is not read. The forms, applied from the
//! innermost decorator out:
//!
//! - `contextmanager`, `asynccontextmanager`: the same parameters; a call gives a context manager
//!   of the yield type, so the return is the yield type of `Iterator[Y]` or `Generator[Y, ...]`
//!   (the async forms for the async one).
//! - `cache`, `lru_cache`: the same signature.
//! - `property`, `cached_property`: an attribute of the return type (the receiver only).
//! - `staticmethod`, `classmethod`: the method kind.
//! - `wraps(original)`: the signature that a reader sees follows `original`, so it counts only when
//!   the two signatures are equal.
//! - `dataclass` on a class: the fields in order and a generated `__init__` (`init=False`,
//!   `kw_only`, `field(init=False)`, `field(kw_only=True)` and `KW_ONLY` respected).
//!
//! Any other decorator, form or body is `Unread` with the reason; the model gives a gap for it.

use std::collections::{BTreeMap, HashSet};

use archkeel_facts::standard::Wrapped;
use archkeel_facts::{ImportFact, Record};

use super::dataclass::class;
use super::found::{Decorated, Found};
use super::shapes::{imports_by_module, module_names, Shaper};
use super::wrapped_read::{function, Reader};
use crate::module::definition::Def;
use crate::module::Module;
use crate::survey::binders::Binders;
use crate::survey::class_writes::ClassWrites;

/// The forms of the decorated definitions of each module, by qualified name.
pub(crate) fn forms(
    found: &[Found<'_>],
    (modules, binders): (&[Module], &[Binders]),
    imports: &[Record<ImportFact>],
    sets: (&HashSet<String>, &HashSet<String>),
    (lazy, writes): (Option<&ClassWrites>, &ClassWrites),
) -> BTreeMap<String, Wrapped> {
    let by_module = imports_by_module(imports);
    let mut out = BTreeMap::new();
    for item in found.iter().filter(|item| !Vec::is_empty(&item.decorated)) {
        let module = &modules[item.index];
        let names = module_names(module, &binders[item.index], &by_module, sets);
        let shaper = Shaper::of(&names, lazy, module);
        let reader = Reader {
            shaper: &shaper,
            names: &names,
            binders: &binders[item.index],
            writes,
            module,
        };
        for decorated in &item.decorated {
            let found = form(&reader, decorated, &mut out);
            out.insert(decorated.qualname.clone(), found);
        }
    }
    out
}

fn form(
    reader: &Reader<'_>,
    decorated: &Decorated<'_>,
    out: &mut BTreeMap<String, Wrapped>,
) -> Wrapped {
    let evidence = &decorated.evidence;
    match decorated.def {
        Def::Function(node) => function(
            reader,
            node,
            (&decorated.qualname, decorated.class_names.as_ref()),
            decorated.slots.clone(),
            evidence,
        ),
        Def::Class(node) => class(reader, node, &decorated.qualname, evidence, out),
    }
}
