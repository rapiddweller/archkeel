# AD-86 Root layout allows only declared immediate children

`root_layout` is an exact allow-list for the immediate package or module names below `root`.
The root module itself is ignored; a missing allowed child is not a finding. Each observed
unexpected child is a normal baselineable violation. Adding a child widens the contract,
removing one narrows it; adding the rule narrows the contract and removing it widens it.

The rule is typed in `ArchitectureRule`, decoded by the contract codec, and evaluated from the
existing package and module facts. No second filesystem walk is needed.
