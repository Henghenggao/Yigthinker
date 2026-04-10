"""Power Automate guided-mode bundle builder.

Packs the 3 PA templates into flow_import.zip with PA's expected paths.
Per Pattern 5 research: definition.json must live at
    Microsoft.Flow/flows/<workflow_name>/definition.json

The bundle is importable via flow.microsoft.com > My flows > Import
Package (Legacy).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yigthinker.tools.workflow.template_engine import TemplateEngine


def build_pa_bundle(
    *,
    workflow_name: str,
    variables: dict,
    engine: "TemplateEngine",
    output_dir: Path,
) -> Path:
    """Assemble flow_import.zip and return its path.

    Args:
        workflow_name: Stable internal id used as the subfolder name under
            Microsoft.Flow/flows/. Keep this equal to the registry key.
        variables: Template context passed to ``engine.render_text``. Must
            include ``display_name``, ``description``, ``cron_expression``,
            ``recurrence_frequency``, ``recurrence_interval``,
            ``registration_date``.
        engine: Phase 8 TemplateEngine with render_text() (Phase 9).
        output_dir: Directory to write the zip into; created if missing.

    Returns:
        Absolute path to the written ``flow_import.zip``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / "flow_import.zip"

    # Render each template through the sandboxed engine (credential scanner).
    workflow_json = engine.render_text("pa/workflow.json.j2", variables)
    api_props = engine.render_text("pa/apiProperties.json.j2", variables)
    definition_vars = {**variables, "workflow_name": workflow_name}
    definition = engine.render_text(
        "pa/definition.json.j2", definition_vars,
    )

    # Canonical PA paths - the subfolder name is the flow's internal id.
    definition_path_in_zip = (
        f"Microsoft.Flow/flows/{workflow_name}/definition.json"
    )

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("workflow.json", workflow_json)
        zf.writestr("apiProperties.json", api_props)
        zf.writestr(definition_path_in_zip, definition)

    return bundle_path
