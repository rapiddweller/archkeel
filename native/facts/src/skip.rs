// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! Wire checks for fields omitted when their value is absent.

#[cfg(test)]
mod tests {
    use crate::data::GapData;

    #[test]
    fn gap_options_keep_their_wire_bytes() {
        let mut gap = GapData::at("why", "ns.mod");
        assert_eq!(
            serde_json::to_string(&gap).expect("JSON"),
            r#"{"reason":"why","module":"ns.mod"}"#
        );
        gap.line = Some(0);
        gap.under_type_checking = Some(false);
        assert_eq!(
            serde_json::to_string(&gap).expect("JSON"),
            r#"{"reason":"why","module":"ns.mod","line":0,"under_type_checking":false}"#
        );
        assert_eq!(
            serde_json::from_str::<GapData>(
                r#"{"reason":"why","module":"ns.mod","line":0,"under_type_checking":false}"#
            )
            .expect("decode"),
            gap
        );
    }
}
