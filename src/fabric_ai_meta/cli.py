"""CLI entrypoint for fabric-ai-meta using Click."""

import json
import os
import re
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from fabric_ai_meta.config import load_config

console = Console()


def _slugify(name: str) -> str:
    """Convert a model name to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _get_fixture_path(model_name: str) -> str:
    """Return path to the best-matching fixture for mock mode."""
    here = os.path.dirname(__file__)
    fixtures_dir = os.path.normpath(os.path.join(here, "..", "..", "tests", "fixtures"))
    slug = _slugify(model_name).replace("-", "_")
    candidate = os.path.join(fixtures_dir, f"{slug}.json")
    if os.path.exists(candidate):
        return candidate
    # Default to adventure_works
    default = os.path.join(fixtures_dir, "adventure_works.json")
    if os.path.exists(default):
        return default
    raise click.ClickException(
        f"No fixture file found for model '{model_name}'. "
        f"Expected: {candidate}"
    )


def _run_analysis(model_name: str, workspace: str, output: str, fmt: str,
                  include_sample_values: bool, llm_enrich: bool, mock: bool) -> None:
    """Core analysis flow shared by analyze and scan commands."""
    from fabric_ai_meta.analyzer.classifier import (
        classify_table_heuristic,
        classify_column_role,
        classify_measure_heuristic,
    )
    from fabric_ai_meta.analyzer.dax_parser import build_dependency_graph
    from fabric_ai_meta.analyzer.scorer import score_model
    from fabric_ai_meta.generator.schema import generate_ai_ready_schema
    from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
    from fabric_ai_meta.generator.export_openai import to_openai_function
    from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin

    cfg = load_config()
    slug = _slugify(model_name)
    out_dir = os.path.join(output, slug)
    _ensure_dir(out_dir)

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        # Step 1: Extract
        task = progress.add_task(f"Extracting '{model_name}'...", total=None)
        if mock:
            from fabric_ai_meta.extractor.mock import MockExtractor
            fixture_path = _get_fixture_path(model_name)
            extractor = MockExtractor(fixture_path)
        else:
            from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
            if not detect_notebook_environment():
                raise FabricEnvironmentError()
            from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
            extractor = SemanticLinkExtractor(workspace=workspace)

        model = extractor.extract(model_name, workspace)
        progress.update(task, description=f"Extracted '{model_name}' ({len(model.tables)} tables)")

        # Step 2: Heuristic classification
        progress.update(task, description="Running heuristic classification...")
        for table in model.tables:
            table.table_type = classify_table_heuristic(table, model.relationships)
            for col in table.columns:
                col.role = classify_column_role(col, table, model.relationships)
            for measure in table.measures:
                measure.category = classify_measure_heuristic(measure)

        # Step 3: Score
        progress.update(task, description="Scoring AI readiness...")
        overall, breakdown = score_model(model)
        model.ai_readiness_score = overall
        model.scoring_breakdown = breakdown

        # Step 4: Optional LLM enrichment
        if llm_enrich:
            progress.update(task, description="Running LLM enrichment...")
            _run_llm_enrichment(model, cfg)

        # Step 5: Generate outputs
        progress.update(task, description="Generating output files...")
        written = []

        # ai-ready-schema.json
        schema = generate_ai_ready_schema(model)
        p = os.path.join(out_dir, "ai-ready-schema.json")
        _write_json(p, schema)
        written.append(("ai-ready-schema.json", p))

        # langchain-tool.json
        lc = to_langchain_tool_definition(model)
        p = os.path.join(out_dir, "langchain-tool.json")
        _write_json(p, lc)
        written.append(("langchain-tool.json", p))

        # openai-function.json
        oa = to_openai_function(model)
        p = os.path.join(out_dir, "openai-function.json")
        _write_json(p, oa)
        written.append(("openai-function.json", p))

        # semantic-kernel-plugin.json
        sk = to_semantic_kernel_plugin(model)
        p = os.path.join(out_dir, "semantic-kernel-plugin.json")
        _write_json(p, sk)
        written.append(("semantic-kernel-plugin.json", p))

        # readiness-score.json
        score_data = {"model": model_name, "score": overall, "breakdown": breakdown}
        p = os.path.join(out_dir, "readiness-score.json")
        _write_json(p, score_data)
        written.append(("readiness-score.json", p))

        # measure-dependency-graph.json
        all_measures = [m for t in model.tables for m in t.measures]
        dep_graph = build_dependency_graph(all_measures)
        p = os.path.join(out_dir, "measure-dependency-graph.json")
        _write_json(p, dep_graph)
        written.append(("measure-dependency-graph.json", p))

        # extraction-raw.json
        p = os.path.join(out_dir, "extraction-raw.json")
        _write_json(p, model.to_dict())
        written.append(("extraction-raw.json", p))

        progress.update(task, description="Done.")

    # Summary table
    tbl = Table(title=f"Output: {model_name} (score: {overall:.2%})", show_header=True)
    tbl.add_column("File")
    tbl.add_column("Path")
    for fname, fpath in written:
        tbl.add_row(fname, fpath)
    console.print(tbl)

    return model, overall


def _run_llm_enrichment(model, cfg) -> None:
    """Run LLM enrichment for ambiguous tables and grain detection."""
    from fabric_ai_meta.analyzer.classifier import classify_table_heuristic
    from fabric_ai_meta.llm.client import FabricLLMClient
    from fabric_ai_meta.models.metadata import TableType

    api_key = os.environ.get(cfg.llm.api_key_env)
    llm = FabricLLMClient(
        api_key=api_key,
        cache_enabled=cfg.llm.cache_enabled,
        cache_dir=cfg.llm.cache_dir,
        max_cost_usd=cfg.llm.max_cost_per_run,
    )
    for table in model.tables:
        if table.table_type == TableType.UNKNOWN:
            try:
                table_type, confidence = llm.classify_table(table, model.relationships)
                if confidence >= 0.7:
                    table.table_type = table_type
                grain, _ = llm.detect_grain(table)
                if grain:
                    table.grain = grain
            except Exception:
                pass


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
def main():
    """Fabric AI Meta — extract, analyze, and export Fabric semantic model metadata for AI frameworks."""
    pass


# ---------------------------------------------------------------------------
# auth commands
# ---------------------------------------------------------------------------

@main.group()
def auth():
    """Authentication commands."""
    pass


@auth.command("login")
def auth_login():
    """Interactive browser login to Microsoft Fabric."""
    console.print(Panel("[bold]auth login[/bold]", title="fabric-ai-meta"))
    cfg = load_config()
    console.print(f"Auth method: [cyan]{cfg.auth.method}[/cyan]")
    try:
        from fabric_ai_meta.auth.entra import get_credential
        credential = get_credential(
            method=cfg.auth.method,
            tenant_id=cfg.auth.tenant_id,
            client_id=cfg.auth.client_id,
            client_secret=cfg.auth.client_secret,
        )
        if credential is not None:
            console.print("[green]Login successful.[/green]")
        else:
            console.print("[yellow]Notebook mode — using ambient Fabric credential.[/yellow]")
    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        sys.exit(1)


@auth.command("status")
def auth_status():
    """Show current authentication state."""
    console.print(Panel("[bold]auth status[/bold]", title="fabric-ai-meta"))
    from fabric_ai_meta.auth.entra import detect_notebook_environment
    in_fabric = detect_notebook_environment()
    if in_fabric:
        console.print("[green]Running inside Fabric notebook runtime.[/green]")
    else:
        console.print("[yellow]Running in local environment (mock/dev mode).[/yellow]")
    cfg = load_config()
    console.print(f"Configured auth method: [cyan]{cfg.auth.method}[/cyan]")


@auth.command("logout")
def auth_logout():
    """Log out and clear stored credentials."""
    console.print(Panel("[bold]auth logout[/bold]", title="fabric-ai-meta"))
    console.print("[green]Logged out. (No persistent token store in v1.)[/green]")


# ---------------------------------------------------------------------------
# analyze command
# ---------------------------------------------------------------------------

@main.command("analyze")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None, help="Fabric workspace name.")
@click.option("--output", "-o", default=None, help="Output directory.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json"]), help="Output format.")
@click.option("--include-sample-values", is_flag=True, default=False)
@click.option("--llm-enrich", is_flag=True, default=False, help="Enable LLM-assisted classification.")
@click.option("--mock", is_flag=True, default=False, help="Use MockExtractor with fixture data (for local dev/testing).")
def analyze(model_name, workspace, output, fmt, include_sample_values, llm_enrich, mock):
    """Analyze a semantic model and generate AI-ready metadata exports."""
    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace
    output = output or cfg.output.output_dir

    console.print(Panel(
        f"[bold]analyze[/bold]  model=[cyan]{model_name}[/cyan]  "
        f"workspace=[cyan]{workspace}[/cyan]  "
        f"mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    try:
        _run_analysis(model_name, workspace, output, fmt, include_sample_values, llm_enrich, mock)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------

@main.command("scan")
@click.option("--workspace", "-w", required=True, help="Fabric workspace name.")
@click.option("--output", "-o", default=None, help="Output directory.")
@click.option("--format", "fmt", default="json", type=click.Choice(["json"]))
def scan(workspace, output, fmt):
    """Scan all models in a workspace and generate AI-ready exports."""
    cfg = load_config()
    output = output or cfg.output.output_dir

    console.print(Panel(
        f"[bold]scan[/bold]  workspace=[cyan]{workspace}[/cyan]",
        title="fabric-ai-meta"
    ))

    from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
    if not detect_notebook_environment():
        raise FabricEnvironmentError()

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    extractor = SemanticLinkExtractor(workspace=workspace)
    model_names = extractor.list_models(workspace)

    console.print(f"Found [bold]{len(model_names)}[/bold] models in workspace.")

    summary = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for name in model_names:
            task = progress.add_task(f"Analyzing {name}...", total=None)
            try:
                result = _run_analysis(name, workspace, output, fmt, False, False, False)
                model, score = result
                summary.append({"model": name, "score": score, "status": "ok"})
            except Exception as e:
                summary.append({"model": name, "score": None, "status": f"error: {e}"})
            progress.remove_task(task)

    # workspace-summary.json
    _ensure_dir(output)
    summary_path = os.path.join(output, "workspace-summary.json")
    _write_json(summary_path, {"workspace": workspace, "models": summary})
    console.print(f"[green]Workspace summary written to:[/green] {summary_path}")


# ---------------------------------------------------------------------------
# export commands
# ---------------------------------------------------------------------------

@main.group("export")
def export_group():
    """Export semantic model metadata to framework-specific formats."""
    pass


def _export_single(model_name: str, workspace: str, filename: str, generator_fn, label: str) -> None:
    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace
    output = cfg.output.output_dir

    console.print(Panel(
        f"[bold]export {label}[/bold]  model=[cyan]{model_name}[/cyan]  workspace=[cyan]{workspace}[/cyan]",
        title="fabric-ai-meta"
    ))

    from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
    if not detect_notebook_environment():
        raise FabricEnvironmentError()

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    extractor = SemanticLinkExtractor(workspace=workspace)
    model = extractor.extract(model_name, workspace)

    result = generator_fn(model)
    slug = _slugify(model_name)
    out_dir = os.path.join(output, slug)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, filename)
    _write_json(path, result)
    console.print(f"[green]Written:[/green] {path}")


@export_group.command("langchain")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None)
def export_langchain(model_name, workspace):
    """Export LangChain tool definition."""
    from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
    _export_single(model_name, workspace, "langchain-tool.json", to_langchain_tool_definition, "langchain")


@export_group.command("openai")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None)
def export_openai(model_name, workspace):
    """Export OpenAI function calling schema."""
    from fabric_ai_meta.generator.export_openai import to_openai_function
    _export_single(model_name, workspace, "openai-function.json", to_openai_function, "openai")


@export_group.command("semantic-kernel")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None)
def export_semantic_kernel(model_name, workspace):
    """Export Semantic Kernel plugin manifest."""
    from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
    _export_single(model_name, workspace, "semantic-kernel-plugin.json", to_semantic_kernel_plugin, "semantic-kernel")


@export_group.command("prep-for-ai")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None)
def export_prep_for_ai(model_name, workspace):
    """Export Prep for AI configuration (requires LLM)."""
    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace

    console.print(Panel(
        f"[bold]export prep-for-ai[/bold]  model=[cyan]{model_name}[/cyan]",
        title="fabric-ai-meta"
    ))

    from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
    if not detect_notebook_environment():
        raise FabricEnvironmentError()

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    from fabric_ai_meta.llm.client import FabricLLMClient
    from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai
    import dataclasses

    extractor = SemanticLinkExtractor(workspace=workspace)
    model = extractor.extract(model_name, workspace)

    api_key = os.environ.get(cfg.llm.api_key_env)
    llm = FabricLLMClient(
        api_key=api_key,
        cache_enabled=cfg.llm.cache_enabled,
        cache_dir=cfg.llm.cache_dir,
        max_cost_usd=cfg.llm.max_cost_per_run,
    )
    prep_config = generate_prep_for_ai(model, llm)

    slug = _slugify(model_name)
    out_dir = os.path.join(cfg.output.output_dir, slug)
    _ensure_dir(out_dir)
    path = os.path.join(out_dir, "prep-for-ai-config.json")
    _write_json(path, dataclasses.asdict(prep_config))
    console.print(f"[green]Written:[/green] {path}")


# ---------------------------------------------------------------------------
# score command
# ---------------------------------------------------------------------------

@main.command("score")
@click.argument("model_name", required=False)
@click.option("--workspace", "-w", default=None, help="Fabric workspace name.")
@click.option("--all", "score_all", is_flag=True, default=False, help="Score all models in workspace.")
@click.option("--mock", is_flag=True, default=False, help="Use MockExtractor for local dev.")
def score(model_name, workspace, score_all, mock):
    """Show AI readiness score for one or all models."""
    from fabric_ai_meta.analyzer.classifier import (
        classify_table_heuristic,
        classify_column_role,
        classify_measure_heuristic,
    )
    from fabric_ai_meta.analyzer.scorer import score_model as run_score

    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace

    console.print(Panel(
        f"[bold]score[/bold]  workspace=[cyan]{workspace}[/cyan]  all=[cyan]{score_all}[/cyan]",
        title="fabric-ai-meta"
    ))

    def _score_one(name: str) -> tuple:
        if mock:
            from fabric_ai_meta.extractor.mock import MockExtractor
            fixture_path = _get_fixture_path(name)
            extractor = MockExtractor(fixture_path)
        else:
            from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
            if not detect_notebook_environment():
                raise FabricEnvironmentError()
            from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
            extractor = SemanticLinkExtractor(workspace=workspace)
        m = extractor.extract(name, workspace)
        for t in m.tables:
            t.table_type = classify_table_heuristic(t, m.relationships)
            for c in t.columns:
                c.role = classify_column_role(c, t, m.relationships)
            for ms in t.measures:
                ms.category = classify_measure_heuristic(ms)
        overall, breakdown = run_score(m)
        return overall, breakdown

    if score_all:
        from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        names = SemanticLinkExtractor(workspace=workspace).list_models(workspace)
    else:
        if not model_name:
            raise click.UsageError("Provide MODEL_NAME or use --all.")
        names = [model_name]

    results = []
    for name in names:
        try:
            overall, breakdown = _score_one(name)
            results.append((name, overall, breakdown))
        except Exception as e:
            console.print(f"[red]Error scoring {name}: {e}[/red]")

    results.sort(key=lambda x: x[1], reverse=True)

    tbl = Table(title="AI Readiness Scores", show_header=True)
    tbl.add_column("Model")
    tbl.add_column("Score", justify="right")
    for k in ["description_coverage", "measure_documentation", "relationship_completeness",
              "naming_consistency", "sample_values_available", "business_rules_documented"]:
        tbl.add_column(k, justify="right")

    for name, overall, breakdown in results:
        tbl.add_row(
            name,
            f"{overall:.2%}",
            *[f"{breakdown.get(k, 0):.2%}" for k in breakdown],
        )
    console.print(tbl)


# ---------------------------------------------------------------------------
# governance command
# ---------------------------------------------------------------------------

@main.command("governance")
@click.option("--workspace", "-w", required=True, help="Fabric workspace name.")
@click.option("--report", default="governance-report.json", help="Output path for governance report.")
def governance(workspace, report):
    """Generate cross-model governance report for a workspace."""
    console.print(Panel(
        f"[bold]governance[/bold]  workspace=[cyan]{workspace}[/cyan]",
        title="fabric-ai-meta"
    ))

    from fabric_ai_meta.auth.entra import detect_notebook_environment, FabricEnvironmentError
    if not detect_notebook_environment():
        raise FabricEnvironmentError()

    from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
    from fabric_ai_meta.analyzer.classifier import (
        classify_table_heuristic,
        classify_column_role,
        classify_measure_heuristic,
    )
    from fabric_ai_meta.analyzer.scorer import score_model as run_score
    from fabric_ai_meta.analyzer.governance import generate_governance_report

    extractor = SemanticLinkExtractor(workspace=workspace)
    model_names = extractor.list_models(workspace)

    models = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for name in model_names:
            t = progress.add_task(f"Extracting {name}...", total=None)
            try:
                m = extractor.extract(name, workspace)
                for tbl in m.tables:
                    tbl.table_type = classify_table_heuristic(tbl, m.relationships)
                    for c in tbl.columns:
                        c.role = classify_column_role(c, tbl, m.relationships)
                    for ms in tbl.measures:
                        ms.category = classify_measure_heuristic(ms)
                overall, breakdown = run_score(m)
                m.ai_readiness_score = overall
                m.scoring_breakdown = breakdown
                models.append(m)
            except Exception as e:
                console.print(f"[red]Error: {name}: {e}[/red]")
            progress.remove_task(t)

    gov_report = generate_governance_report(models)
    _write_json(report, gov_report)
    console.print(f"[green]Governance report written to:[/green] {report}")


if __name__ == "__main__":
    main()
