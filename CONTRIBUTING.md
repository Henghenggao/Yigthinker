# Contributing to Yigthinker

Thanks for considering a contribution. This project is pre-1.0 and evolving fast — please read the policies below before opening a PR so we don't waste each other's time.

## Quick links

- Design specs: `docs/superpowers/specs/` (local-only, ask if you need access)
- Architecture decisions: `docs/adr/README.md`
- Development context: `CLAUDE.md` (local — mirrored by `README.md` "Architecture" section for public readers)

## Core policies

### 1. No-custom-code rule

Every feature request becomes a product feature merged into the open-source core, or it gets rejected. **There are no customer-specific forks, branches, or code paths.** Consulting engagements pay for setup, configuration, training, and prioritisation — not for custom code that never returns to the main codebase.

If you're requesting a feature that only makes sense for one organisation, consider contributing it as a plugin under `.yigthinker/plugins/` (user-level) rather than core. See `docs/adr/007-plugin-and-skill-distribution.md`.

### 2. Headless product invariant

Yigthinker is **CLI + IM bot + Gateway API**. No web dashboard. PRs that add a web UI, Streamlit app, FastAPI HTML renderer, or similar will be closed. See `.planning/project_dashboard_cut.md` (local) for the 2026-04-08 rationale.

If users need a web view, the correct answer is Streamlit / Grafana / Metabase consuming the Gateway API — not code inside this repo.

### 3. Architect-not-executor

The core agent **generates** automation and **does not run** automation. Scheduled workflows, RPA jobs, and deployed scripts execute on traditional RPA platforms (Power Automate, UiPath) or OS schedulers — never inside the Yigthinker process itself.

PRs that add in-process schedulers (APScheduler, Celery, custom cron), in-process RPA runners, or similar are rejected on principle. See `docs/adr/009-scheduled-reports-executor.md`.

### 4. Test-driven development

All production code must land with a failing test written first. We use the discipline from the superpowers TDD skill: write the test, watch it fail for the right reason, write minimal code to pass, verify green, refactor.

A PR with production code but no corresponding failing-first test will be asked to rewrite. Tests written after the fact give false confidence.

### 5. Honesty over success

Tools must fail loudly, not silently. If a feature is not yet wired, raise a clear error naming what's missing — don't return a pretend success value. The 2026-04-17 voice provider rewrite (`feat(voice): wire real OpenAI Whisper + loud-failure semantics`) is the canonical example.

## Setting up

```bash
git clone https://github.com/Henghenggao/Yigthinker.git
cd Yigthinker
pip install -e ".[dev,test]"
python -m pytest
```

Expected: **1179 passed / 1 skipped / 1 deselected** as of 2026-04-18. If your baseline differs, check `CHANGELOG.md` [Unreleased] for recent additions.

Run the independent MCP packages separately:

```bash
cd packages/yigthinker-mcp-uipath && python -m pytest
cd packages/yigthinker-mcp-powerautomate && python -m pytest
```

## PR checklist

- [ ] Tests exist and were written before the production code they cover
- [ ] `python -m pytest` passes in the root
- [ ] `python -m pytest` passes in both MCP package directories
- [ ] `python scripts/check_presence_boundaries.py` exits 0 (if you touched `yigthinker/presence/` or `yigthinker/core/`)
- [ ] `python scripts/check_adr_format.py docs/adr/` exits 0 (if you added an ADR)
- [ ] `python scripts/pypi_publish_helper.py check` exits 0 (if you touched pyproject.toml)
- [ ] `CHANGELOG.md` `[Unreleased]` section mentions the change
- [ ] Commit messages are detailed + end with `Co-Authored-By: ...` if AI-assisted

## Commit message style

Prefer small, atomic commits over one large "everything at once" commit. Example shapes from the recent history:

- `feat(voice): wire real OpenAI Whisper + loud-failure semantics`
- `fix(gateway): clear PermissionSystem overrides on session removal`
- `refactor(memory): drop misleading _locked suffix on self-locking reader`
- `docs(adr): index ADR-009 scheduled reports executor decision`
- `chore(pkg): complete PyPI metadata across all three packages`

First line under 72 chars. Body: why (not just what). If AI-assisted: `Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>` on the last line.

## What kinds of contributions are welcome

- Bug fixes (with a regression test)
- New tools that fit the flat-registry philosophy (no tool categorisation at runtime)
- New hook implementations for cross-cutting concerns
- New channel adapters (follow the `ChannelAdapter` Protocol in `yigthinker/core/presence.py`)
- Documentation improvements (README, examples, ADRs)
- Live tenant UAT reports for Phase 10/11/12 (see the runbooks under `docs/audit/`)
- Windows-specific fixes (Yigthinker runs on Windows; uvloop is unavailable there, `gateway.token` protection uses icacls)

## What we will likely reject

- Adding a web UI or dashboard (see policy 2)
- In-process schedulers or RPA runners (policy 3)
- Customer-specific branches (policy 1)
- Production code without tests written first (policy 4)
- Features that swallow errors silently (policy 5)
- Dependencies with non-OSI-approved licenses
- Dependencies that pin narrow version ranges without justification

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
