---
phase: 07-spawn-agent
plan: 04
subsystem: subagent-lifecycle
tags: [spawn-agent, foreground, background, transcript, notification, builder]
dependency_graph:
  requires: [07-01, 07-02, 07-03]
  provides: [spawn_agent_execution, subagent_transcript, notification_injection, builder_wiring]
  affects: [agent_loop, settings, builder]
tech_stack:
  added: []
  patterns: [asyncio.create_task, notification_drain, dependency_injection]
key_files:
  created:
    - yigthinker/subagent/transcript.py
    - tests/test_subagent/test_lifecycle.py
    - tests/test_subagent/test_transcript.py
  modified:
    - yigthinker/tools/spawn_agent.py
    - yigthinker/agent.py
    - yigthinker/settings.py
    - yigthinker/builder.py
    - yigthinker/subagent/__init__.py
    - tests/test_tools/test_registry_factory.py
    - tests/test_tools/test_registry_factory_phase3.py
    - tests/test_tools/test_spawn_agent.py
decisions:
  - "SubagentStop hook return value intentionally ignored per D-13 (notification-only event)"
  - "Background task reference stored on SubagentInfo.task for cancel support"
  - "Transcript writer creates directories lazily via TranscriptWriter constructor"
  - "Subagent notifications injected as system prompt addendum in AgentLoop.run()"
metrics:
  duration: 5min
  completed: "2026-04-08T10:38:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 11
  test_count: 10
requirements_completed: [SPAWN-10, SPAWN-11, SPAWN-12, SPAWN-17]
---

# Phase 07 Plan 04: Spawn Agent Lifecycle Wiring Summary

Complete spawn_agent foreground/background execution with DataFrame sharing, concurrency limiting, transcript persistence, and SubagentStop hook firing -- all wired through builder.py dependency injection.

## Commits

| # | Hash | Type | Description |
|---|------|------|-------------|
| 1 | ba6be7c | feat | Complete spawn_agent execution with foreground/background modes |
| 2 | 102d0be | test | Add lifecycle and transcript tests for spawn_agent |

## What Was Built

### Task 1: Complete spawn_agent execution flow

**SpawnAgentTool** (`yigthinker/tools/spawn_agent.py`) was rewritten from a stub into a fully functional tool with:

- **Foreground mode (SPAWN-10):** `execute()` awaits `child_loop.run()` inline and returns the final text as `tool_result.content`. DataFrames are merged back with `{agent_name}_` prefix.
- **Background mode (SPAWN-11):** `execute()` launches `_run_background()` via `asyncio.create_task()` and returns immediately with the `subagent_id`. Background completion triggers `manager.add_notification()` for parent LLM injection.
- **Concurrency limit (SPAWN-12):** `can_spawn()` check before spawning; returns clear error with the limit value.
- **SubagentStop hook (D-13, D-14):** Fires on both completion and failure with `subagent_final_text` truncated to 500 chars. Return value intentionally ignored (notification-only event per D-13).
- **Failure handling (D-09):** Foreground failures return `ToolResult(is_error=True)` with error details. Background failures add failure notification.
- **set_parent_components():** Dependency injection method for tools, hooks, permissions, and provider.

**SubagentTranscriptWriter** (`yigthinker/subagent/transcript.py`): Creates a `TranscriptWriter` at `~/.yigthinker/sessions/subagents/{session_id}/{subagent_id}.jsonl` (SPAWN-17).

**AgentLoop notification injection** (`yigthinker/agent.py`): Before each LLM call, drains pending subagent notifications and appends them as `[Subagent Notifications]` section in the system prompt (D-08).

**Settings defaults** (`yigthinker/settings.py`): Added `spawn_agent.max_concurrent=3`, `spawn_agent.max_iterations=20`, `spawn_agent.timeout=120.0`.

**Builder wiring** (`yigthinker/builder.py`): After `AgentLoop` construction, calls `spawn_tool.set_parent_components(tools, hooks, permissions, provider)` with `hasattr` guard.

### Task 2: Lifecycle and transcript test suite

10 new tests covering:
- `test_foreground_mode`: Verifies foreground await and completed status
- `test_background_mode`: Verifies immediate return, task creation, and notification after completion
- `test_concurrent_limit`: Verifies error when at max_concurrent
- `test_subagent_stop_hook`: Verifies SubagentStop fires with correct subagent_final_text (D-14)
- `test_subagent_stop_block_ignored`: Verifies BLOCK result ignored for SubagentStop (D-13)
- `test_foreground_failure`: Verifies is_error=True and failed status
- `test_background_notification`: Verifies add_notification called on background completion (D-08)
- `test_not_initialized`: Verifies error when parent components missing
- `test_transcript_path`: Verifies correct path construction
- `test_transcript_write`: Verifies valid JSONL output

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated registry factory test counts**
- **Found during:** Task 2 verification
- **Issue:** `test_registry_factory.py` and `test_registry_factory_phase3.py` hardcoded tool count as 21, but Wave 1/2 added agent_status and agent_cancel (23 total)
- **Fix:** Updated assertions from 21 to 23 with explanatory comment
- **Files modified:** `tests/test_tools/test_registry_factory.py`, `tests/test_tools/test_registry_factory_phase3.py`

**2. [Rule 3 - Blocking] Updated test_spawn_agent.py for new behavior**
- **Found during:** Task 2 verification
- **Issue:** Old test expected "not yet implemented" stub response, but spawn_agent now returns "not fully initialized" when parent components aren't set
- **Fix:** Updated test expectations to match new behavior
- **Files modified:** `tests/test_tools/test_spawn_agent.py`

## Verification

- `python -m pytest tests/test_subagent/ -x -v`: 43 passed
- `python -m pytest tests/ -x --ignore=tests/test_dashboard --ignore=tests/test_gateway/test_dedup.py`: 424 passed, 3 skipped
- `python -c "from yigthinker.tools.spawn_agent import SpawnAgentTool; t = SpawnAgentTool(); print(t.name)"`: prints "spawn_agent"
- `python -c "from yigthinker.subagent.transcript import create_subagent_transcript_writer"`: exits 0

## Self-Check: PASSED

All 7 key files verified present. Both commits (ba6be7c, 102d0be) confirmed in git log.
