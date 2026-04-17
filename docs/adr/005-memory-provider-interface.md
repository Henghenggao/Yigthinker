# ADR-005: MemoryProvider 接口

Status: Accepted  |  Date: 2026-04-17  |  Supersedes: —
Lang: zh

## Context
Yigcore 宣称三层 memory（Working/LTM/Core）+ pgvector，但 spec §8 审计显示 LTM V2 embedding 是 stub，三层模型被过度销售。Yigthinker 需要诚实、可测、零依赖起点的记忆抽象。

## Decision
引入 `MemoryProvider` Protocol 作为 agent 私有记忆的唯一接口，与企业 RAG `RetrievalProvider` 严格切分（spec §4.5.2 一票否决）。默认 `FileMemoryProvider`：JSONL 追加、filelock 并发、零新增依赖。语义检索**不**进入默认 Protocol；vector 后端作为 `SemanticMemoryProvider` 子协议，Phase 3+ opt-in。

## Consequences
- `pip install yigthinker` 即刻具备私有记忆能力。
- LTM V1 schema 以 SQLAlchemy 形态 port 但 dormant。
- 现有 `yigthinker/memory/*.py` 暂不迁入本 Protocol。
- pgvector 完全排除于核心 `extras_require`。

## References
- Yigcore LTM V1 schema、V2 审计
- Yigthinker spec §4.2、§4.5.2、§9.6
