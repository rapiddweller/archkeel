# AD-152 Validated construct identity controls rules

Replacement collectors carry a typed `data.construct` and a descriptive record
kind. Core validates capabilities using the construct, so rules must use that
same identity. Dispatching on the kind can hide an accepted assert fact.

Use the validated construct for rule evaluation. Retain legacy kind mapping only
for older typing signals without a construct field. Preserve record spelling,
source exemptions, capability refusal and traceable violation evidence.

Rejecting alternative descriptive kinds would restrict the replaceable port
without adding proof. Two independent identities would retain the false PASS.

`tests/test_collection_capabilities.py` covers normal, renamed and conflicting
kinds through decoding and observation, with a negative GETATTR control.
