# AD-618: The report draws one page for a system

Status: accepted (owner order). Part of #880. It amends AD-616 item 4 and item 5.

`archkeel report --config docs/architecture/architecture-system.json --output page.html` writes one
page for the whole system. The page decides nothing: the core joins the data, and the page draws it.

1. A system run accepts the page and the topology. Each part runs with its topology; the baseline
   stays refused for a system run.
2. The topology of the system has one top component for each part (`PART:<id>`), named by the title
   of the part. The top components of the contract of the part sit inside it. A component id, a
   module name or a rule id that two parts use refuses the run: no id names two things.
3. The language of each module is the collector value of its part. A part box names the profile of
   its part; the Language perspective of the Explorer lists each language.
4. The tree of the Explorer draws the layers of a part inside its part box (the children of a scope
   that all name a layer of one layer order), as it did for a single run at the top.
5. The verdict of a part box is the weakest verdict inside it (FAIL, then UNKNOWN, then PASS) and the
   verdict of the system is `report::system_status` (AD-616). A gap that no box owns holds each box.
6. `explain` joins by rule id; the counts and flags of `holds` add up.

Limit: `tools/report_product.py` still joins for the page of the gallery; it can go in a later step.
