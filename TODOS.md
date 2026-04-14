# TODOS

Actionable items still worth carrying forward after the 2026-04-13 cleanup.

## Archived

- Eng review fixes from 2026-04-07 were completed in the referenced quick tasks.
- Dashboard-specific design and architecture TODOs were archived on 2026-04-13 because Yigthinker is now a headless product.

## Remaining

### Live tenant UAT for RPA milestone
What: Run real-environment checks for Phase 10 callback flow plus UiPath and Power Automate round-trips.
Why: Automated coverage is green, but live credentials and tenant behavior still need final validation.

### PyPI publication cutover
What: Publish the core package and MCP packages, then switch installer/docs from GitHub-source installs back to PyPI commands.
Why: Current installation UX is correct but intentionally temporary while packages are unpublished.

### Permission override cleanup on session eviction
What: Ensure session eviction clears `PermissionSystem` per-session overrides.
Why: Long-running gateways can otherwise accumulate stale override state.

### Durable scheduled reports
What: Persist `report_schedule` entries outside in-memory session settings and attach a real executor path.
Why: The current command returns success for work that does not survive restarts.

### Voice provider implementation
What: Replace the current Whisper stub with a real transcription path or fail loudly when voice is enabled.
Why: Silent failure is worse than an explicit unsupported message.
