# ADR-001: 不采用 PGEC 显式阶段

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore 早期把 agent cognition 拆成 Plan / Generate / Evaluate / Compose 四个显式阶段（PGEC）。ADR-038 已正式废弃此路线，回归 LLM-native ReAct 循环。Yigthinker 作为继承者须决定是否复制该结构。

## Decision
Yigthinker 只保留一条 LLM-native agent loop，不把 Plan/Compose 作为运行期阶段。`exit_plan_mode` 工具作为 opt-in 用户命令存在，不是默认路径。反思以 tool-error 恢复的形式嵌入主循环，不抽成独立阶段。

## Consequences
- `agent.py` 只有单一主循环，控制流可审计。
- 任何"加 Planner"提议须通过新 ADR 驳回或替代本决策。
- Dry-run 模式（Phase 1b）承担"预览计划"的用户需求。
- Reflexion 作为 ArgPatch hook 存在，不新增阶段边界。

## References
- Yigcore ADR-038、ADR-008（历史输入）
- Yigthinker spec §5.1
