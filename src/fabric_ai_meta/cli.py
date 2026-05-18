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

from fabric_ai_meta import __version__
from fabric_ai_meta.config import load_config

# Ensure stdout/stderr use UTF-8 on Windows (default is cp1252), so Rich's
# spinner glyphs and other Unicode output don't raise UnicodeEncodeError.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

console = Console(legacy_windows=False)


def _slugify(name: str) -> str:
    """Convert a model name to a filesystem-safe slug."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _write_json(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _empty_copilot_signals() -> dict:
    """Signal shape for a model whose Copilot/ folder is absent or unreadable.

    Single source of truth: an empty `CopilotBundle`'s `signals()` output.
    Keeps the scan-time fallback shape in lockstep with the live signals shape.
    """
    from fabric_ai_meta.models.copilot import CopilotBundle
    return CopilotBundle().signals()


def _aggregate_copilot_signals(model_summaries: list[dict]) -> dict:
    """Workspace-level rollup, delegating to the shared aggregator."""
    from fabric_ai_meta.analyzer.governance import aggregate_copilot_signals
    pairs = [
        (m["name"], m["copilot"])
        for m in model_summaries
        if isinstance(m.get("copilot"), dict)
    ]
    return aggregate_copilot_signals(pairs)


def _list_mock_models() -> list[str]:
    """List model names available from fixture files in the tests/fixtures directory."""
    here = os.path.dirname(os.path.abspath(__file__))
    fixtures_dir = os.path.normpath(os.path.join(here, "..", "..", "tests", "fixtures"))
    models = []
    if os.path.isdir(fixtures_dir):
        for fname in sorted(os.listdir(fixtures_dir)):
            if fname.endswith(".json"):
                fpath = os.path.join(fixtures_dir, fname)
                try:
                    with open(fpath, encoding="utf-8") as f:
                        data = json.load(f)
                    models.append(data.get("name", fname[:-5]))
                except Exception:
                    pass
    return models


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
                  include_sample_values: bool, llm_enrich: bool, mock: bool,
                  *, with_copilot: bool = False) -> None:
    """Core analysis flow shared by analyze and scan commands."""
    from fabric_ai_meta.analyzer.classifier import (
        classify_column_role,
        classify_measure_heuristic,
        classify_table_heuristic,
    )
    from fabric_ai_meta.analyzer.dax_parser import build_dependency_graph
    from fabric_ai_meta.analyzer.scorer import score_model
    from fabric_ai_meta.generator.export_langchain import to_langchain_tool_definition
    from fabric_ai_meta.generator.export_openai import to_openai_function
    from fabric_ai_meta.generator.export_semantic_kernel import to_semantic_kernel_plugin
    from fabric_ai_meta.generator.schema import generate_ai_ready_schema

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
            from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
            if not detect_notebook_environment():
                raise FabricEnvironmentError()
            from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
            extractor = SemanticLinkExtractor(workspace=workspace)

        model = extractor.extract(model_name, workspace, with_copilot=with_copilot)
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


def _run_llm_enrichment(model, cfg):
    """Run LLM enrichment: classify ambiguous tables, detect grain, backfill descriptions.

    Returns the DescriptionBackfill produced (may be empty if no items needed backfill).
    """
    from fabric_ai_meta.generator.description_backfill import apply_backfill, backfill_descriptions
    from fabric_ai_meta.llm import load_llm_client
    from fabric_ai_meta.models.metadata import TableType

    llm = load_llm_client(cfg)
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

    backfill = backfill_descriptions(model, llm)
    apply_backfill(model, backfill)
    return backfill


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(version=__version__, prog_name="fabric-ai-meta")
def main():
    """Fabric AI Meta: extract, analyze, and export Fabric semantic model metadata for AI frameworks."""
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
            console.print("[yellow]Notebook mode, using ambient Fabric credential.[/yellow]")
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
@click.option("--with-copilot", is_flag=True, default=False,
              help="Also fetch the Copilot/ folder via Fabric REST getDefinition.")
def analyze(model_name, workspace, output, fmt, include_sample_values, llm_enrich, mock, with_copilot):
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
        _run_analysis(model_name, workspace, output, fmt, include_sample_values, llm_enrich, mock,
                      with_copilot=with_copilot)
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
@click.option("--mock", is_flag=True, default=False, help="Use MockExtractor with fixture data (for local dev/testing).")
@click.option("--llm-enrich", is_flag=True, default=False, help="Enable LLM-assisted enrichment for each model.")
@click.option("--with-copilot", is_flag=True, default=False,
              help="Also fetch the Copilot/ folder via Fabric REST getDefinition.")
def scan(workspace, output, fmt, mock, llm_enrich, with_copilot):
    """Scan all models in a workspace and generate AI-ready exports."""
    from datetime import datetime, timezone

    cfg = load_config()
    output = output or cfg.output.output_dir

    console.print(Panel(
        f"[bold]scan[/bold]  workspace=[cyan]{workspace}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        here = os.path.dirname(os.path.abspath(__file__))
        fixtures_dir = os.path.normpath(os.path.join(here, "..", "..", "tests", "fixtures"))
        extractor = MockExtractor(fixture_dir=fixtures_dir)
        model_names = extractor.list_models(workspace)
    else:
        from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        extractor = SemanticLinkExtractor(workspace=workspace)
        model_names = extractor.list_models(workspace)

    console.print(f"Found [bold]{len(model_names)}[/bold] models in workspace.")

    scan_timestamp = datetime.now(timezone.utc).isoformat()
    model_summaries = []

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for name in model_names:
            task = progress.add_task(f"Analyzing {name}...", total=None)
            try:
                result = _run_analysis(name, workspace, output, fmt, False, llm_enrich, mock,
                                        with_copilot=with_copilot)
                model, score = result
                slug = _slugify(name)
                table_count = len(model.tables)
                measure_count = sum(len(t.measures) for t in model.tables)
                # Description coverage: fraction of columns + measures with any description
                total_objs = sum(len(t.columns) + len(t.measures) for t in model.tables)
                described = sum(
                    sum(1 for c in t.columns if c.description or c.ai_description) +
                    sum(1 for m in t.measures if m.description or m.ai_description)
                    for t in model.tables
                )
                desc_coverage = round(described / total_objs, 4) if total_objs > 0 else 0.0
                entry = {
                    "name": name,
                    "slug": slug,
                    "ai_readiness_score": round(score, 4),
                    "table_count": table_count,
                    "measure_count": measure_count,
                    "description_coverage": desc_coverage,
                    "extraction_timestamp": model.extraction_timestamp,
                    "output_directory": f"{slug}/",
                    "errors": [],
                }
                if with_copilot:
                    entry["copilot"] = (
                        model.copilot.signals()
                        if model.copilot is not None
                        else _empty_copilot_signals()
                    )
                model_summaries.append(entry)
            except Exception as e:
                model_summaries.append({
                    "name": name,
                    "slug": _slugify(name),
                    "ai_readiness_score": None,
                    "table_count": None,
                    "measure_count": None,
                    "description_coverage": None,
                    "extraction_timestamp": None,
                    "output_directory": f"{_slugify(name)}/",
                    "errors": [str(e)],
                })
                console.print(f"[yellow]Warning:[/yellow] {name}: {e}")
            progress.remove_task(task)

    # Build summary fields
    scored = [m for m in model_summaries if m["ai_readiness_score"] is not None]
    avg_score = round(sum(m["ai_readiness_score"] for m in scored) / len(scored), 4) if scored else 0.0
    score_ranking = [m["name"] for m in sorted(scored, key=lambda x: x["ai_readiness_score"], reverse=True)]

    recommendations = []
    if scored:
        lowest = min(scored, key=lambda x: x["ai_readiness_score"])
        recommendations.append(
            f"Lowest scoring model: '{lowest['name']}' ({lowest['ai_readiness_score']:.0%})"
            f", run with --llm-enrich to improve"
        )
    low_coverage = [m for m in scored if m["description_coverage"] is not None and m["description_coverage"] < 0.7]
    if low_coverage:
        recommendations.append(
            f"{len(low_coverage)} of {len(model_summaries)} models have description coverage below 70%"
        )

    workspace_summary = {
        "$schema": "https://raw.githubusercontent.com/psistla/fabric-ai-meta/master/schemas/workspace-summary/v1.json",
        "version": "1.0",
        "workspace": workspace,
        "scan_timestamp": scan_timestamp,
        "model_count": len(model_summaries),
        "average_readiness_score": avg_score,
        "models": model_summaries,
        "score_ranking": score_ranking,
        "recommendations": recommendations,
    }
    if with_copilot:
        workspace_summary["copilot_summary"] = _aggregate_copilot_signals(model_summaries)

    _ensure_dir(output)
    summary_path = os.path.join(output, "workspace-summary.json")
    _write_json(summary_path, workspace_summary)
    console.print(f"[green]Workspace summary written to:[/green] {summary_path}")

    # Rankings table
    tbl = Table(title=f"Workspace: {workspace}, {len(model_summaries)} models", show_header=True)
    tbl.add_column("Model")
    tbl.add_column("Score", justify="right")
    tbl.add_column("Tables", justify="right")
    tbl.add_column("Measures", justify="right")
    tbl.add_column("Desc Coverage", justify="right")
    for m in sorted(model_summaries, key=lambda x: (x["ai_readiness_score"] or 0), reverse=True):
        score_str = f"{m['ai_readiness_score']:.2%}" if m["ai_readiness_score"] is not None else "error"
        cov_str = f"{m['description_coverage']:.0%}" if m["description_coverage"] is not None else "-"
        tbl.add_row(m["name"], score_str, str(m["table_count"] or "-"),
                    str(m["measure_count"] or "-"), cov_str)
    console.print(tbl)


# ---------------------------------------------------------------------------
# export commands
# ---------------------------------------------------------------------------

@main.group("export")
def export_group():
    """Export semantic model metadata to framework-specific formats."""
    pass


def _export_single(model_name: str, workspace: str, exporter, mock: bool = False,
                   *, with_copilot: bool = False) -> None:
    """Run a single `BaseExporter` against the extracted model and write its output."""
    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace
    output = cfg.output.output_dir

    console.print(Panel(
        f"[bold]export {exporter.name}[/bold]  model=[cyan]{model_name}[/cyan]  "
        f"workspace=[cyan]{workspace}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        extractor = MockExtractor(fixture_path=_get_fixture_path(model_name))
    else:
        from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        extractor = SemanticLinkExtractor(workspace=workspace)

    model = extractor.extract(model_name, workspace, with_copilot=with_copilot)
    path = exporter.write(model, output)
    if path:
        console.print(f"[green]Written:[/green] {path}")
    else:
        console.print("[yellow]No Copilot/ parts in model definition. Nothing exported.[/yellow]")


def _register_exporter_commands() -> None:
    """Register every discovered exporter (built-in + plugins) as a CLI subcommand."""
    from fabric_ai_meta.generator.registry import discover_exporters

    for ep_name, exporter_cls in discover_exporters().items():
        def _make_cmd(exporter_cls=exporter_cls, ep_name=ep_name):
            @click.command(name=ep_name, help=exporter_cls.description or f"Export {ep_name} format.")
            @click.argument("model_name")
            @click.option("--workspace", "-w", default=None)
            @click.option("--mock", is_flag=True, default=False,
                          help="Use MockExtractor with fixture data.")
            def _cmd(model_name, workspace, mock):
                _export_single(
                    model_name, workspace, exporter_cls(),
                    mock=mock,
                    with_copilot=exporter_cls.requires_copilot,
                )
            return _cmd

        export_group.add_command(_make_cmd())


_register_exporter_commands()


@export_group.command("prep-for-ai")
@click.argument("model_name")
@click.option("--workspace", "-w", default=None)
@click.option("--output", "-o", default=None, help="Output directory.")
@click.option("--mock", is_flag=True, default=False, help="Use MockExtractor with fixture data.")
@click.option("--llm-enrich", is_flag=True, default=False, help="Enable LLM enrichment and description backfill.")
def export_prep_for_ai(model_name, workspace, output, mock, llm_enrich):
    """Export Prep for AI configuration."""
    import dataclasses

    from fabric_ai_meta.analyzer.classifier import (
        classify_column_role,
        classify_measure_heuristic,
        classify_table_heuristic,
    )
    from fabric_ai_meta.generator.prep_for_ai import generate_prep_for_ai

    cfg = load_config()
    workspace = workspace or cfg.extraction.default_workspace
    output = output or cfg.output.output_dir

    console.print(Panel(
        f"[bold]export prep-for-ai[/bold]  model=[cyan]{model_name}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        extractor = MockExtractor(fixture_path=_get_fixture_path(model_name))
    else:
        from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
        if not detect_notebook_environment():
            raise FabricEnvironmentError()
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        extractor = SemanticLinkExtractor(workspace=workspace)

    model = extractor.extract(model_name, workspace)

    for table in model.tables:
        table.table_type = classify_table_heuristic(table, model.relationships)
        for col in table.columns:
            col.role = classify_column_role(col, table, model.relationships)
        for measure in table.measures:
            measure.category = classify_measure_heuristic(measure)

    backfill = None
    llm = None
    if llm_enrich:
        from fabric_ai_meta.llm import load_llm_client
        llm = load_llm_client(cfg)
        backfill = _run_llm_enrichment(model, cfg)

    if llm is None:
        from fabric_ai_meta.llm import load_llm_client
        llm = load_llm_client(cfg)

    prep_config = generate_prep_for_ai(model, llm, backfill=backfill)

    slug = _slugify(model_name)
    out_dir = os.path.join(output, slug)
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
        classify_column_role,
        classify_measure_heuristic,
        classify_table_heuristic,
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
            from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
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
        from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment
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
@click.option("--report", default=None, help="Output file path for governance report JSON.")
@click.option("--output", "-o", default="./output", show_default=True, help="Output directory (report defaults here).")
@click.option("--mock", is_flag=True, default=False, help="Use MockExtractor with fixture files.")
@click.option("--with-copilot", is_flag=True, default=False,
              help="Also extract each model's Copilot/ folder and include the copilot_completeness section.")
def governance(workspace, report, output, mock, with_copilot):
    """Generate cross-model governance report for a workspace."""
    console.print(Panel(
        f"[bold]governance[/bold]  workspace=[cyan]{workspace}[/cyan]",
        title="fabric-ai-meta"
    ))

    from fabric_ai_meta.analyzer.classifier import (
        classify_column_role,
        classify_measure_heuristic,
        classify_table_heuristic,
    )
    from fabric_ai_meta.analyzer.governance import generate_governance_report, write_governance_report
    from fabric_ai_meta.analyzer.scorer import score_model as run_score
    from fabric_ai_meta.auth.entra import FabricEnvironmentError, detect_notebook_environment

    if mock:
        from fabric_ai_meta.extractor.mock import MockExtractor
        extractor = MockExtractor(fixture_dir="tests/fixtures/")
    elif detect_notebook_environment():
        from fabric_ai_meta.extractor.semantic_link import SemanticLinkExtractor
        extractor = SemanticLinkExtractor(workspace=workspace)
    else:
        raise FabricEnvironmentError()

    model_names = extractor.list_models(workspace)

    models = []
    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console) as progress:
        for name in model_names:
            t = progress.add_task(f"Extracting {name}...", total=None)
            try:
                m = extractor.extract(name, workspace, with_copilot=with_copilot)
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
                console.print(f"[yellow]Warning: could not process '{name}': {e}[/yellow]")
            progress.remove_task(t)

    gov_report = generate_governance_report(models)

    report_path = report or os.path.join(output, "governance-report.json")
    write_governance_report(gov_report, workspace, report_path)
    console.print(f"[green]Governance report written to:[/green] {report_path}")

    # Print summary table
    from rich.table import Table
    tbl = Table(title="Model Readiness Ranking")
    tbl.add_column("Model", style="cyan")
    tbl.add_column("Score", justify="right")
    tbl.add_column("Tables", justify="right")
    tbl.add_column("Measures", justify="right")
    for entry in gov_report["score_ranking"]:
        score_str = f"{entry['ai_readiness_score']:.2f}" if entry['ai_readiness_score'] is not None else "N/A"
        tbl.add_row(entry["name"], score_str, str(entry["table_count"]), str(entry["measure_count"]))
    console.print(tbl)
    console.print(f"Naming issues: {gov_report['summary']['total_naming_issues']}  "
                  f"Duplicate measures: {gov_report['summary']['total_duplicate_measures']}")


# ---------------------------------------------------------------------------
# diff command
# ---------------------------------------------------------------------------

@main.command("diff")
@click.argument("baseline_path", type=click.Path(exists=True))
@click.argument("current_path", type=click.Path(exists=True))
@click.option("--output", "-o", type=click.Path(), default=None, help="Write delta report to file.")
@click.option("--format", "fmt", type=click.Choice(["json", "text"]), default="json", help="Output format.")
def diff_cmd(baseline_path: str, current_path: str, output: str | None, fmt: str) -> None:
    """Compare two workspace-summary.json files and show changes."""
    from fabric_ai_meta.analyzer.delta import compare_workspace_summaries, format_delta_text

    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    with open(current_path, "r", encoding="utf-8") as f:
        current = json.load(f)

    delta = compare_workspace_summaries(baseline, current)

    if fmt == "text":
        result = format_delta_text(delta)
    else:
        result = json.dumps(delta, indent=2)

    if output:
        os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
        with open(output, "w", encoding="utf-8") as f:
            f.write(result)
        console.print(f"Delta report written to {output}")
    else:
        click.echo(result)


# ---------------------------------------------------------------------------
# apply-descriptions command
# ---------------------------------------------------------------------------

@main.command("apply-descriptions")
@click.argument("config_path", type=click.Path(exists=True))
@click.option("--workspace", "-w", required=True, help="Fabric workspace name.")
@click.option("--dry-run/--no-dry-run", default=True,
              help="Preview changes without writing (default: dry-run on).")
@click.option("--mock", is_flag=True, default=False,
              help="Use MockWriter for local testing (no service contact).")
def apply_descriptions(config_path, workspace, dry_run, mock):
    """Apply generated descriptions from a prep-for-ai-config.json to a model."""
    console.print(Panel(
        f"[bold]apply-descriptions[/bold]  config=[cyan]{config_path}[/cyan]  "
        f"workspace=[cyan]{workspace}[/cyan]  "
        f"dry_run=[cyan]{dry_run}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception as e:
        console.print(f"[red]Could not read {config_path}: {e}[/red]")
        sys.exit(1)

    descriptions = config_data.get("generated_descriptions", {})
    model_name = config_data.get("model_name") or os.path.basename(
        os.path.dirname(os.path.abspath(config_path))
    )

    try:
        if mock:
            from fabric_ai_meta.writeback.description_writer import MockWriter
            writer = MockWriter()
        else:
            from fabric_ai_meta.auth.entra import (
                FabricEnvironmentError,
                detect_notebook_environment,
            )
            if not detect_notebook_environment():
                raise FabricEnvironmentError()
            from fabric_ai_meta.writeback.description_writer import SemanticLinkWriter
            writer = SemanticLinkWriter()

        result = writer.apply_descriptions(
            model_name=model_name,
            workspace=workspace,
            descriptions=descriptions,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    label = "DRY RUN" if result.dry_run else "APPLIED"
    console.print(
        f"[bold]{label}[/bold]: tables={result.tables_updated}, "
        f"columns={result.columns_updated}, measures={result.measures_updated}, "
        f"total={result.total_changes}"
    )

    if result.changes:
        tbl = Table(title=f"{label}: planned changes", show_header=True)
        tbl.add_column("Type")
        tbl.add_column("Table")
        tbl.add_column("Object")
        tbl.add_column("Old description")
        tbl.add_column("New description")
        for change in result.changes:
            tbl.add_row(
                change["type"],
                change["table"],
                change["object"],
                (change.get("old_description") or "-")[:50],
                (change.get("new_description") or "")[:80],
            )
        console.print(tbl)

    if result.errors:
        console.print("[yellow]Errors:[/yellow]")
        for err in result.errors:
            console.print(f"  - {err}")
        # Exit non-zero on errors so CI gates can detect failed writebacks.
        if not result.dry_run:
            sys.exit(1)


# ---------------------------------------------------------------------------
# apply-copilot command
# ---------------------------------------------------------------------------

@main.command("apply-copilot")
@click.argument("copilot_dir", type=click.Path(exists=True, file_okay=False))
@click.option("--model", "-m", required=True, help="Semantic model name.")
@click.option("--workspace", "-w", required=True, help="Fabric workspace name.")
@click.option("--dry-run/--no-dry-run", default=True,
              help="Preview changes without writing (default: dry-run on).")
@click.option("--mock", is_flag=True, default=False,
              help="Use MockCopilotWriter for local testing (no service contact).")
def apply_copilot(copilot_dir, model, workspace, dry_run, mock):
    """Apply a Copilot/ folder to a semantic model via updateDefinition."""
    console.print(Panel(
        f"[bold]apply-copilot[/bold]  dir=[cyan]{copilot_dir}[/cyan]  "
        f"model=[cyan]{model}[/cyan]  workspace=[cyan]{workspace}[/cyan]  "
        f"dry_run=[cyan]{dry_run}[/cyan]  mock=[cyan]{mock}[/cyan]",
        title="fabric-ai-meta"
    ))

    try:
        from fabric_ai_meta.generator.copilot_reader import CopilotReader
        bundle = CopilotReader.from_directory(copilot_dir)
    except Exception as e:
        console.print(f"[red]Could not load Copilot folder {copilot_dir}: {e}[/red]")
        sys.exit(1)

    try:
        if mock:
            from fabric_ai_meta.writeback.copilot_writer import MockCopilotWriter
            writer = MockCopilotWriter()
        else:
            from fabric_ai_meta.auth.entra import (
                FabricEnvironmentError,
                detect_notebook_environment,
            )
            if not detect_notebook_environment():
                raise FabricEnvironmentError()
            from fabric_ai_meta.writeback.copilot_writer import (
                SemanticLinkCopilotWriter,
            )
            writer = SemanticLinkCopilotWriter()

        result = writer.apply_copilot(
            bundle=bundle,
            model_name=model,
            workspace=workspace,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if result.dry_run:
        label = "DRY RUN"
    elif result.succeeded:
        label = "APPLIED"
    else:
        label = "FAILED"
    console.print(
        f"[bold]{label}[/bold]: "
        f"ai_instructions={result.ai_instructions_updated}, "
        f"verified_answers={result.verified_answers_written}, "
        f"schema={result.ai_data_schema_updated}, "
        f"prompts={result.example_prompts_updated}, "
        f"settings={result.settings_updated}, "
        f"version={result.version_updated}, "
        f"total={result.total_changes}"
    )

    if result.changes:
        tbl = Table(title=f"{label}: planned changes", show_header=True)
        tbl.add_column("Operation")
        tbl.add_column("Primitive")
        tbl.add_column("Path")
        for change in result.changes:
            tbl.add_row(change["operation"], change["primitive"], change["path"])
        console.print(tbl)

    if result.errors:
        console.print("[yellow]Errors:[/yellow]")
        for err in result.errors:
            console.print(f"  - {err}")
        # Exit non-zero on errors so CI gates can detect failed writebacks.
        if not result.dry_run:
            sys.exit(1)


# ---------------------------------------------------------------------------
# serve command (MCP server)
# ---------------------------------------------------------------------------

@main.command("serve")
@click.option("--transport", type=click.Choice(["stdio", "streamable-http"]),
              default="stdio", show_default=True,
              help="Transport for the MCP server.")
@click.option("--port", type=int, default=8000, show_default=True,
              help="Port for the streamable-http transport.")
def serve(transport, port):
    """Start the MCP server exposing fabric-ai-meta tools to AI agents."""
    console.print(Panel(
        f"[bold]serve[/bold]  transport=[cyan]{transport}[/cyan]  port=[cyan]{port}[/cyan]",
        title="fabric-ai-meta"
    ))
    try:
        from fabric_ai_meta.mcp_server import run as run_server
        run_server(transport=transport, port=port)
    except ImportError as e:
        console.print(str(e), markup=False, style="red")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
