"""Core abstractions shared across presences and subsystems (Phase 1b).

This package hosts Protocols and types that are intentionally presence-agnostic —
e.g. the ChannelAdapter Protocol, which channel-type presences (Teams, Feishu,
Google Chat) implement but CLI/TUI/Gateway do not.
"""
