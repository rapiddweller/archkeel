// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The standard library names that the survey states for the premise `standard_library_unchanged`
//! (AD-782).
//!
//! The premise says that code outside the scan leaves the standard library unchanged. It does not
//! cover code of the repository, so a name that a file of the repository may change is listed as
//! changed, with the reason. The names are closed tables:
//!
//! - `TYPES`: types that hold no open record: value types and markers. A mapping, `object`, a
//!   callable type or any other name of the standard library is not here: it stays a type outside
//!   the scan, because a broad type must not become an allowed leaf.
//! - the special forms of `typing` that the shape reader normalizes (#1718), from its table.
//! - the qualified collections of `shapes::COLLECTIONS`: the shape reader and a facade read them
//!   by name, so they count only under the premise too (#1718).
//! - the decorators that `declared::wrapped` models, which it names itself.

use std::collections::{BTreeMap, BTreeSet};

use archkeel_facts::standard::{StandardFacts, Wrapped};

use super::class_writes::ClassWrites;

/// The value types and markers of the standard library, by qualified name.
const TYPES: [&str; 26] = [
    "pathlib.Path",
    "pathlib.PurePath",
    "pathlib.PosixPath",
    "pathlib.WindowsPath",
    "pathlib.PurePosixPath",
    "pathlib.PureWindowsPath",
    "datetime.date",
    "datetime.datetime",
    "datetime.time",
    "datetime.timedelta",
    "datetime.timezone",
    "decimal.Decimal",
    "fractions.Fraction",
    "uuid.UUID",
    "ipaddress.IPv4Address",
    "ipaddress.IPv6Address",
    "ipaddress.IPv4Network",
    "ipaddress.IPv6Network",
    "ipaddress.IPv4Interface",
    "ipaddress.IPv6Interface",
    "re.Pattern",
    "re.Match",
    "typing.Pattern",
    "typing.Match",
    "typing.Final",
    "typing_extensions.Final",
];

/// The names that a written position reads, by `<qualified name>:<position>` (#1718).
pub(crate) type Positions = BTreeMap<String, BTreeSet<String>>;

/// Why code of the repository may change the standard library name `qualified`, if it may. A
/// builtin is an attribute of the module `builtins`.
pub(super) fn changed(writes: &ClassWrites, qualified: &str) -> Option<String> {
    let name = qualified.rsplit('.').next().unwrap_or(qualified);
    let reason = ClassWrites::change_of(writes, name)?;
    Some(reason.to_owned())
}

/// The statements of the survey: the types, the changed names among them, and the forms of the
/// decorated definitions.
pub(super) fn facts(
    writes: &ClassWrites,
    (collections, forms): (&[&str], &[&str]),
    (wrapped, positions): (BTreeMap<String, Wrapped>, Positions),
) -> StandardFacts {
    let qualified = collections.iter().filter(|name| name.contains('.'));
    let names = TYPES.iter().chain(forms).chain(qualified);
    let names = names.map(|name| (*name).to_owned());
    let mut types = BTreeSet::new();
    let mut changes = BTreeMap::new();
    for name in names {
        match changed(writes, &name) {
            Some(reason) => {
                changes.insert(name, reason);
            }
            None => {
                types.insert(name);
            }
        }
    }
    StandardFacts {
        types,
        changed: changes,
        wrapped,
        positions,
    }
}
