"""CLI ``export`` command — write release notes to a file."""

from __future__ import annotations

import click

from releasepilot.cli.app import cli
from releasepilot.cli.helpers import (
    _ALL_AUDIENCES,
    _ALL_FORMATS,
    _atomic_write_bytes,
    _atomic_write_text,
    _build_settings,
    _common_options,
    _handle_error,
    _run_dry,
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
@click.option("-o", "--output", "output_file", required=True, help="Output file path")
@click.option("--show-authors", is_flag=True, help="Include author names")
@click.option("--show-hashes", is_flag=True, help="Include commit hashes")
def export(
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
    output_file: str,
    show_authors: bool,
    show_hashes: bool,
):
    """Write release notes to a file."""
    # Resolve effective values for pre-settings checks
    eff_format = output_format if output_format is not None else "markdown"

    # Validate export format deps early
    if eff_format in ("pdf", "docx"):
        err = validate_export_format_deps(eff_format)
        if err:
            err.exit()

    # Validate output path
    err = validate_export_path(output_file, allow_overwrite=True)
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
        output_file=output_file,
        show_authors=show_authors,
        show_hashes=show_hashes,
        app_name=app_name,
        lang=lang,
    )

    if dry_run:
        _run_dry(settings)
        return

    resolved_audience = settings.audience.value
    resolved_format = eff_format

    # Executive audience uses a separate rendering pipeline
    if resolved_audience == "executive":
        _export_executive(settings, resolved_format, output_file)
        return

    # Narrative audiences use the fact-grounded narrative pipeline
    if resolved_audience in ("narrative", "customer-narrative"):
        _export_narrative(settings, resolved_format, output_file)
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

    if resolved_format in ("pdf", "docx"):
        if resolved_format == "pdf":
            from releasepilot.rendering.pdf import PdfRenderer

            data = PdfRenderer().render_bytes(notes, settings.render)
        else:
            from releasepilot.rendering.docx_renderer import DocxRenderer

            data = DocxRenderer().render_bytes(notes, settings.render)
        _atomic_write_bytes(output_file, data)
    else:
        output = orchestrator.render(settings, notes)
        _atomic_write_text(output_file, output)

    console.print(f"[green]✓[/green] Written to {output_file}")


def _export_executive(settings, output_format: str, output_file: str) -> None:
    """Export an executive brief to a file."""
    from releasepilot.cli.cmd_generate import _build_executive_brief

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

        _atomic_write_bytes(
            output_file,
            ExecutivePdfRenderer().render_bytes(
                brief, lang=settings.language, accent_color=settings.render.accent_color
            ),
        )
    elif output_format == "docx":
        from releasepilot.rendering.executive_docx import ExecutiveDocxRenderer

        _atomic_write_bytes(
            output_file,
            ExecutiveDocxRenderer().render_bytes(
                brief, lang=settings.language, accent_color=settings.render.accent_color
            ),
        )
    elif output_format == "json":
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        _atomic_write_text(output_file, ExecutiveMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.executive_md import ExecutiveMarkdownRenderer

        _atomic_write_text(
            output_file, ExecutiveMarkdownRenderer().render(brief, lang=settings.language)
        )

    console.print(f"[green]✓[/green] Written to {output_file}")


def _export_narrative(settings, output_format: str, output_file: str) -> None:
    """Export a narrative brief to a file."""
    from releasepilot.cli.cmd_generate import _build_narrative_brief

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

        _atomic_write_bytes(
            output_file,
            NarrativePdfRenderer().render_bytes(
                brief, lang=settings.language, accent_color=settings.render.accent_color
            ),
        )
    elif output_format == "docx":
        from releasepilot.rendering.narrative_docx import NarrativeDocxRenderer

        _atomic_write_bytes(
            output_file,
            NarrativeDocxRenderer().render_bytes(
                brief, lang=settings.language, accent_color=settings.render.accent_color
            ),
        )
    elif output_format == "json":
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

        _atomic_write_text(output_file, NarrativeMarkdownRenderer().render_json(brief))
    else:
        from releasepilot.rendering.narrative_md import NarrativeMarkdownRenderer

        _atomic_write_text(
            output_file, NarrativeMarkdownRenderer().render(brief, lang=settings.language)
        )

    console.print(f"[green]✓[/green] Written to {output_file}")
