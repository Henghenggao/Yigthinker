---
description: Accounts receivable aging report — bucket open invoices, drill down on 90+ accounts, produce xlsx + chart, offer automation
argument-hint: [as-of-date YYYY-MM-DD, default=today]
allowed-tools: sql_query,schema_inspect,df_transform,df_merge,finance_analyze,chart_create,excel_write,suggest_automation
---

You are executing the **AR Aging Report** ritual. Deliver a finished artifact — do NOT describe the process in prose. Follow these steps exactly:

## 1. Verify the AR data source

Call `schema_inspect` on the finance connection. Confirm there is a table that looks like accounts receivable (candidate names: `accounts_receivable`, `ar`, `invoices_open`, `receivables`). If multiple match, pick the one whose column set best matches AR semantics (customer + invoice amount + due date + optional status).

If NO AR-shaped table exists, STOP and ask the user one question: "I don't see an accounts receivable table in the configured connection. Which table holds your open invoices?" — then wait for their answer before continuing.

## 2. Pull open AR as of the target date

Compose a `sql_query` that returns open invoices as of the target date (default: today, unless the user provided one):

- Columns required: `customer_id` (or equivalent), `customer_name` (if available), `invoice_id`, `amount_due`, `due_date`
- Filter: only open / unpaid invoices (status field, or amount_paid < amount)
- Store the result as a DataFrame named `ar_open`

## 3. Compute aging buckets

Use `df_transform` to add an `age_bucket` column based on (target_date - due_date) days:
- `"0-30"` — 0 to 30 days past due (or not yet due)
- `"31-60"` — 31 to 60 days past due
- `"61-90"` — 61 to 90 days past due
- `"90+"` — more than 90 days past due

Group by bucket and sum `amount_due`. Store the summary DataFrame as `ar_aging_summary`.

## 4. Drill down on 90+ accounts

If the `90+` bucket total is non-zero, produce a second DataFrame `ar_aging_90plus_detail` sorted by `amount_due` descending, showing the top 20 aged accounts (customer + amount + days past due). These are the conversations the AR team needs to have this week.

## 5. Produce a chart of the bucket totals

Call `chart_create(chart_type="bar", var_name="ar_aging_summary", x="age_bucket", y="amount_due", title="AR Aging by Bucket — as of <date>")`. Store the chart as `ar_aging_chart`.

## 6. Export the formatted xlsx

Call `excel_write`:
- `input_var="ar_aging_summary"`
- `sheet_name="Aging Summary"`
- `embed_chart="ar_aging_chart"` — this embeds the native openpyxl chart alongside the data
- `number_format={"amount_due": "#,##0.00;[Red]-#,##0.00"}`
- `freeze_pane="A2"`

If the 90+ detail DataFrame was produced in step 4, write that too as a second sheet via a second `excel_write` call using `base_file` pointing at the workbook from the first call and `sheet_name="90+ Detail"`.

## 7. Narrate the result

Give the user a SHORT reply (2-3 sentences) covering:
- Total open AR (sum across buckets)
- Percent in the `90+` bucket
- The single largest 90+ account by name or ID (if detail is available)
- Link to the Excel artifact (the channel adapter delivers the download button automatically)

## 8. Offer automation (REQUIRED)

Call `suggest_automation` and then explicitly ask the user: **"Want me to make this a recurring automation — runs every Monday morning, emails you the Excel?"** If yes, call `workflow_generate` with the ar-aging pattern and offer `workflow_deploy` in local / guided / auto mode. This is the RPA-first hand-off that turns a one-shot analysis into a deployed workflow; do not skip it.

## Constraints

- Never invent data — if the schema doesn't match what the recipe expects, stop and ask.
- Never commit to delivery without running `excel_write` — this command's contract is to produce a file, not to describe one.
- Currency formatting must respect the connection's configured currency (default EUR for Yigthinker sample DBs).
