# Yigthinker Architecture Decision Records

Each file in this directory records a single architectural decision.

## Rules

- Length: `Lang: en` → ≤500 words. `Lang: zh` → ≤750 CJK chars. Code blocks are excluded from the count.
- Required sections: Context, Decision, Consequences, References.
- Enforced by `scripts/check_adr_format.py` in CI.

## ADRs

| # | Title | Source(s) |
|---|---|---|
| 001 | Why we don't do PGEC | Yigcore ADR-038 + ADR-008 |
| 002 | Intent-first routing | Yigcore ADR-016 |
| 003 | Harness philosophy | Yigcore ADR-036 |
| 004 | Governance as pluggable sidecar | Yigcore ADR-001 + Sentinel 4-layer model |
| 005 | MemoryProvider interface | Yigcore LTM V1 spec (2026-03) |
| 006 | Workflow templating | Yigcore ADR-037 + Compiled Paths |
| 007 | Plugin and skill distribution | Yigcore ADR-014 + ADR-015 |
| 008 | Persona as data | Yigcore PersonaCard 收敛 spec (2026-02-18) |
| 009 | Scheduled reports executor — workflow_deploy sugar + OS hand-off, no in-process scheduler | TODOs.md §"Durable scheduled reports — EXECUTOR" (2026-04-17) |
| 010 | Settings merge precedence — split by semantic class, not by source | 2026-04-18 Teams UAT §UX-2 |
