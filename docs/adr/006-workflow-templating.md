# ADR-006: 工作流模板系统

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore ADR-037 引入 HIL Draft pipeline 与 Compiled Path 作为可重放工作流单元，但二者紧耦合，大量 feature 长期卡在 HIL review。Yigthinker 已有 `workflow_generate` 工具，须决定是否复制该耦合。

## Decision
合并 Compiled Path 与 `workflow_generate`，统一为基于 Jinja2 `SandboxedEnvironment` + AST 校验的单一模板系统。HIL 退化为**按工具 opt-in** 的 settings flag，不作为架构级约束。workflow 脚本自包含，可在无 Yigthinker 环境下独立运行，凭 `vault://` 引用获取凭据。

## Consequences
- `workflow_generate` 产出的脚本可端到端运行，不会被审核门卡死。
- 需要 HIL 的工具（如 DML SQL）在注册时声明 `requires_approval: true`。
- Phase 3 的 Compiled Path replay 基于此基础重建，不重复 Yigcore Draft 耦合。
- 模板保持两层 SSTI 防御。

## References
- Yigcore ADR-037（历史输入）
- Yigthinker spec §2、§10
- `yigthinker/tools/workflow/`
