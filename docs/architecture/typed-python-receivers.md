# Python receiver evidence origins

The Python Source component's existing receiver_types module owns ReceiverOrigin:
literal values, annotations and documented library returns are separate evidence.
ReceiverType retains its import path and constructor parameters. Valid legacy origin
strings are normalized once to the nominal Enum; Origin remains a type alias.
Invalid values raise ValueError and already nominal inputs retain their identity.

Calls produces and merges these origins; resolve keys the existing verdict table by
the owned type. Literal evidence keeps its resolved verdict. Annotated/documented
evidence remains partially resolved with the same reason text and call wire values.
Conflicting types, voided bindings and shadowed builtin constructors remain unresolved.

The inner Python Target requires the nominal origin field and frozen ReceiverType.
A complete-module raw-control guard protects receiver_types; it does not certify all
remaining grammar in calls/resolve. Names and documented method tables remain data.
No namespace, descriptor, GenericAlias or compiler proof authority is added.
