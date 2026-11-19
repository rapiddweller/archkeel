// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The data enums and trait implementations that the section module defines.

/// The data enum of a section: one variant for each kind, and the data type of that kind.
macro_rules! section_facts {
    (
        $(#[$doc:meta])*
        pub enum $name:ident in $section:ident with $data:ty { $($(#[$vdoc:meta])* $variant:ident,)* }
    ) => {
        section_facts! { $(#[$doc])* pub enum $name in $section { $($(#[$vdoc])* $variant($data),)* } }
        impl CommonData for $name {
            type Data = $data;

            fn data(&self) -> &$data {
                match self { $(Self::$variant(data) => data,)* }
            }
        }
    };
    (
        $(#[$doc:meta])*
        pub enum $name:ident in $section:ident { $($(#[$vdoc:meta])* $variant:ident($data:ty),)* }
    ) => {
        $(#[$doc])*
        #[derive(Clone, Debug, PartialEq)]
        pub enum $name {
            $($(#[$vdoc])* $variant($data),)*
        }

        impl IntoSection for $name {
            fn section(records: Vec<Record<Self>>) -> Section {
                Section::$section(records)
            }

            fn records(section: &Section) -> Option<&[Record<Self>]> {
                match section {
                    Section::$section(records) => Some(records),
                    _ => None,
                }
            }
        }

        impl FactData for $name {
            const NAME: &'static str = stringify!($name);

            fn kind(&self) -> Kind {
                match self {
                    $(Self::$variant(_) => Kind::$variant,)*
                }
            }

            fn wire_kind(&self) -> &str {
                self.kind().as_str()
            }

            fn fields(&self) -> Fields<'_> {
                match self {
                    $(Self::$variant(data) => Project::fields(data),)*
                }
            }

            fn serialize_data<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
                match self {
                    $(Self::$variant(data) => serde::Serialize::serialize(data, serializer),)*
                }
            }

            fn deserialize_data<'de, D: serde::Deserializer<'de>>(
                kind: &str,
                deserializer: D,
            ) -> Result<Self, D::Error> {
                match Kind::parse(kind) {
                    $(Some(Kind::$variant) => {
                        <$data as serde::Deserialize>::deserialize(deserializer).map(Self::$variant)
                    })*
                    _ => Err(<D::Error as serde::de::Error>::custom(format!(
                        "the kind {kind} is not a kind of {}", stringify!($name)
                    ))),
                }
            }

            fn variants(generator: &mut schemars::SchemaGenerator) -> Vec<(serde_json::Value, schemars::Schema)> {
                vec![$((
                    serde_json::json!({"const": Kind::$variant.as_str()}),
                    generator.subschema_for::<$data>(),
                ),)*]
            }
        }
    };
}
