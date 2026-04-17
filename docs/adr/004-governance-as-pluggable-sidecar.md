# ADR-004: 治理作为可插拔 sidecar

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore 把 Sentinel 作为内嵌治理内核，RBAC、Quota、PII、Audit 全部硬编码进主路径。Yigthinker 遵循薄内核 + 外挂哲学（spec §3.1、§3.2），必须决定治理如何安放。

## Decision
不内嵌 Sentinel。治理以两种形态可选接入：(1) 基础策略——allow/ask/deny 路由——作为 PreToolUse hook 提供；(2) 企业级能力——RBAC、Quota、PII 扫描、durable audit——作为独立的 Sentinel MCP sidecar 服务，可选挂载。保留 Yigcore 四层模型（Declaration / Gate / Monitor / Audit）作为**概念地图**，不作为代码结构。

## Consequences
- 核心包对治理零依赖，`pip install yigthinker` 可用。
- Sentinel sidecar 是 YCE 企业版交付物，不进 MVP。
- Phase 0 permission 路由与 audit JSONL 保持不变。
- 任何 governance 代码不得出现在 `yigthinker/agent.py` 或 `yigthinker/core/`。

## References
- Yigcore ADR-001（历史输入）
- Yigthinker spec §3.1、§3.2
