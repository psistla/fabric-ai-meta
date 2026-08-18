# Fixture provenance

A generated fixture sitting beside a real one is indistinguishable to the next
reader, which is the confusion this whole release exists to prevent. This file
records exactly what produced each artifact.

## Semantic models (real Power BI Desktop output)

All `*.SemanticModel` folders were produced by Microsoft Power BI Desktop with
the "Store semantic model using TMDL format" preview feature enabled, via
File > Save As > Power BI project (.pbip). TMDL envelope version is `4.2`
(`definition.pbism`); platform schema `2.0.0` (`.platform`). The two
`stix-one-pho*` models are built on the public coffee-sales CSV dataset
(`small.csv`, `large.csv`, `cards.csv`).

| Folder | Produced by | Date | Notes |
|--------|-------------|------|-------|
| `stix-one-pho.SemanticModel/definition/` | Power BI Desktop, Save As .pbip (TMDL) | 2026-07-17 | 3 tables (`Sales Order`, `SalesOrderLarge`, `cards`). Measures authored in Desktop, including `Coffee YTD`, which carries a hardcoded literal (`coffee_name = "Hot Chocolate"`) inside `TOTALYTD(CALCULATE(...))` to exercise the rule-eligible + literal-bearing case. |
| `stix-one-pho-amazon.SemanticModel/definition/` | Power BI Desktop, Save As .pbip (TMDL) | 2026-07-17 | Single `All Items` table. Deliberately has NO `Copilot/` folder, so the "Copilot absent" path is a real fixture rather than a mocked one. |
| `power-bi-stix-won-pho.SemanticModel/definition/` | Power BI Desktop, Save As .pbip (TMDL) | 2026-08-08 | A DAX-authored report showcase, not a data model: 14 tables but only 1 relationship, 65 measures, field parameters, shape maps, a Gantt table and markdown/formatting helpers, 9 of the 14 hidden. Every table is a calculated table built from inline DAX, so Power BI serializes **no `dataType` for 58 of the 60 columns** and the extractor cannot type them. Also the first fixture containing a real `calculationGroup` (`Time Calculation`), which is out of scope per constraint 5. Its gaps are pinned by the characterization tests in `test_pbip_extractor.py`; they assert current behavior, not correct behavior, and are meant to fail when the parser improves. Also carries `DAXQueries/` and `TMDLScripts/` folders that no other fixture has and the extractor does not read. |
| `city-sustainability.SemanticModel/definition/` | Power BI Desktop, Save As .pbip (TMDL) | 2026-08-17 | 6 tables, 223 measures (3.4x the previous high) in a single `_Measures` table, 2 relationships one of which is inactive, and 3 hidden parameter tables. Added because it is the first fixture where **backtick-fenced expressions** appear at scale: 182 of its 223 measures use the three-backtick verbatim form, against 2 of 65 in `power-bi-stix-won-pho`. That ratio is what exposed the parser storing the fence delimiter as the expression; at 2 measures the defect had hidden inside won-pho's already-blessed unknowns. Also 922 lines of SVG/HTML embedded in DAX. |
| `footwear-sustainability.SemanticModel/definition/` | Power BI Desktop, Save As .pbip (TMDL) | 2026-08-08 | The only fixture with a full star schema: `fact_order_line` plus six conformed dimensions, a dedicated `_Measures` table of 17 measures, and a real `dim_date` rather than Power BI's auto-generated date tables. Added specifically to cover two cases nothing else did: **balance-pattern DAX** (`CLOSINGBALANCEMONTH`, `OPENINGBALANCEMONTH`, `LASTDATE`, `FIRSTNONBLANK`), and a **table name whose dimension prefix contains a fact keyword** (`dim_factory`, where `fact` is a substring of `factory`). Both were latent bugs no other fixture could reach; see the classifier precedence fix. |

### What was stripped after export (not part of extraction, not committed)

- `.Report/` folders and top-level `.pbip` files: this release reads
  `*.SemanticModel` folders; the report layer is out of scope.
- `.pbi/` folders: contained `localSettings.json` (a machine-specific
  `securityBindingsSignature` blob that must never be committed to a public
  repo), `editorSettings.json`, and `cache.abf` (a binary Analysis Services
  cache, 168 KB to 2.5 MB, with no test value). Stripping this from
  `footwear-sustainability` alone took it from 2.6 MB to 76 KB. **Strip `.pbi/`
  before staging any new fixture; this repo is public.**
- A byte-identical duplicate item (`stix-one-pho-large`, whose
  `SemanticModel/definition/` matched `stix-one-pho` exactly) was dropped.
- `city-sustainability`'s `definition/cultures/` (1.3 MB of Q&A
  `linguisticMetadata`), which took the fixture from 1.7 MB to 442 KB. No code
  reads `cultures/`, and `power-bi-stix-won-pho` already carries the identical
  structure at 436 KB, including both `Generated` and `Suggested` term states.
  Neither model contains a single `Authored` term, so the second copy adds size
  and no coverage. `model.tmdl` still carries its `ref cultureInfo en-US`; TMDL
  ignores a ref whose file is absent. **Keep won-pho's copy**: it is the only
  on-disk sample of the linguistic schema, and the fixture that would change the
  synonym decision is one containing `"State": "Authored"`.

## Copilot folder (generated, NOT from Fabric)

Power BI Desktop does not emit a `Copilot/` folder (Prep for AI is a Fabric
service feature and there is no tenant here), so the one below was generated.

| Folder | Produced by | Date |
|--------|-------------|------|
| `stix-one-pho.SemanticModel/Copilot/` | GENERATED by `CopilotExporter().write()` from `tests/fixtures/adventure_works.copilot.json` | 2026-07-17 |

This validates that `extract(with_copilot=True)` discovers and attaches a parsed
bundle. It does NOT validate that Fabric's real on-disk Copilot emission matches
our writer's layout; that rests on the v1.1.0 TMDL/Copilot research spike, not
on any test here.
