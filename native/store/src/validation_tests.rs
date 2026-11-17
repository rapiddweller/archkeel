// Archkeel
// Copyright (c) 2026 Rapiddweller Asia Co., Ltd.
// SPDX-License-Identifier: MIT

//! The validation block of protocol 11 (AD-688) on the frozen H-typescript reply: a block can only
//! add checks, and no block lowers the language-free minimum of the store.

use serde_json::{json, Value};

use crate::validate::tests::{compressed, golden};

/// The H-typescript reply as protocol 11, with a block whose one registered set is exactly its
/// capabilities: the widest block that an honest collector could state for it.
fn eleven() -> Value {
    let mut value = golden("h-typescript");
    let capabilities = value["facts"]["capabilities"].clone();
    let constructs: Vec<Value> = capabilities["constructs"]
        .as_array()
        .into_iter()
        .flatten()
        .map(|entry| json!({"name": entry["name"], "statuses": [entry["status"]]}))
        .collect();
    value["protocol_version"] = json!("11.0.0");
    value["facts"]["validation"] = json!({
        "registered": [{
            "sections": capabilities["sections"],
            "optional_sections": [],
            "features": capabilities["resolution_features"],
            "optional_features": [],
            "constructs": constructs,
        }],
        "interface": "nothing",
        "standard_library": "archkeel-typescript-imports",
    });
    value
}

/// The refusal of both front doors, which must agree; empty when the reply is accepted.
fn refusal(value: &Value) -> String {
    let bytes = crate::ingest_reply(&compressed(value), 1 << 30)
        .err()
        .unwrap_or_default();
    let typed = match serde_json::from_value::<archkeel_facts::envelope::Reply>(value.clone()) {
        Ok(reply) => crate::ingest_typed(reply).err().unwrap_or_default(),
        Err(error) => error.to_string(),
    };
    assert_eq!(bytes, typed, "the two front doors differ");
    bytes
}

#[test]
fn a_reply_of_protocol_11_with_its_block_is_accepted() {
    assert_eq!(refusal(&eleven()), "");
}

#[test]
fn the_block_and_the_protocol_go_together() {
    let mut without = eleven();
    without["facts"]
        .as_object_mut()
        .map(|facts| facts.remove("validation"));
    assert_eq!(
        refusal(&without),
        "a protocol 11.0.0 reply needs its validation block (AD-688)"
    );
    let mut old = eleven();
    old["protocol_version"] = json!("9.0.0");
    assert_eq!(
        refusal(&old),
        "only a protocol 11.0.0 reply carries a validation block (AD-688)"
    );
    // The reader of the transition: a 9.0.0 reply without a block keeps its profile checks.
    assert_eq!(refusal(&golden("h-typescript")), "");
}

#[test]
fn the_capabilities_must_be_one_registered_set_of_the_block() {
    let mut fewer = eleven();
    let features = &mut fewer["facts"]["validation"]["registered"][0]["features"];
    features.as_array_mut().map(Vec::pop);
    assert_eq!(
        refusal(&fewer),
        "source sections or resolution features are not registered"
    );
    let mut status = eleven();
    status["facts"]["validation"]["registered"][0]["constructs"][0]["statuses"] =
        json!(["supported"]);
    assert_eq!(
        refusal(&status),
        "source sections or resolution features are not registered"
    );
    let mut none = eleven();
    none["facts"]["validation"]["registered"] = json!([]);
    assert_eq!(
        refusal(&none),
        "source sections or resolution features are not registered"
    );
}

/// The plant of the owner decision: a block cannot widen what the store checks. A registered set
/// that names a feature the store does not check is refused, whatever the reply states.
#[test]
fn a_block_cannot_add_a_feature_that_the_store_does_not_check() {
    let mut value = eleven();
    value["facts"]["validation"]["registered"][0]["optional_features"] = json!(["eval-v1"]);
    assert_eq!(
        refusal(&value),
        "the store does not check the resolution feature eval-v1 yet"
    );
    let mut interface = eleven();
    interface["facts"]["validation"]["interface"] = json!({"feature": "eval-v1"});
    assert_eq!(
        refusal(&interface),
        "the store does not check the resolution feature eval-v1 yet"
    );
}

/// The plant of the owner decision: a reply that claims fewer required features cannot lower the
/// symbol rule of the store. The block requires no routes feature, the reply drops it, and the
/// store still refuses a symbol statement without its feature.
#[test]
fn a_block_with_fewer_required_features_cannot_lower_the_symbol_rule() {
    let mut value = eleven();
    let fewer: Vec<Value> = value["facts"]["capabilities"]["resolution_features"]
        .as_array()
        .into_iter()
        .flatten()
        .filter(|feature| *feature != "script-globals-v1")
        .cloned()
        .collect();
    value["facts"]["capabilities"]["resolution_features"] = json!(fewer);
    value["facts"]["validation"]["registered"][0]["features"] = json!(fewer);
    let mut reply: archkeel_facts::envelope::Reply = serde_json::from_value(value).unwrap();
    reply.facts.profile_limits = Some(archkeel_facts::envelope::ProfileLimits {
        dependency_symbols: archkeel_facts::envelope::LimitSupport::Supported,
        interface_boundary: archkeel_facts::envelope::LimitSupport::Supported,
    });
    assert_eq!(
        crate::ingest_typed(reply).err().unwrap_or_default(),
        "profile symbol statement does not match its capability"
    );
}

#[test]
fn the_standard_library_key_names_the_family_of_the_adapter_and_the_runtime() {
    let mut other = eleven();
    other["facts"]["validation"]["standard_library"] = json!("archkeel-rust-imports");
    assert_eq!(
        refusal(&other),
        "the standard library archkeel-rust-imports is not a list of the adapter \
         archkeel-typescript-imports"
    );
    let mut minor = eleven();
    minor["facts"]["validation"]["standard_library"] = json!("archkeel-typescript-imports@3.11");
    assert_eq!(
        refusal(&minor),
        "the standard library archkeel-typescript-imports@3.11 is not the list of the runtime 1.88.0"
    );
    minor["facts"]["validation"]["standard_library"] = json!("archkeel-typescript-imports@1.88");
    assert_eq!(refusal(&minor), "");
}

#[test]
fn an_interface_statement_agrees_with_the_need_of_the_block() {
    let stated = |need: Value, interface: bool| {
        let mut value = eleven();
        value["facts"]["validation"]["interface"] = need;
        let mut reply: archkeel_facts::envelope::Reply = serde_json::from_value(value).unwrap();
        reply.facts.profile_limits = Some(archkeel_facts::envelope::ProfileLimits {
            dependency_symbols: archkeel_facts::envelope::LimitSupport::Supported,
            interface_boundary: if interface {
                archkeel_facts::envelope::LimitSupport::Supported
            } else {
                archkeel_facts::envelope::LimitSupport::Unsupported
            },
        });
        crate::ingest_typed(reply).err().unwrap_or_default()
    };
    assert_eq!(stated(json!("nothing"), true), "");
    assert_eq!(
        stated(json!("unsupported"), true),
        "the collector makes no interface statement"
    );
    assert_eq!(stated(json!("unsupported"), false), "");
    let routes = json!({"feature": "script-globals-v1"});
    assert_eq!(stated(routes.clone(), true), "");
    assert_eq!(
        stated(routes, false),
        "an interface statement holds exactly with the feature script-globals-v1"
    );
}
