# Spike: Programmatic Read/Write of Prep for AI Settings

> **Status:** Initial hypothesis was wrong. This document was rewritten after verifying against Microsoft Learn and the Fabric REST API reference. The corrected position is below; see "Original hypothesis (falsified)" at the end for what was retracted.

---

## TL;DR

Prep for AI primitives (AI Instructions, AI Data Schema, Verified Answers) are **not** stored in TMDL. They live in a `Copilot/` folder that sits **alongside** the `definition/` folder inside a semantic model, as Markdown and JSON files. Microsoft Learn refers to this storage layer as "the LSDL" in prose, but the on-disk and on-the-wire representation is the `Copilot/` tree (Markdown + JSON), not a single `.lsdl.yaml` file.

The Fabric REST API endpoints `getDefinition` and `updateDefinition` return and accept the `Copilot/` parts as base64-encoded files in the same payload that carries TMDL parts. A read-modify-write loop for AI Instructions, AI Data Schema, and Verified Answers is therefore feasible through the existing definition endpoints, with caveats around refresh latency and full-payload replacement semantics.

---

## What lives where

```
{semanticModel}/
├── definition/                              <- TMDL: tables, columns, measures, relationships, etc.
│   ├── model.tmdl
│   ├── tables/Sales.tmdl
│   ├── relationships.tmdl
│   └── ...
├── Copilot/                                 <- Prep for AI primitives (referred to as "LSDL" in Learn prose)
│   ├── Instructions/
│   │   └── instructions.md                  <- AI Instructions (Markdown)
│   ├── schema.json                          <- AI Data Schema (which tables / columns AI can see)
│   ├── examplePrompts.json                  <- Suggested prompts shown to users
│   ├── VerifiedAnswers/                     <- Verified Answers (one file per answer)
│   ├── settings.json                        <- Copilot toggles, behavior flags
│   └── version.json                         <- Schema version of the Copilot folder
├── definition.pbism                         <- Dataset settings (qnaEnabled flag, etc.)
├── diagramLayout.json
└── .pbi/, .platform                         <- Project metadata
```

The `Copilot/` folder is sibling to `definition/`, not nested inside it. TMDL parsers and writers (Tabular Editor, the official Power BI Modeling MCP server, our `SemanticLinkWriter`) operate on `definition/` and do not touch `Copilot/`.

---

## Q1. Are AI Instructions in the TMDL definition? **No.**

`Copilot/Instructions/instructions.md` (Markdown). Returned by `getDefinition` as a sibling part to TMDL parts, with `path = "Copilot/Instructions/instructions.md"` and base64-encoded payload.

Source: [Fabric REST: SemanticModel definition](https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/semantic-model-definition).

## Q2. Are Verified Answers in the TMDL definition? **No.**

`Copilot/VerifiedAnswers/` directory; one file per verified answer, returned as separate parts. Same envelope as Q1.

Source: same as Q1.

## Q3. What format are they stored in?

| Primitive | File | Format |
|-----------|------|--------|
| AI Instructions | `Copilot/Instructions/instructions.md` | Markdown |
| AI Data Schema | `Copilot/schema.json` | JSON |
| Verified Answers | `Copilot/VerifiedAnswers/*` | JSON |
| Example prompts | `Copilot/examplePrompts.json` | JSON |
| Copilot settings | `Copilot/settings.json` | JSON |
| Schema version | `Copilot/version.json` | JSON |

Not annotations on TMDL objects. Not extended properties. First-class files in the model definition payload.

## Q4. Can we modify these and push back via `updateDefinition`? **Yes, with caveats.**

`updateDefinition` accepts the `Copilot/` parts in the same payload shape as TMDL parts. A read-modify-write loop is mechanically possible:

1. `getDefinition` returns all parts (TMDL + `Copilot/` + project metadata).
2. Client modifies the in-memory bytes for the relevant `Copilot/` file.
3. `updateDefinition` accepts the full payload and replaces the model definition.

**Caveat: refresh latency before changes take effect in Copilot:**

| Storage mode | Time to surface in Copilot |
|--------------|---------------------------|
| Import | Any model refresh |
| DirectQuery | Once per day |
| Direct Lake | Once per day |

The deployment can succeed and the model definition can be updated, but Copilot will keep using the previous AI Instructions until that refresh fires. This is documented behavior, not a bug. Surface this in any writeback CLI: report success of the API call separately from the latency window.

Source: [Prepare data for AI in Power BI](https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai) (Considerations section).

## Q5. Risks of full-model replacement via `updateDefinition`

Same risks documented in the original draft, plus one new one specific to this finding:

1. **Lossy round trips.** `updateDefinition` is whole-model replacement. Anything not in the payload is removed. The client must round-trip every part it does not modify byte-for-byte. This now applies to `Copilot/` parts too: a client that only knows about TMDL will silently delete the entire Prep for AI configuration on writeback.
2. **Concurrent edits.** Another user editing in Fabric Service between `getDefinition` and `updateDefinition` is overwritten. No ETag in v1.
3. **Permission scope.** Member / Contributor / Admin on the workspace, plus write permission on the model. A read-only credential succeeds at `getDefinition` and fails 403 only at write.
4. **Refresh latency.** Above; particularly punishing for DirectQuery / Direct Lake.
5. **Q&A deprecation context.** Q&A (the historical home of the term "LSDL") is being deprecated December 2026. The `Copilot/` folder is the forward path; `.lsdl.yaml` exports from the Modeling ribbon are tied to the deprecated Q&A surface and should not be the integration target.

Source for deprecation: [Q&A overview](https://learn.microsoft.com/en-us/power-bi/natural-language/q-and-a-tooling-advanced) and surrounding Q&A pages.

## Q6. Authentication / permissions

Unchanged from the original draft:

- OAuth2 bearer token, scope `https://api.fabric.microsoft.com/.default` (or the Power BI compatibility scope).
- Inside Fabric: `notebookutils.credentials.getToken("pbi")` returns a usable token.
- Outside Fabric: `azure.identity` credential or service principal with delegated permissions on the Power BI service.
- `getDefinition`: Member / Contributor / Admin on the workspace, or Build permission on the model.
- `updateDefinition`: Member / Contributor / Admin **and** write permission on the model.

Additional prerequisite for Prep for AI features to function at all: `definition.pbism` must have `qnaEnabled: true`.

---

## Recommended next step: a `CopilotWriter`

The previously hypothesized writer (`TMDLDescriptionWriter` for Prep for AI) is replaced by a `CopilotWriter`:

- Reads / writes the `Copilot/` parts via `getDefinition` / `updateDefinition`.
- Round-trip preservation: every part the writer does not modify (TMDL files, other `Copilot/` files, project metadata) must be returned to `updateDefinition` byte-for-byte.
- Probe write permission before mutating.
- Surface the refresh-latency caveat in `WritebackResult` (e.g., a warning when the model storage mode is DirectQuery or Direct Lake).
- Long-running operation handling: `updateDefinition` returns 202 with a `Location` header; poll `/v1/operations/{id}` until terminal and propagate failure detail to `WritebackResult.errors`.
- Do not target `.lsdl.yaml`. That artifact exists only as a manual Modeling-ribbon export tied to the deprecating Q&A surface; it is not part of the live model definition payload.

The existing `TMDLClient.get_definition` HTTP layer is structurally correct (the envelope is the same for TMDL and `Copilot/` parts). What changed is the *path filter* used to find Prep for AI primitives: match on `path` prefixes rooted at `Copilot/`, not on annotation strings inside TMDL files.

A future `CopilotWriter` can build directly on this foundation.

---

## Authoritative references

- PBIP SemanticModel folder layout: <https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-dataset>
- PBIP overview: <https://learn.microsoft.com/en-us/power-bi/developer/projects/projects-overview>
- TMDL overview: <https://learn.microsoft.com/en-us/analysis-services/tmdl/tmdl-overview>
- Fabric REST: SemanticModel definition envelope (shows the `Copilot/` tree): <https://learn.microsoft.com/en-us/rest/api/fabric/articles/item-management/definitions/semantic-model-definition>
- Get Semantic Model Definition: <https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/get-semantic-model-definition>
- Update Semantic Model Definition: <https://learn.microsoft.com/en-us/rest/api/fabric/semanticmodel/items/update-semantic-model-definition>
- Prepare data for AI in Power BI (LSDL terminology + refresh rules): <https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai>
- AI Data Schemas: <https://learn.microsoft.com/en-us/power-bi/create-reports/copilot-prepare-data-ai-data-schema>
- Q&A linguistic schema (origin of `.lsdl.yaml`, on the deprecating side): <https://learn.microsoft.com/en-us/power-bi/natural-language/q-and-a-tooling-advanced>
- Official Power BI Modeling MCP server (TMDL only, does not touch `Copilot/`): <https://github.com/microsoft/powerbi-modeling-mcp>

---

## Original hypothesis (falsified)

The first version of this document hypothesized that AI Instructions and Verified Answers were persisted as model-level TMDL annotations under the `__PBI_` namespace (e.g., `annotation __PBI_AIInstructions = "..."`). That hypothesis was based on Microsoft's historical pattern for Q&A linguistic-schema persistence. Verification against the Fabric REST `getDefinition` reference and the Prep for AI Learn page falsified it: the storage layer is the `Copilot/` folder of Markdown + JSON files described above. The TMDL annotation hypothesis has been retracted.
