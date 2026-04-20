# TMDL Spike: Programmatic Read/Write of Prep for AI Settings

> **Status:** Research spike. Some answers below are marked **"requires Fabric testing"** because they cannot be confirmed from a local development environment. The accompanying `notebooks/tmdl-spike.ipynb` is the vehicle for completing those answers from inside a Fabric workspace.
>
> **Spike goal:** Determine whether AI Instructions and Verified Answers (the two Prep for AI primitives that lack a public REST API) appear in the TMDL definition exposed by `getDefinition` / `updateDefinition`, and whether a read-modify-write loop is feasible.

---

## Background

Prep for AI in Microsoft Fabric configures three classes of metadata on a semantic model:

1. **AI Data Schema:** which tables and columns the AI surface should see.
2. **AI Instructions:** free-form natural language guidance shown to the LLM.
3. **Verified Answers:** human-curated question-to-DAX mappings.

XMLA / TOM exposes table, column, and measure `Description` properties (S6-01 uses this). It does **not** expose AI Instructions or Verified Answers as first-class TOM objects. The Fabric REST API surface for semantic models, however, includes `getDefinition` and `updateDefinition` endpoints that return and accept the **entire model definition** in TMDL (Tabular Model Definition Language) format. If Prep for AI settings serialize into the TMDL payload, a read-modify-write loop becomes a viable writeback path, even without an object-level API.

---

## Endpoints under examination

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/workspaces/{workspaceId}/semanticModels/{modelId}/getDefinition` | Returns the model definition as base64-encoded TMDL files. |
| `POST` | `/v1/workspaces/{workspaceId}/semanticModels/{modelId}/updateDefinition` | Replaces the model definition with the supplied TMDL payload. Long-running operation. |

Both endpoints require a Fabric workspace bearer token (Power BI / Fabric scope).

---

## Q1. Do AI Instructions appear in the TMDL definition returned by `getDefinition`?

**Status:** Requires Fabric testing.

**Hypothesis:** Likely yes, as a model-level annotation or extended property. Microsoft's serialization pattern for non-TOM concepts (linguistic schema, Q&A metadata, perspectives) historically uses model annotations. AI Instructions appear configurable from the Fabric web UI without a separate storage system, which strongly suggests inline persistence in the model.

**How to verify:** Run cells 4 and 5 of `notebooks/tmdl-spike.ipynb` against a workspace where AI Instructions have been set. Search the decoded TMDL files for the configured instruction text. If found, record the exact path (file name and TMDL property/annotation key).

---

## Q2. Do Verified Answers appear in the TMDL definition?

**Status:** Requires Fabric testing.

**Hypothesis:** Less certain than Q1. Verified Answers are conceptually adjacent to Q&A linguistic schema, which historically lived in a separate `linguisticSchema` part of the model bim/tmdl. They may appear as:

- A dedicated TMDL section (similar to `cultures` or `perspectives`).
- Annotations on the model or on individual measures referenced by the answer.
- A separate file inside the model definition payload.

**How to verify:** With at least one Verified Answer configured in the test model, scan all decoded TMDL file contents for the question text or the DAX expression. The location of the match resolves the structure question.

---

## Q3. What TMDL format are they stored in (properties, annotations, extended properties)?

**Status:** Partially answered, requires Fabric testing for confirmation.

TMDL supports several mechanisms for non-canonical metadata:

| Mechanism | Syntax | Likelihood for Prep for AI |
|-----------|--------|----------------------------|
| First-class TMDL property | `propertyName: value` | Low. Would imply TMDL grammar additions. |
| Annotation | `annotation Name = value` | High. Microsoft uses this for `__PBI_*` and `__TM_*` keys. |
| Extended property | `extendedProperty Name = { ... }` | Medium. Used for richer JSON payloads. |

**Expected pattern:** model-level `annotation __PBI_AIInstructions` (string) and `annotation __PBI_VerifiedAnswers` (JSON array). This is consistent with how Power BI persists Q&A linguistic schema and field synonyms.

**How to verify:** Once Q1/Q2 turn up the storage location, classify the TMDL syntax of the surrounding block.

---

## Q4. Can we modify these fields and push back via `updateDefinition`?

**Status:** Conditional yes, contingent on Q1-Q3.

If the settings live inside the TMDL payload, a round trip is mechanically possible:

1. `getDefinition` returns the full model TMDL.
2. Modify the relevant annotation / extended property in memory.
3. `updateDefinition` accepts the modified payload and replaces the model definition.

**Risks specific to this round trip:**

- `updateDefinition` is **whole-model replacement**, not a patch. Any TMDL not included in the payload is removed. The client must round-trip the full definition without dropping fields it does not understand.
- The endpoint runs as a long-running operation; clients must poll the operation status URL until terminal.
- TMDL parsers downstream of Microsoft's may reject annotations they do not recognize, even if the payload is valid TMDL. Verification with the actual Prep for AI UI after writeback is required.

---

## Q5. What are the risks of full-model replacement via `updateDefinition`?

**Critical risks:**

1. **Lossy round trips.** If the TMDL payload contains tokens this client does not preserve verbatim (e.g., comments, ordering, extended properties for unrelated features), the writeback can silently delete metadata that the original UI configuration depended on. Mitigation: byte-for-byte preserve every file the client does not explicitly modify; only re-serialize the file whose annotation is being updated.
2. **Concurrent edits.** Another user editing the model in Fabric Service between `getDefinition` and `updateDefinition` will have their changes overwritten. The REST API offers no ETag / optimistic concurrency token in v1. Mitigation: schedule writebacks during low-edit windows; fail loudly if scoring metadata appears to have changed unexpectedly between read and write.
3. **Permission scope.** `updateDefinition` requires write access (Member or Admin role on the workspace, or model-level write permission). A read-only credential will succeed at `getDefinition` and fail with 403 only at write time. Fail fast: probe write permission before mutating.
4. **Downstream invalidation.** Replacing the model definition refreshes downstream caches and may trigger dataset reloads. Schedule outside business hours for production models.
5. **Validation failures.** Malformed TMDL produces a long-running operation that fails after the call returns 202. The client must surface the operation failure clearly, not just the initial 202.

---

## Q6. What authentication / permissions are required?

**Authentication:** OAuth2 bearer token for the Fabric / Power BI service.

- Scope: `https://api.fabric.microsoft.com/.default` (or `https://analysis.windows.net/powerbi/api/.default` for the Power BI compatibility surface).
- Inside a Fabric notebook, the ambient credential (`get_credential(method="notebook")` returning `None`, with `sempy.fabric` handling the token) works for read; write requires explicit credential acquisition via `notebookutils.credentials.getToken("pbi")` or an explicit `azure.identity` credential with delegated permissions.
- Outside Fabric, an Entra service principal with `Tenant.ReadWrite.All` on Power BI service is the typical pattern for automated writeback.

**Permissions:**

- `getDefinition`: Member / Contributor / Admin on the workspace, **or** Build permission on the dataset.
- `updateDefinition`: Member / Contributor / Admin on the workspace **and** write permission on the dataset.

---

## Recommendation for Sprint 7+

If Q1 and Q2 confirm that AI Instructions and Verified Answers serialize into the TMDL definition, build a `TMDLDescriptionWriter` (sibling to `SemanticLinkWriter`) with the following constraints:

- Round-trip preservation: never re-serialize a TMDL file the writer does not edit.
- Probe write permission before any mutation.
- Surface long-running-operation status, including failure detail, in `WritebackResult.errors`.
- Support dry-run mode that diffs the would-be-written TMDL files against the originals.

If Q1 or Q2 falsifies the hypothesis (the settings are stored outside the TMDL payload, e.g., in a separate Fabric metadata service), document the gap and revert to manual application as the supported path for those primitives.

---

## Appendix: Endpoint reference

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/semanticModels/{modelId}/getDefinition

Headers:
  Authorization: Bearer <token>

Response 200:
{
  "definition": {
    "parts": [
      { "path": "model.tmdl",   "payload": "<base64>", "payloadType": "InlineBase64" },
      { "path": "tables/Sales.tmdl", "payload": "<base64>", "payloadType": "InlineBase64" },
      ...
    ]
  }
}
```

```
POST https://api.fabric.microsoft.com/v1/workspaces/{workspaceId}/semanticModels/{modelId}/updateDefinition

Headers:
  Authorization: Bearer <token>
  Content-Type: application/json

Body:
{
  "definition": {
    "parts": [
      { "path": "model.tmdl", "payload": "<base64>", "payloadType": "InlineBase64" },
      ...
    ]
  }
}

Response 202:
  Location: https://api.fabric.microsoft.com/v1/operations/{operationId}
  Retry-After: 30
```

Operation polling: `GET /v1/operations/{operationId}` returns `status` in `{NotStarted, Running, Succeeded, Failed}`; on `Failed`, the response body carries the error detail.
