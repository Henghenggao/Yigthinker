"""E2E Simulation: FCST 2+10 Monthly P&L via Yigthinker tool chain.

Simulates an LLM-driven session where the agent:
  1. df_load   -- loads the SAP BPC Excel export
  2. explore_overview -- profiles the raw data
  3. df_transform (x3) -- cleans, pivots, formats into monthly P&L
  4. report_generate -- exports the final P&L to Excel

No real LLM is called; we replay the exact tool_use sequence the LLM
would produce, but execute each tool through the real Yigthinker pipeline
(SessionContext => VarRegistry => Tool.execute => ToolResult).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

# -- Yigthinker imports ----------------------------------------------
from yigthinker.session import SessionContext
from yigthinker.tools.dataframe.df_load import DfLoadTool, DfLoadInput
from yigthinker.tools.dataframe.df_transform import DfTransformTool, DfTransformInput
from yigthinker.tools.exploration.explore_overview import ExploreOverviewTool, ExploreOverviewInput
from yigthinker.tools.reports.report_generate import ReportGenerateTool, ReportGenerateInput
from yigthinker.types import ToolResult

# -- Paths -----------------------------------------------------------
INPUT_FILE = Path("C:/Users/gaoyu/Downloads/FCST_2+10.xlsx")
OUTPUT_FILE = Path("C:/Users/gaoyu/Downloads/FCST_2+10_PNL_Yigthinker.xlsx")


def _print_result(step: str, tool_name: str, result: ToolResult) -> None:
    """Pretty-print a tool result like the agent loop would show it."""
    status = "ERROR" if result.is_error else "OK"
    print(f"\n{'='*80}")
    print(f"[{step}] tool_use: {tool_name}  =>  {status}")
    print(f"{'='*80}")
    if isinstance(result.content, dict):
        # Truncate large preview dicts
        for k, v in result.content.items():
            if isinstance(v, dict) and len(str(v)) > 500:
                print(f"  {k}: <{len(v)} items>")
            elif isinstance(v, str) and len(v) > 300:
                print(f"  {k}: {v[:300]}…")
            else:
                print(f"  {k}: {v}")
    else:
        text = str(result.content)
        print(f"  {text[:500]}")
    if result.is_error:
        raise RuntimeError(f"Tool {tool_name} failed: {result.content}")


async def run_simulation() -> None:
    """Replay the tool-call sequence for the FCST 2+10 Monthly P&L task."""

    # -- Bootstrap ---------------------------------------------------
    ctx = SessionContext(settings={}, channel_origin="simulation")
    df_load = DfLoadTool()
    df_transform = DfTransformTool()
    explore = ExploreOverviewTool()
    report_gen = ReportGenerateTool()

    print("\n" + "=" * 80)
    print("  Yigthinker E2E Simulation -- FCST 2+10 Monthly P&L")
    print("  User query: 'Clean FCST_2+10.xlsx, build monthly PNL with months as columns'")
    print("=" * 80)

    # -- Step 1: df_load ---------------------------------------------
    # LLM decides: "I need to load the Excel data first. The main data
    # is in the 'Retrieve_Retrieve_Rep.' sheet."
    r1 = await df_load.execute(
        DfLoadInput(
            source=str(INPUT_FILE),
            var_name="raw",
            sheet_name="Retrieve_Retrieve_Rep.",
            header=None,        # FIX: no standard header row
            skiprows=3,         # FIX: skip SAP BPC metadata rows
            usecols="A:L",      # FIX: only columns A through L have data
        ),
        ctx,
    )
    _print_result("Step 1/6", "df_load", r1)

    # -- Step 2: explore_overview ------------------------------------
    # LLM decides: "Let me understand the dataset structure first."
    r2 = await explore.execute(
        ExploreOverviewInput(var_name="raw"),
        ctx,
    )
    _print_result("Step 2/6", "explore_overview", r2)

    # -- Step 3: df_transform -- clean --------------------------------
    # LLM decides: "The raw data has unnamed columns (0-21) from the
    # header-less read. I need to assign proper names, skip the meta
    # rows, strip whitespace, and coerce numeric columns."
    r3 = await df_transform.execute(
        DfTransformInput(
            input_var="raw",
            output_var="clean",
            code="""\
import pandas as pd  # FIX VALIDATED: import now works in sandbox

# df_load already skipped metadata rows and selected cols A:L
# Columns are 0..11 (positional, since header=None)
col_names = ['composite_key1', 'composite_key2', 'bu', 'region',
             'customer_segment', 'statement_type', 'department',
             'pnl_line', 'fiscal_year', 'month',
             'value_total_plan', 'value_business_solutions']
clean = df.copy()
clean.columns = col_names

# Strip whitespace from text columns
text_cols = ['bu', 'region', 'customer_segment', 'statement_type',
             'department', 'pnl_line']
for c in text_cols:
    clean[c] = clean[c].astype(str).str.strip()

# Coerce numeric
clean['value_total_plan'] = pd.to_numeric(clean['value_total_plan'], errors='coerce').fillna(0)
clean['value_business_solutions'] = pd.to_numeric(clean['value_business_solutions'], errors='coerce').fillna(0)

# Drop composite keys (redundant)
result = clean.drop(columns=['composite_key1', 'composite_key2'])
""",
        ),
        ctx,
    )
    _print_result("Step 3/6", "df_transform (clean)", r3)

    # -- Step 4: df_transform -- pivot to monthly P&L -----------------
    # LLM decides: "Now I'll create the monthly P&L pivot: rows = P&L
    # line items, columns = months Jan..Dec, values = sum of value_total_plan."
    r4 = await df_transform.execute(
        DfTransformInput(
            input_var="clean",
            output_var="monthly_pnl",
            code="""\
# pd is pre-injected
month_order = ['Jan','Feb','Mar','Apr','May','Jun',
               'Jul','Aug','Sep','Oct','Nov','Dec']

pnl_order = [
    'Order Intake FA',
    'Net Sales FA',
    'Cost of Sales',
    'Gross Profit',
    'SG&A',
    'R&D',
    'Holding Costs FA',
    'License Recharge FA',
    'OOI/OOE',
    'Non-Recurring Items FA',
    'PPA FA',
    'Financial Result',
    'Other Financial Result',
    'Tax FA',
]

# Aggregate across all regions and departments
agg = df.groupby(['pnl_line', 'month'])['value_total_plan'].sum().reset_index()

# Pivot: rows=pnl_line, columns=month
pivot = agg.pivot(index='pnl_line', columns='month', values='value_total_plan')
pivot = pivot.reindex(columns=month_order).reindex(pnl_order).fillna(0)

# Add FY Total
pivot['FY24 Total'] = pivot[month_order].sum(axis=1)

# Round to integers for readability
result = pivot.round(0).astype(int)
""",
        ),
        ctx,
    )
    _print_result("Step 4/6", "df_transform (pivot)", r4)

    # -- Step 5: df_transform -- by-region breakdown ------------------
    # LLM decides: "User might want a regional breakdown too. Let me
    # also prepare that."
    r5 = await df_transform.execute(
        DfTransformInput(
            input_var="clean",
            output_var="pnl_by_region",
            code="""\
# pd is pre-injected
month_order = ['Jan','Feb','Mar','Apr','May','Jun',
               'Jul','Aug','Sep','Oct','Nov','Dec']
pnl_order = [
    'Order Intake FA', 'Net Sales FA', 'Cost of Sales', 'Gross Profit',
    'SG&A', 'R&D', 'Holding Costs FA', 'License Recharge FA',
    'OOI/OOE', 'Non-Recurring Items FA', 'PPA FA',
    'Financial Result', 'Other Financial Result', 'Tax FA',
]

# Build a multi-level pivot: region x pnl_line => months
agg = df.groupby(['region', 'pnl_line', 'month'])['value_total_plan'].sum().reset_index()
pivot = agg.pivot_table(
    index=['region', 'pnl_line'],
    columns='month',
    values='value_total_plan',
    aggfunc='sum',
)
pivot = pivot.reindex(columns=month_order).fillna(0)
pivot['FY24 Total'] = pivot[month_order].sum(axis=1)

# Sort by region, then by pnl_order within each region
order_map = {name: i for i, name in enumerate(pnl_order)}
sort_keys = [(region, order_map.get(pnl, 99)) for region, pnl in pivot.index]
sort_order = sorted(range(len(sort_keys)), key=lambda i: sort_keys[i])
pivot = pivot.iloc[sort_order]
result = pivot.round(0).astype(int)
""",
        ),
        ctx,
    )
    _print_result("Step 5/6", "df_transform (by_region)", r5)

    # -- Step 6: report_generate -- export to Excel -------------------
    # LLM decides: "Now I'll export the monthly P&L to an Excel report."
    r6 = await report_gen.execute(
        ReportGenerateInput(
            var_name="monthly_pnl",
            format="excel",
            output_path=str(OUTPUT_FILE),
            title="FY24 FCST 2+10 -- Monthly P&L -- SCS EMEA (EUR)",
            sheet_name="Monthly PNL",
        ),
        ctx,
    )
    _print_result("Step 6/6", "report_generate", r6)

    # -- Final summary (what the LLM would respond) ------------------
    pnl_df = ctx.vars.get("monthly_pnl")
    print("\n" + "=" * 80)
    print("  AGENT RESPONSE (simulated)")
    print("=" * 80)
    print("""
Data cleaned and organized into Monthly P&L.

VarRegistry state:
""")
    for info in ctx.vars.list():
        print(f"  - {info.name}: {info.shape[0]} rows x {info.shape[1]} cols ({info.var_type})")

    print(f"\nOutput: {OUTPUT_FILE}")
    print(f"\n{'-'*80}")
    print("FY24 Forecast 2+10 -- Monthly P&L (EUR, Total Plan)")
    print("Actuals: Jan-Feb | Forecast: Mar-Dec (Working)")
    print(f"{'-'*80}")

    pd_opts = {
        'display.float_format': '{:,.0f}'.format,
        'display.width': 200,
        'display.max_columns': 15,
    }
    import pandas as pd
    for k, v in pd_opts.items():
        pd.set_option(k, v)
    print(pnl_df.to_string())

    # Key metrics
    ns = pnl_df.loc['Net Sales FA', 'FY24 Total']
    cos = pnl_df.loc['Cost of Sales', 'FY24 Total']
    gp = pnl_df.loc['Gross Profit', 'FY24 Total']
    sga = pnl_df.loc['SG&A', 'FY24 Total']
    rd = pnl_df.loc['R&D', 'FY24 Total']
    oi = pnl_df.loc['Order Intake FA', 'FY24 Total']

    print("\nKey Metrics (FY24):")
    print(f"  Order Intake:   {oi:>15,}")
    print(f"  Net Sales:      {ns:>15,}")
    print(f"  Cost of Sales:  {cos:>15,}")
    print(f"  Gross Profit:   {gp:>15,}")
    print(f"  SG&A:           {sga:>15,}")
    print(f"  R&D:            {rd:>15,}")

    print(f"\n{'='*80}")
    print("  Simulation PASSED OK")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    asyncio.run(run_simulation())
