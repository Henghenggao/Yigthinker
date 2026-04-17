# skill-pptx audit — 2026-04-17

**Source:** `C:/Users/gaoyu/Documents/GitHub/Yigcore/packages/skills/skill-pptx/engine/`
**Scope:** 1974 LOC Python, 8 modules + 1 smoke test
**Original deployment form:** MCP-over-Docker service (Node MCP wrapper in sibling `src/`, Python engine in `engine/`)

## Dimensions (1–5, 5 = best)

| Dimension | Score | Notes |
|---|---|---|
| API cleanliness | 4 | `main.py` is a thin JSON-stdin/stdout dispatcher, not MCP-coupled; all engine modules expose plain functions (`parse_template`, `create_from_scratch`, `update_slides`, `insert_chart`, `add_comments`, `generate_snapshots`, `export_file`). No global state, no `mcp` imports anywhere in `engine/`. Mild camelCase/snake_case duality in kwargs. |
| Test coverage | 3 | One `test_engine_smoke.py` exercises a realistic end-to-end path: create → parse → update text → insert bar chart (Q1/Q2/Q3 revenue) → add comment → re-parse and assert `has_chart`. Covers the main render path but no per-module unit tests, no edge cases (missing placeholders, malformed input, unsupported shapes). |
| Dependency footprint | 4 | `requirements.txt` is 4 lines: `python-pptx>=1.0`, `lxml>=5.0`, `pydantic>=2.0`, `Pillow>=10.0`. All pure-Python-ish, already standard. `snapshot_generator.py` and `export_file(pdf)` shell out to LibreOffice via `subprocess` — optional and gracefully falls back to Pillow-drawn placeholder PNGs when absent. No ML/cloud deps. |
| Financial-report fitness | 4 | `chart_handler.insert_chart` builds native editable PowerPoint charts from `{categories, series}` — trivially mappable from a pandas DataFrame (bar, column, line, pie, area, scatter; waterfall falls back to column). `template_updater._update_table_data` supports header + rows (P&L / BS / CF tables). Template-driven via `update_slides` with placeholder-idx targeting and run-level format preservation. Real `.pptx` output. Gap: no built-in three-statement templates; caller must supply `.pptx` template or assemble with `create_from_scratch`. |

**Aggregate:** 3.75 / 5

## Verdict: ACCEPT

Rationale: The engine is self-contained pure-Python on top of `python-pptx`/`lxml`, with zero MCP protocol coupling inside `engine/` — the MCP transport lives in the sibling Node `src/` tree and is discarded on import. Each module is a short (~100–355 LOC) set of flat functions that already match the shape we want for a `YigthinkerTool` adapter on `report_generate`. The financial-report use case (pandas DataFrame → categories/series chart + placeholder tables on a template) is first-class, and LibreOffice dependency is optional and isolated to snapshot/PDF paths we can defer.

## If ACCEPT
- Target path: `yigthinker/tools/reports/pptx_engine/`
- Budget: ≤5 workdays
- Adapter needed: wrap into `YigthinkerTool` protocol for `report_generate`
- New deps: python-pptx (optional extra)

## If WRAP
- Write a ~300 LOC `python-pptx` wrapper in `yigthinker/tools/reports/pptx_wrapper.py`
- Budget: ≤3 workdays
- Don't port any Yigcore code

## If DEFER / REJECT
- No code change
- `report_generate` retains current PDF-only behavior
- Re-audit in Phase 2 or 3
