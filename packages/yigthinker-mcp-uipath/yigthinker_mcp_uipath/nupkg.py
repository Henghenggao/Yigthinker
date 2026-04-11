"""On-the-fly UiPath Cross-Platform Python .nupkg builder.

Implemented in Plan 11-04 per CONTEXT.md D-15..D-18 and RESEARCH.md Finding 4.
Will expose ``build_nupkg(script_path, workflow_name, version) -> bytes``.
"""
from __future__ import annotations
