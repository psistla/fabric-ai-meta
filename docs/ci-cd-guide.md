# CI/CD Integration Guide

This guide shows how to wire `fabric-ai-meta` into a continuous integration pipeline so that semantic model quality is enforced on every change instead of audited after the fact.

## Two patterns covered

1. **Governance gate on pull request.** Run `scan` and `governance` against the workspace fixtures (or a mocked snapshot) on every PR; fail the build if average AI readiness drops below a threshold or if the number of naming inconsistencies exceeds an agreed cap.
2. **Scheduled scan with delta tracking.** Run a weekly scan, store the resulting `workspace-summary.json` as a build artifact, then compare each scan with the previous one using `fabric-ai-meta diff` and surface the delta as a workflow annotation or PR comment.

Both patterns work in mock mode (no Fabric runtime required) for fixture-based development. Live mode requires a Fabric notebook context, so the patterns below show mock mode by default with notes on how to switch to live mode where applicable.

---

## Pattern 1: GitHub Actions governance gate

Drop the workflow below into `.github/workflows/governance.yml`. It runs on every PR, executes the governance pipeline against your fixtures, and fails if the report breaches the configured thresholds.

```yaml
name: Governance gate

on:
  pull_request:
    branches: [main, master]
  push:
    branches: [main, master]

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install
        run: pip install --no-cache-dir -e ".[dev]"

      - name: Bulk scan (mock mode)
        run: |
          mkdir -p ci-output
          fabric-ai-meta scan --workspace ci --mock --output ci-output

      - name: Governance report (mock mode)
        run: |
          fabric-ai-meta governance \
            --workspace ci --mock \
            --output ci-output \
            --report ci-output/governance-report.json

      - name: Enforce governance thresholds
        run: |
          python scripts/ci-governance-check.py \
            ci-output/governance-report.json \
            --max-naming-issues 5 \
            --min-score 0.70

      - name: Upload governance artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: governance-output
          path: ci-output/
```

The `Enforce governance thresholds` step calls the standalone [`scripts/ci-governance-check.py`](../scripts/ci-governance-check.py) helper (no fabric-ai-meta import required at gate time). The script exits non-zero when the report breaches either threshold, which fails the workflow.

To run against a live Fabric workspace from CI (advanced; requires a Fabric notebook job runner), replace `--mock` with `--workspace "<your workspace>"` and ensure the runner is inside the Fabric notebook environment. Most teams run this gate in mock mode against committed fixtures and leave live verification to the scheduled pattern below.

---

## Pattern 2: GitHub Actions scheduled scan with delta

This pattern runs once a week, archives the workspace summary as an artifact, and compares against the previous run.

```yaml
name: Scheduled scan with delta

on:
  schedule:
    - cron: "0 6 * * 1"   # Mondays at 06:00 UTC
  workflow_dispatch: {}

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - run: pip install --no-cache-dir -e ".[dev]"

      - name: Scan workspace
        run: |
          mkdir -p current
          fabric-ai-meta scan --workspace ci --mock --output current

      - name: Download previous scan
        id: previous
        uses: dawidd6/action-download-artifact@v6
        with:
          workflow: scheduled-scan-delta.yml
          name: workspace-summary
          path: previous
          if_no_artifact_found: warn
        continue-on-error: true

      - name: Compute delta when previous exists
        if: steps.previous.outcome == 'success'
        run: |
          fabric-ai-meta diff \
            previous/workspace-summary.json \
            current/workspace-summary.json \
            --format text \
            --output current/delta.txt
          cat current/delta.txt
          echo "---" >> "$GITHUB_STEP_SUMMARY"
          echo "## Workspace delta vs previous run" >> "$GITHUB_STEP_SUMMARY"
          echo '```' >> "$GITHUB_STEP_SUMMARY"
          cat current/delta.txt >> "$GITHUB_STEP_SUMMARY"
          echo '```' >> "$GITHUB_STEP_SUMMARY"

      - name: Archive workspace summary
        uses: actions/upload-artifact@v4
        with:
          name: workspace-summary
          path: current/workspace-summary.json
          retention-days: 90
```

The delta is emitted both to the build log and to the GitHub Actions step summary so reviewers see score regressions, added or removed models, and naming-issue trends without leaving the workflow run page.

---

## Pattern 3: Azure DevOps pipeline

Both patterns translate cleanly to Azure DevOps. The example below combines the gate and the scheduled scan into a single `azure-pipelines.yml`.

```yaml
trigger:
  branches:
    include: [main, master]

pr:
  branches:
    include: [main, master]

schedules:
  - cron: "0 6 * * 1"
    displayName: Weekly scan
    branches:
      include: [main]
    always: true

pool:
  vmImage: ubuntu-latest

steps:
  - task: UsePythonVersion@0
    inputs:
      versionSpec: "3.11"

  - script: pip install --no-cache-dir -e ".[dev]"
    displayName: Install fabric-ai-meta

  - script: |
      mkdir -p $(Build.ArtifactStagingDirectory)/output
      fabric-ai-meta scan --workspace ci --mock \
        --output $(Build.ArtifactStagingDirectory)/output
      fabric-ai-meta governance --workspace ci --mock \
        --output $(Build.ArtifactStagingDirectory)/output \
        --report $(Build.ArtifactStagingDirectory)/output/governance-report.json
    displayName: Scan + governance

  - script: |
      python scripts/ci-governance-check.py \
        $(Build.ArtifactStagingDirectory)/output/governance-report.json \
        --max-naming-issues 5 \
        --min-score 0.70
    displayName: Enforce governance thresholds

  - task: PublishBuildArtifacts@1
    condition: always()
    inputs:
      pathToPublish: $(Build.ArtifactStagingDirectory)/output
      artifactName: governance-output
```

To compute a delta on the scheduled run, download the previous build's `workspace-summary.json` via the Azure DevOps REST API or the `DownloadBuildArtifacts@1` task, then add a step that calls `fabric-ai-meta diff` against the new summary.

---

## The `ci-governance-check.py` helper

The standalone script lives at [`scripts/ci-governance-check.py`](../scripts/ci-governance-check.py). It depends only on the Python standard library, so CI runners do not need `fabric-ai-meta` installed at gate time when the report is produced upstream and passed in as an artifact.

### Usage

```bash
python scripts/ci-governance-check.py <governance-report.json> \
  [--max-naming-issues N] \
  [--min-score F] \
  [--max-duplicate-measures N]
```

| Flag | Default | Behavior |
|------|---------|----------|
| `--max-naming-issues` | unlimited | Fail if `summary.total_naming_issues > N`. |
| `--max-duplicate-measures` | unlimited | Fail if `summary.total_duplicate_measures > N`. |
| `--min-score` | 0.0 | Fail if average AI readiness across models is below `F`. |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | All thresholds satisfied. |
| `1` | At least one threshold breached or the report file could not be read. |

### Tuning the thresholds

A reasonable starting point for a mature data estate:

| Threshold | Starting value | Rationale |
|-----------|---------------|-----------|
| `--min-score` | `0.70` | Average readiness above 70% indicates most models have descriptions, named relationships, and consistent measure naming. |
| `--max-naming-issues` | `5` | Allows for naming drift across a handful of models without blocking every PR. Tighten over time. |
| `--max-duplicate-measures` | `0` | Duplicate DAX expressions across models indicate consolidation opportunities. Set to `0` once known duplicates are resolved. |

Bake the thresholds into the workflow file so changes are reviewed and version-controlled like any other code change.

---

## Operational notes

- **Mock mode is the right default for CI.** Live extraction requires a Fabric notebook environment, which most CI runners do not provide. The scan and governance commands produce identical output structure in both modes, so a mock-mode gate gives you regression detection on the parts of the pipeline you control: classification, scoring, governance heuristics, and the script that enforces thresholds.
- **Artifact retention.** Keep at least 90 days of `workspace-summary.json` artifacts so the delta workflow has a useful history. Stored summaries are small (under 50 KB for typical workspaces).
- **Failure semantics.** Treat governance gate failure as a soft signal during rollout: failing PRs without a clear migration path frustrates teams. Once the baseline is healthy, switch the gate from `continue-on-error: true` to a hard failure.
- **Cost.** Both patterns avoid LLM calls (`--llm-enrich` is omitted), so CI cost is bounded by GitHub or Azure DevOps minutes alone.
