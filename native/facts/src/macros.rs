// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The macros for a closed vocabulary and a record data type with its read-set.

/// A closed vocabulary: the enum, its JSON text, `ALL`, `as_str` and `parse`.
macro_rules! closed {
    (
        $(#[$doc:meta])*
        pub enum $name:ident { $($(#[$vdoc:meta])* $variant:ident = $text:literal,)* }
    ) => {
        $(#[$doc])*
        #[derive(
            Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash,
            serde::Serialize, serde::Deserialize, schemars::JsonSchema,
        )]
        pub enum $name {
            $($(#[$vdoc])* #[serde(rename = $text)] $variant,)*
        }

        impl $name {
            /// Each value, in the order of the declaration.
            pub const ALL: &'static [Self] = &[$(Self::$variant),*];

            /// The JSON text of the value.
            pub fn as_str(self) -> &'static str {
                match self {
                    $(Self::$variant => $text,)*
                }
            }

            /// The value of a JSON text, or `None` when the vocabulary does not hold it.
            pub fn parse(text: &str) -> Option<Self> {
                match text {
                    $($text => Some(Self::$variant),)*
                    _ => None,
                }
            }
        }
    };
}

/// The data of a record kind. Each field carries a mark list `[mode mark "key"]`:
///
/// 1. `read` or `wire`: a rule or a view reads the field for some kind of this type (WP1), or no
///    reader reads it. The mark is a record of that survey; no code uses it.
/// 2. `skip` (`Option`) or `skip_nullable` (`Nullable`): omit the field when it is absent.
///    `required`: the wire holds the field as a key that may be null.
///    `never`: the wire does not hold the field.
/// 3. `"key"`: the JSON name of the field, for a name that is a Rust keyword.
///
/// The macro writes the `serde` attributes of each field from its marks. The wire form (`serde`)
/// writes each field in the order of the declaration.
macro_rules! facts_data {
    (
        $(#[$doc:meta])*
        pub struct $name:ident {
            $($(#[$fdoc:meta])* [$mode:ident $($mark:ident)? $($key:literal)?] $field:ident : $ty:ty,)*
        }
    ) => {
        facts_data!(@fields pub [$(#[$doc])* $name] [] $([$($mark)? $($key)?] [$(#[$fdoc])*] $field : $ty,)*);
    };
    // The fields, one by one, each with its document and its `serde` attributes. The last step
    // writes the type.
    (@fields $v:tt [$(#[$doc:meta])* $name:ident] [$($done:tt)*]) => {
        $(#[$doc])*
        #[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
        #[serde(deny_unknown_fields)]
        pub struct $name { $($done)* }
    };
    (@fields $v:tt $head:tt $done:tt [skip $($key:literal)?] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done
            [#[serde($(rename = $key,)? default, skip_serializing_if = "Option::is_none")]]
            $fd $($rest)*);
    };
    (@fields $v:tt $head:tt $done:tt [skip_nullable $($key:literal)?] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done
            [#[serde($(rename = $key,)? default, skip_serializing_if = "crate::nullable::Nullable::is_absent")]]
            $fd $($rest)*);
    };
    (@fields $v:tt $head:tt $done:tt [required] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done
            [#[serde(deserialize_with = "crate::nullable::required")] #[schemars(required)]]
            $fd $($rest)*);
    };
    (@fields $v:tt $head:tt $done:tt [never] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done [#[serde(skip)]] $fd $($rest)*);
    };
    (@fields $v:tt $head:tt $done:tt [$key:literal] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done [#[serde(rename = $key)]] $fd $($rest)*);
    };
    (@fields $v:tt $head:tt $done:tt [] $fd:tt $($rest:tt)*) => {
        facts_data!(@push $v $head $done [] $fd $($rest)*);
    };
    (@push $v:tt $head:tt [$($done:tt)*] [$($attr:tt)*] [$($fd:tt)*] $field:ident : $ty:ty, $($rest:tt)*) => {
        facts_data!(@fields $v $head [$($done)* $($fd)* $($attr)* $v $field: $ty,] $($rest)*);
    };
}
