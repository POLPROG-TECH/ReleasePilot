"""CLI ``generate`` command — full release-notes generation pipeline."""

from __future__ import annotations

import click

from releasepilot.cli.app import cli
from releasepilot.cli.helpers import (
    _ALL_AUDIENCES,
    _ALL_FORMATS,
    _atomic_write_bytes,
    _build_settings,
    _common_options,
    _handle_error,
    _run_dry,
    _run_pipeline,
    console,
)
from releasepilot.cli.validators import (
    validate_export_format_deps,
    validate_export_path,
    validate_settings,
)
from releasepilot.pipeline import orchestrator
from releasepilot.pipeline.orchestrator import PipelineError
from releasepilot.sources.git import GitCollectionError
from releasepilot.sources.structured import StructuredFileError


@cli.command()
@_common_options
@click.option(
    "--audience",
    type=click.Choice(_ALL_AUDIENCES),
    default=None,
    help="Target audience (default: changelog)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(_ALL_FORMATS),
    default=None,
    help="Output format (default: markdown)",
)
@click.option("--show-authors", is_flag=True, help="Include author names")
@click.option("--show-hashes", is_flag=True, help="Include commit hashes")
def generate(
    repo: str,
    from_ref: str,
    to_ref: str,
    source_file: str,
    version_str: str,
    title: str,
    app_name: str,
    lang: str,
    branch: str,
    since_date: str,
    dry_run: bool,
    audience: str,
    output_format: str,
    show_authors: bool,
    show_hashes: bool,
):
    """Generate release notes."""
    # Resolve effective values for pre-settings checks
    eff_format = output_format if output_format is not None else "markdown"

    if eff_format in ("pdf", "docx"):
        err = validate_export_format_deps(eff_format)
        if err:
            err.exit()

    settings = _build_settings(
        repo,
        from_ref,
        to_ref,
        source_file,
        version_str,
        title,
        branch,
        since_date,
        audience,
        output_format,
        show_authors=show_authors,
        show_hashes=show_hashes,
        app_name=app_name,
        lang=lang,
    )

    resolved_audience = settings.audience.value
    resolved_format = eff_format  # pdf/docx not stored in settings directly

    # Executive audience uses a separate rendering pipeline
    if resolved_audience == "executive":
        _run_executive(settings, resolved_format, dry_run)
        return

    # Narrative audiences use the fact-grounded narrative pipeline
    if resolved_audience in ("narrative", "customer-narrative"):
        _run_narrative(settings, resolved_format, dry_run)
        return

    if resolved_format in ("pdf", "docx"):
        _generate_binary(settings, resolved_format, dry_run)
    else:
        output = _run_pipeline(settings, dry_run=dry_run)
        if output:
            click.echo(output)


def _generate_binary(settings, fmt: str, dry_run: bool) -> None:
    """Generate binary output (PDF/DOCX) and save to file."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        release_range = orchestrator.build_release_range(settings)
        items = orchestrator.collect(settings, release_range)
        items, stats = orchestrator.process_with_stats(settings, items)
        notes = orchestrator.compose(settings, items, release_range, stats)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    ext = ".pdf" if fmt == "pdf" else ".docx"
    default_name = f"RELEASE_NOTES{ext}"
    output_path = settings.output_file or default_name

    err = validate_export_path(output_path, allow_overwrite=True)
    if err:
        err.exit()

    if fmt == "pdf":
        from releasepilot.rendering.pdf import PdfRenderer

        data = PdfRenderer().render_bytes(notes, settings.render)
    else:
        from releasepilot.rendering.docx_renderer import DocxRenderer

        data = DocxRenderer().render_bytes(notes, settings.render)

    _atomic_write_bytes(output_path, data)
    console.print(f"[green]✓[/green] Written to {output_path}")


def _build_executive_brief(settings):
    """Run the pipeline and compose an ExecutiveBrief."""
    from releasepilot.audience.executive import compose_executive_brief

    release_range = orchestrator.build_release_range(settings)
    items = orchestrator.collect(settings, release_range)
    items, stats = orchestrator.process_with_stats(settings, items)
    notes = orchestrator.compose(settings, items, release_range, stats)

    period = ""
    if settings.since_date:
        from releasepilot.i18n import get_label

        period = get_label("since_date_label", settings.language).format(
            date=settings.since_date,
        )
    return compose_executive_brief(notes, analysis_period=period)


def _run_executive(settings, output_format: str, dry_run: bool) -> None:
    """Run the executive brief pipeline."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_executive_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.executive_pdf import ExecutivePdfRenderer

        data = ExecutivePdfRenderer().render_bytes(
            brief, lang=settings.language, accent_color=settings.render.accent_color
        )
        output_path = settings.output_file or "RELEASE_BRIEF.pdf"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "docx":
        from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer

        data = ExecutiveDocxRenderer().render_bytes(
            brief, lang=settings.language, accent_color=settings.render.accent_color
        )
        output_path = settings.output_file or "RELEASE_BRIEF.docx"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "json":
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        click.echo(ExecutiveMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        click.echo(ExecutiveMarkdownRenderer().render(brief, lang=settings.language))


def _build_narrative_brief(settings):
    """Run the pipeline and compose a NarrativeBrief."""
    from releasepilot.audience.narrative import compose_narrative

    release_range = orchestrator.build_release_range(settings)
    items = orchestrator.collect(settings, release_range)
    items, stats = orchestrator.process_with_stats(settings, items)
    notes = orchestrator.compose(settings, items, release_range, stats)

    customer_facing = settings.audience.value == "customer-narrative"
    return compose_narrative(notes, customer_facing=customer_facing)


def _run_narrative(settings, output_format: str, dry_run: bool) -> None:
    """Run the narrative brief pipeline."""
    if dry_run:
        _run_dry(settings)
        return

    err = validate_settings(settings)
    if err:
        err.exit()

    try:
        brief = _build_narrative_brief(settings)
    except (PipelineError, GitCollectionError, StructuredFileError) as exc:
        _handle_error(exc)
        return

    if output_format == "pdf":
        from releasepilot.rendering.narrative_pdf import NarrativePdfRenderer

        data = NarrativePdfRenderer().render_bytes(
            brief, lang=settings.language, accent_color=settings.render.accent_color
        )
        output_path = settings.output_file or "NARRATIVE_SUMMARY.pdf"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "docx":
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer

        data = NarrativeDocxRenderer().render_bytes(
            brief, lang=settings.language, accent_color=settings.render.accent_color
        )
        output_path = settings.output_file or "NARRATIVE_SUMMARY.docx"
        err = validate_export_path(output_path, allow_overwrite=True)
        if err:
            err.exit()
        _atomic_write_bytes(output_path, data)
        console.print(f"[green]✓[/green] Written to {output_path}")
    elif output_format == "json":
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

        click.echo(NarrativeMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

        click.echo(NarrativeMarkdownRenderer().render(brief, lang=settings.language))
