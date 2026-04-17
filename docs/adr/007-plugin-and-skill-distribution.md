# ADR-007: 插件与 Skill 分发

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore ADR-014/015 把 skill 生态抽到独立的 YigYaps 仓作为分发中心。Yigthinker 继承"可分发"的理念，但不希望 YigYaps 成为唯一市场，更不希望核心感知具体渠道。

## Decision
"可分发"是第一原则，分发渠道**不绑定** YigYaps。支持三种形态：(1) 本地 Python 包 + entry point，作为 plugin；(2) MCP server，作为 skill；(3) `.skill` marketplace 格式，兼容 Anthropic Skills 规范。Yigthinker 核心不感知分发渠道，`PluginLoader` 只负责从已配置位置加载。

## Consequences
- YigYaps 可作为未来一种 Yigcore plugin 注册，但非前置依赖。
- Claude Agent SDK Skills 兼容层在 Phase 3 引入。
- 核心仓不内置 skill marketplace UI。
- 新增分发渠道不会污染 `PluginLoader` 接口。

## References
- Yigcore ADR-014、ADR-015（历史输入）
- Claude Agent SDK Skills 规范
- Yigthinker spec §3.2
