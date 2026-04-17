# ADR-008: Persona 作为数据

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore 积累 25+ 张 PersonaCard（CFO analyst、Excel analyst 等），每张是 JSON，含 role、skills、prompt、constraints。若代码依赖 persona 分支，会滑向 persona-specific 的工具路由与行为切换，侵蚀 flat tool registry 的核心假设。

## Decision
Persona 永远是**数据**，不是代码分支。JSON cards 放 `yigthinker/presets/personas/*.json`，由用户或 channel 在运行期显式选定，作为 system_prompt 片段注入。Yigthinker 不基于 persona 做 tool gating 或 behavior switching。

## Consequences
- 新增 persona = 新增 JSON，零代码改动。
- tool registry 保持 flat 30 tools。
- Phase 1a 把 25 张 persona + 3 张 team card 迁入 `presets/`。
- loader 工具推迟到 Phase 3。

## References
- Yigcore PersonaCard 收敛 spec（历史输入）
- Yigthinker spec §6.2 A 类
- `yigthinker/presets/personas/`
