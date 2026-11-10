// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The three macros that keep each fact type one definition: a closed vocabulary, a record data
//! type with its read-set, and the data enum of a section.

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

/// The data of a record kind. Each field carries two marks:
///
/// 1. `read` or `wire`: a rule or a view reads the field for some kind of this type (WP1), or no
///    reader reads it. The read-set writes a `read` field only when the list of the area and the
///    kind holds it (`readset_fields`).
/// 2. `skip`: the wire omits the field when it is absent. The read-set omits it too.
///
/// The wire form (`serde`) writes each field in the order of the declaration. A `[read "name"]`
/// field gives its JSON name, for a field that is a Rust keyword.
macro_rules! facts_data {
    (
        $(#[$doc:meta])*
        pub struct $name:ident {
            $([$mode:ident $($skip:ident)? $($key:literal)?] $(#[$attr:meta])* $field:ident : $ty:ty,)*
        }
    ) => {
        $(#[$doc])*
        #[derive(Clone, Debug, PartialEq, serde::Serialize, serde::Deserialize, schemars::JsonSchema)]
        #[serde(deny_unknown_fields)]
        pub struct $name {
            $($(#[$attr])* pub $field: $ty,)*
        }

        impl $crate::readset::ReadFields for $name {
            // A type with no read field does not use the map or the list.
            #[allow(unused_variables)]
            fn read_fields<M: serde::ser::SerializeMap>(
                &self,
                map: &mut M,
                reads: $crate::readset::Reads,
            ) -> Result<(), M::Error> {
                $(facts_data!(@entry $mode $($skip)? [map self reads $field] $($key)?);)*
                Ok(())
            }
        }
    };
    (@entry read skip [$map:ident $self:ident $reads:ident $field:ident] $($key:literal)?) => {
        if $crate::readset::Present::present(&$self.$field) {
            facts_data!(@entry read [$map $self $reads $field] $($key)?)
        }
    };
    (@entry read [$map:ident $self:ident $reads:ident $field:ident] $key:literal) => {
        if $crate::readset::allowed($reads, $key) {
            $map.serialize_entry($key, &$self.$field)?
        }
    };
    (@entry read [$map:ident $self:ident $reads:ident $field:ident]) => {
        if $crate::readset::allowed($reads, stringify!($field)) {
            $map.serialize_entry(stringify!($field), &$self.$field)?
        }
    };
    (@entry wire $($skip:ident)? [$($rest:tt)*] $($key:literal)?) => {};
}

/// The data enum of a section: one variant for each kind, and the data type of that kind.
macro_rules! section_facts {
    (
        $(#[$doc:meta])*
        pub enum $name:ident in $section:ident { $($variant:ident($data:ty),)* }
    ) => {
        $(#[$doc])*
        #[derive(Clone, Debug, PartialEq)]
        pub enum $name {
            $($variant($data),)*
        }

        impl $crate::sections::IntoSection for $name {
            fn section(records: Vec<$crate::record::Record<Self>>) -> $crate::sections::Section {
                $crate::sections::Section::$section(records)
            }
        }

        impl $crate::record::FactData for $name {
            const NAME: &'static str = stringify!($name);

            fn kind(&self) -> $crate::vocab::Kind {
                match self {
                    $(Self::$variant(_) => $crate::vocab::Kind::$variant,)*
                }
            }

            fn wire_kind(&self) -> &str {
                self.kind().as_str()
            }

            fn serialize_data<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
                match self {
                    $(Self::$variant(data) => serde::Serialize::serialize(data, serializer),)*
                }
            }

            fn read_set_entries<M: serde::ser::SerializeMap>(
                &self,
                map: &mut M,
                reads: $crate::readset::Reads,
            ) -> Result<(), M::Error> {
                match self {
                    $(Self::$variant(data) => $crate::readset::ReadFields::read_fields(data, map, reads),)*
                }
            }

            fn deserialize_data<'de, D: serde::Deserializer<'de>>(
                kind: &str,
                deserializer: D,
            ) -> Result<Self, D::Error> {
                match $crate::vocab::Kind::parse(kind) {
                    $(Some($crate::vocab::Kind::$variant) => {
                        <$data as serde::Deserialize>::deserialize(deserializer).map(Self::$variant)
                    })*
                    _ => Err(<D::Error as serde::de::Error>::custom(format!(
                        "the kind {kind} is not a kind of {}", stringify!($name)
                    ))),
                }
            }

            fn variants(generator: &mut schemars::SchemaGenerator) -> Vec<(serde_json::Value, schemars::Schema)> {
                vec![$((
                    serde_json::json!({"const": $crate::vocab::Kind::$variant.as_str()}),
                    generator.subschema_for::<$data>(),
                ),)*]
            }
        }
    };
}
