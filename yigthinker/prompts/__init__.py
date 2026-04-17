"""Prompt library for Yigthinker.

This module owns all base system prompts used by the agent loop.
Keep all LLM-facing prompt text centralized here so doc-code alignment
(§9.1 of the design spec) has a single source of truth.
"""
from yigthinker.prompts.base import BASE_SYSTEM_PROMPT

__all__ = ["BASE_SYSTEM_PROMPT"]
