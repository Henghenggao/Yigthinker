# ADR-003: Harness 工程哲学

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore ADR-036 识别 agent harness 是独立工程学科——hook 生命周期、idle watchdog、token continuation、reflexion、dry-run——与 LLM 能力和领域能力正交。Yigthinker 需要稳定可测的 harness 形状，避免重复发明。

## Decision
采纳 Claude Agent SDK 风格的 hook 生命周期作为形状：PreToolUse、PostToolUse、Stop、SessionStart、SessionEnd、PreCompact、SubagentStop、UserPromptSubmit。Phase 1b 补齐 4 个 P1 能力：idle watchdog、token continuation、ArgPatch reflexion、dry-run。**形状对齐 SDK，代码独立，不依赖 SDK**。

## Consequences
- 每个 hook event 有独立测试，harness 即工程纪律。
- 新增 event 的 PR 须同步改 CLAUDE.md 列表、实现与测试。
- harness 代码与 agent.py 合并计入 spec §9.5 的 3000 LOC 硬上限。

## References
- Yigcore ADR-036（历史输入）
- Claude Agent SDK 文档
- Yigthinker spec §5
