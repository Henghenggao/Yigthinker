---
quick_id: 260414-peo
description: "Task 4.2: public yigthinker.sdk module — query(), create_session(), resume_session()"
date: 2026-04-14
branch: feat/p0-arch-gaps-260414
---

# Quick Task 260414-peo: Public yigthinker.sdk API

## Goal

Expose the public `yigthinker.sdk` module surface with three async functions:
- `query()` — single-shot prompt, returns str
- `create_session()` — returns new `SDKSession`
- `resume_session()` — returns `SDKSession` with given session_id

`SDKSession` was created in Task 4.1 at `yigthinker/sdk/session.py`.

## Tasks

### Task 1: Write failing tests
- **File:** `tests/test_sdk/test_query.py`
- **Action:** Create 3 tests covering `query()`, `create_session()` return type, and settings merge
- **Verify:** `pytest tests/test_sdk/test_query.py -v` → 3 FAILED (ImportError or AttributeError)
- **Done:** Tests exist and fail before implementation

### Task 2: Implement `yigthinker/sdk/__init__.py`
- **File:** `yigthinker/sdk/__init__.py`
- **Action:** Write `query()`, `create_session()`, `resume_session()` using `build_app`, `load_settings`, `SessionContext`, `SDKSession`
- **Verify:** `pytest tests/test_sdk/ -v` → 7 passed (3 new + 4 existing)
- **Done:** All tests green, `__all__` exports all 4 symbols

### Task 3: Commit
- **Action:** `git add yigthinker/sdk/__init__.py tests/test_sdk/test_query.py && git commit`
- **Done:** Commit on `feat/p0-arch-gaps-260414`
