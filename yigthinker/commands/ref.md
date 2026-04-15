---
description: Reference specific earlier turns for context emphasis
argument-hint: <turn_numbers> <instruction>
allowed-tools: []
---

Reference specific earlier conversation turns to emphasize context when
responding to your instruction.

**Usage:** `/ref 3,5 compare these two results`

The referenced turns (by 1-based history index) are highlighted in the
agent's next system prompt so it focuses on those exchanges when acting
on the instruction that follows.
