"""UiPath guided-mode bundle builder.

Packs project.json + Main.xaml into process_package.zip. User renames to
.nupkg before importing in UiPath Studio (Studio refuses .zip). An
optional .nuspec is NOT required for Studio import; Orchestrator publish
re-packs the package with a proper .nuspec automatically.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yigthinker.tools.workflow.template_engine import TemplateEngine


def build_uipath_bundle(
    *,
    workflow_name: str,
    variables: dict,
    engine: "TemplateEngine",
    output_dir: Path,
) -> Path:
    """Assemble process_package.zip and return its path.

    Args:
        workflow_name: Stable internal id used as project name in
            project.json. Keep equal to the registry key.
        variables: Template context passed to ``engine.render_text``. Must
            include ``display_name``, ``description``, ``python_exe``,
            ``registration_date``.
        engine: Phase 8 TemplateEngine with render_text() (Phase 9).
        output_dir: Directory to write the zip into; created if missing.

    Returns:
        Absolute path to the written ``process_package.zip``.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = output_dir / "process_package.zip"

    vars_with_name = {**variables, "workflow_name": workflow_name}
    project_json = engine.render_text(
        "uipath/project.json.j2", vars_with_name,
    )
    main_xaml = engine.render_text(
        "uipath/main.xaml.j2", vars_with_name,
    )

    with zipfile.ZipFile(bundle_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("project.json", project_json)
        zf.writestr("Main.xaml", main_xaml)

    return bundle_path
