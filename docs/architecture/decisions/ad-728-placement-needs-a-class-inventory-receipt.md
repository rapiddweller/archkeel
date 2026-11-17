# AD-728: Placement needs a class inventory receipt

## Status

Accepted for the `symbol_placement` port in #619.

## Decision

A proven class of a selected kind outside the allowed modules is a violation even when another
class inventory is incomplete. A pass needs a receipt proving the written class inventory empty
for every selected module outside the allowed modules. An absent receipt is unread, not empty.
The usual scope, coverage and gap checks still apply.

The initial receipt is deliberately narrow (AD-726). A module containing a class does not get
an empty-inventory receipt, even when all of its known classes are allowed by kind. Such a
placement stays UNKNOWN unless a known violation makes it FAIL.

## Amendment (#1713)

A call that can create a class at run time (a standard-library factory, a metaclass shape, or a
call result that the module uses as a class) withholds the receipt. The UNKNOWN names its site
(`FileFact.class_inventory_site`, `Cause::ClassSite`). See `docs/known-limits.md`.

## Checks

The placement plants exercise PASS, FAIL, incomplete inventories and a known violation beside
an unread class.
