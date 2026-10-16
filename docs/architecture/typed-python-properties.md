# Typed Python property proof

Issue [#542](https://github.com/rapiddweller/archkeel/issues/542), property sub-scope.

The source-facts owner defines immutable `PropertyBinding`, `PropertyOperation`
and `PropertyOrigin`. Source classifies standard property decorator syntax into
these types; Core consumes the same types after the source-record boundary.
The existing descriptor, binding order, owner and inherited-accessor proof
conditions remain authoritative. A nominal category never supplies missing proof.

`facts.property_binding` reads the existing four-field property record.
`facts_codec.property_binding_data` only writes those same four JSON fields.
There is no protocol version change, new property syntax or resolver authority.
The old private `source._PropertyBinding` TypedDict constructor remains a real
dict for valid mapping/keyword callers; actual property producers use the new
immutable type. These are distinct wire and domain responsibilities.

The IR Target pins the actual nominal fields and decoder/writer ports. The
Python Target pins the actual Source producer's return type. Native mutations
widen these declarations without updating either Target. Existing whole-module
facts and facts-codec guards protect their closed-control decisions. Scoped
native Source/Core observations cover the property functions only: unrelated
raw annotation/compiler/proof controls in those large modules remain outside
this stage. No whole-Source or whole-Core guard PASS is claimed.

Within Core's two property functions the pre-existing record-kind `method`
comparison and `property_binding` JSON-key presence tests remain separate
control/data forms. The native property scope asserts operation/origin values
and enum-value extraction, without certifying those entire functions.
