# ADR-002: Intent-first 路由

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
IM 通道（Teams / Feishu）上大量用户请求是纯对话式——"这是什么意思"、"帮我解释一下"，不需要工具调用。全部请求都进入完整 LLM+tool 循环会带来可感知延迟与多余 token 开销。

## Decision
在 agent loop 入口加一层 intent classifier，用轻量 LLM 把请求归类为 `direct_reply` / `tool_call` / `clarification_needed`。`direct_reply` 分支跳过 tool registry 直接出文本，其余走完整 loop。classifier 使用 fast-and-cheap provider（Haiku、GPT-4o-mini），可配置；超时或错误时默认回落到完整 loop，不阻断。

## Consequences
- Phase 1a 先落 MemoryProvider 与 dry-run，classifier 属 Phase 1b/3 工作。
- 定义性问题的 H4 回归测试在 Phase 1a 写好，为此分支兜底。
- IM 通道响应中位数预计下降；完整 loop 仍是默认兜底路径。

## References
- Yigcore ADR-016（历史输入）
- Yigthinker spec §5.1 harness P1-3
- docs/adr/001-why-we-dont-do-pgec.md
