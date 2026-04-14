---
phase: quick
plan: 260412-uyf
type: execute
wave: 1
depends_on: []
files_modified:
  - yigthinker/tools/dataframe/df_load.py
  - yigthinker/settings.py
  - tests/test_tools/test_df_load.py
  - tests/test_settings.py
autonomous: true
requirements: []

must_haves:
  truths:
    - "df_load on a multi-sheet Excel file without sheet_name returns sheet list instead of silently reading the first sheet"
    - "df_load on a single-sheet Excel file without sheet_name loads that sheet directly"
    - "df_load with a wrong sheet_name returns error listing available sheets"
    - "Read-only tools execute without permission prompt in default settings"
    - "Write/execute tools still require permission prompt in default settings"
  artifacts:
    - path: "yigthinker/tools/dataframe/df_load.py"
      provides: "Smart Excel sheet enumeration in df_load"
      contains: "pd.ExcelFile"
    - path: "yigthinker/settings.py"
      provides: "Pre-approved read-only tools in DEFAULT_SETTINGS"
      contains: "df_load"
    - path: "tests/test_tools/test_df_load.py"
      provides: "Tests for sheet enumeration behavior"
      contains: "sheet_names"
    - path: "tests/test_settings.py"
      provides: "Test asserting default allow list"
      contains: "default_allow"
  key_links:
    - from: "yigthinker/tools/dataframe/df_load.py"
      to: "pd.ExcelFile"
      via: "sheet_names enumeration before loading"
      pattern: "ExcelFile.*sheet_names"
    - from: "yigthinker/settings.py"
      to: "yigthinker/permissions.py"
      via: "PermissionSystem reads permissions.allow from settings"
      pattern: "allow.*df_load"
---

<objective>
Fix two UX problems from real user sessions: (1) df_load silently reads the first Excel sheet when multiple sheets exist, and (2) every tool call prompts for permission even for read-only tools.

Purpose: Eliminate two friction points that break the analysis flow -- LLM can auto-discover Excel sheet structure, and safe read-only tools run without interrupting the user.
Output: Updated df_load.py with sheet enumeration, updated DEFAULT_SETTINGS with pre-approved tools, and tests for both.
</objective>

<execution_context>
@C:\Users\gaoyu\.claude\get-shit-done\workflows\execute-plan.md
@C:\Users\gaoyu\.claude\get-shit-done\templates\summary.md
</execution_context>

<context>
@yigthinker/tools/dataframe/df_load.py
@yigthinker/settings.py
@yigthinker/permissions.py
@tests/test_tools/test_df_load.py
@tests/test_settings.py

<interfaces>
<!-- Key types and contracts the executor needs. -->

From yigthinker/types.py:
```python
class ToolResult:
    tool_use_id: str
    content: str | dict
    is_error: bool = False
```

From yigthinker/session.py:
```python
class SessionContext:
    vars: VarRegistry
    context_manager: ContextManager
```

From yigthinker/permissions.py:
```python
class PermissionSystem:
    def __init__(self, permissions: dict[str, list[str]]) -> None:
        self._allow: list[str] = permissions.get("allow", [])
        # ...
    def check(self, tool_name, tool_input=None, session_id=None) -> PermissionDecision:
        # deny > allow > session_override > ask > default(ask)
```

From yigthinker/settings.py:
```python
DEFAULT_SETTINGS: dict[str, Any] = {
    "permissions": {"allow": [], "ask": [], "deny": []},
    # ...
}
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add Excel sheet enumeration to df_load</name>
  <files>yigthinker/tools/dataframe/df_load.py, tests/test_tools/test_df_load.py</files>
  <behavior>
    - Test: multi-sheet Excel without sheet_name returns content dict with "available_sheets" list and "message" prompting selection (is_error=False, no DataFrame loaded)
    - Test: single-sheet Excel without sheet_name loads that sheet directly (same as current CSV behavior)
    - Test: Excel with wrong sheet_name returns is_error=True with error message containing available sheet names
    - Test: Excel with correct sheet_name loads that sheet (existing behavior preserved)
  </behavior>
  <action>
    In `tests/test_tools/test_df_load.py`:
    - Add an `xlsx_multi_sheet` fixture that creates a tmp .xlsx file with 2 sheets ("Revenue" with data, "Costs" with data) using `pd.ExcelWriter`
    - Add an `xlsx_single_sheet` fixture with 1 sheet
    - Add `test_load_excel_multi_sheet_enumerates_sheets`: call df_load without sheet_name on the multi-sheet file. Assert is_error=False, content contains "available_sheets" key with ["Revenue", "Costs"], var_name NOT in ctx.vars (nothing loaded yet)
    - Add `test_load_excel_single_sheet_loads_directly`: call df_load without sheet_name on single-sheet file. Assert is_error=False, var_name IS in ctx.vars, df has expected data
    - Add `test_load_excel_wrong_sheet_name_shows_available`: call with sheet_name="Nonexistent" on multi-sheet file. Assert is_error=True, content string contains "Revenue" and "Costs"
    - Add `test_load_excel_correct_sheet_name`: call with sheet_name="Revenue" on multi-sheet file. Assert loads correctly

    In `yigthinker/tools/dataframe/df_load.py`:
    - After the loader lookup and before calling the loader, add Excel sheet enumeration logic for .xlsx/.xls files:
      ```python
      if suffix in (".xlsx", ".xls"):
          xls = pd.ExcelFile(path)
          sheets = xls.sheet_names

          if input.sheet_name and input.sheet_name not in sheets:
              return ToolResult(
                  tool_use_id="",
                  content=f"Sheet '{input.sheet_name}' not found. Available sheets: {sheets}",
                  is_error=True,
              )

          if not input.sheet_name and len(sheets) > 1:
              return ToolResult(
                  tool_use_id="",
                  content={
                      "message": f"This Excel file has {len(sheets)} sheets. Specify sheet_name to load one.",
                      "available_sheets": sheets,
                  },
              )

          # Single sheet or explicit sheet_name — proceed with loading
          if not input.sheet_name:
              kwargs["sheet_name"] = sheets[0]
      ```
    - Keep existing kwargs logic for header/skiprows/usecols unchanged
    - Wrap pd.ExcelFile in the existing try/except so file errors are handled
  </action>
  <verify>
    <automated>cd C:/Users/gaoyu/Documents/GitHub/Yigthinker && .venv/Scripts/python -m pytest tests/test_tools/test_df_load.py -x -v</automated>
  </verify>
  <done>Multi-sheet Excel returns sheet list for LLM selection; single-sheet loads directly; wrong sheet_name error includes available sheets; all existing df_load tests still pass</done>
</task>

<task type="auto">
  <name>Task 2: Pre-approve read-only tools in DEFAULT_SETTINGS</name>
  <files>yigthinker/settings.py, tests/test_settings.py</files>
  <action>
    In `yigthinker/settings.py`:
    - Change `"permissions": {"allow": [], "ask": [], "deny": []}` to:
      ```python
      "permissions": {
          "allow": [
              "df_load",
              "df_profile",
              "df_merge",
              "schema_inspect",
              "explore_overview",
              "explore_drilldown",
              "explore_anomaly",
              "chart_create",
              "chart_modify",
              "chart_recommend",
              "forecast_timeseries",
              "forecast_regression",
              "forecast_evaluate",
              "finance_calculate",
              "finance_analyze",
              "finance_validate",
          ],
          "ask": [],
          "deny": [],
      }
      ```
    - Note: `sql_query`, `sql_explain`, `df_transform`, `report_generate`, `report_template`, `report_schedule`, `workflow_generate`, `workflow_deploy`, `workflow_manage`, `suggest_automation`, `spawn_agent`, `agent_status`, `agent_cancel`, `finance_budget` are intentionally NOT in allow — they either write data, execute code, cost money, or produce artifacts

    In `tests/test_settings.py`:
    - Add `test_default_allow_includes_readonly_tools`: assert that DEFAULT_SETTINGS["permissions"]["allow"] contains the 16 read-only tools listed above
    - Add `test_default_allow_excludes_write_tools`: assert that `sql_query`, `df_transform`, `workflow_deploy`, `spawn_agent` are NOT in DEFAULT_SETTINGS["permissions"]["allow"]
    - Fix existing `test_load_settings_project_overrides_defaults`: this test currently asserts `allow == ["chart_create"]` after project override — this should still pass because _deep_merge replaces the list entirely (list override, not list merge). Verify it still passes.
  </action>
  <verify>
    <automated>cd C:/Users/gaoyu/Documents/GitHub/Yigthinker && .venv/Scripts/python -m pytest tests/test_settings.py -x -v</automated>
  </verify>
  <done>DEFAULT_SETTINGS has 16 read-only tools in permissions.allow; write/execute tools not in allow list; project-level overrides still work via _deep_merge; all settings tests pass</done>
</task>

</tasks>

<verification>
Run full test suite for both changed modules:
```bash
cd C:/Users/gaoyu/Documents/GitHub/Yigthinker && .venv/Scripts/python -m pytest tests/test_tools/test_df_load.py tests/test_settings.py -v
```
</verification>

<success_criteria>
- df_load with multi-sheet Excel and no sheet_name returns available_sheets list (not empty DataFrame)
- df_load with single-sheet Excel and no sheet_name loads directly
- df_load with wrong sheet_name returns error with available sheet names
- DEFAULT_SETTINGS permissions.allow contains 16 read-only tools
- Write/execute tools (sql_query, df_transform, workflow_deploy, spawn_agent) remain ask-by-default
- All existing tests continue to pass
</success_criteria>

<output>
After completion, create `.planning/quick/260412-uyf-optimize-df-load-excel-sheet-enumeration/260412-uyf-SUMMARY.md`
</output>
