# AD-1006 The shop repository owns its package entry point

The shop owner assigns the exact module `shop.store` to the repository component.
The module publishes `OrderRepository`. Each sibling module keeps its own owner.
A package selector would also claim the siblings.

The clean fixture passes `store:STORE-REQUIRES-COMPLETE`.
Importing `shop.store.sqlite` from the package entry point violates that rule.
The fixture matrix checks the clean and planted shop reports.
