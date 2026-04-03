"""Unit tests for GatewayWSClient."""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, patch


class TestGatewayWSClient:
    def test_initial_state(self):
        """Client starts in disconnected state."""
        from yigthinker.tui.ws_client import GatewayWSClient

        client = GatewayWSClient(url="ws://localhost:8766/ws", token="test")
        assert client.state == "disconnected"

    def test_state_change_callback(self):
        """State changes trigger the on_state_change callback."""
        from yigthinker.tui.ws_client import GatewayWSClient

        states: list[str] = []
        client = GatewayWSClient(
            url="ws://localhost:8766/ws",
            token="test",
            on_state_change=lambda s: states.append(s),
        )
        client._set_state("connecting")
        client._set_state("connected")
        assert states == ["connecting", "connected"]

    # TUI-04: Reconnection with exponential backoff (1s base, 30s max)
    @pytest.mark.asyncio
    async def test_reconnect_backoff_timing(self):
        """Verify backoff doubles from 1s base up to 30s max on connection failures."""
        from yigthinker.tui.ws_client import GatewayWSClient

        states: list[str] = []
        sleep_calls: list[float] = []

        client = GatewayWSClient(
            url="ws://localhost:1/ws",  # Will fail immediately
            token="test",
            on_state_change=lambda s: states.append(s),
        )

        original_sleep = asyncio.sleep
        call_count = 0

        async def mock_sleep(delay):
            nonlocal call_count
            sleep_calls.append(delay)
            call_count += 1
            if call_count >= 4:
                raise asyncio.CancelledError()  # Stop after 4 retries
            # Yield control briefly
            await original_sleep(0.01)

        with patch("yigthinker.tui.ws_client.asyncio.sleep", side_effect=mock_sleep):
            with patch(
                "websockets.connect",
                side_effect=ConnectionRefusedError("refused"),
            ):
                try:
                    await client.connect_loop()
                except asyncio.CancelledError:
                    pass

        # Verify exponential backoff: 1.0, 2.0, 4.0 (doubles each time)
        assert len(sleep_calls) >= 3, f"Expected at least 3 sleep calls, got {sleep_calls}"
        assert sleep_calls[0] == 1.0, f"First delay should be 1.0, got {sleep_calls[0]}"
        assert sleep_calls[1] == 2.0, f"Second delay should be 2.0, got {sleep_calls[1]}"
        assert sleep_calls[2] == 4.0, f"Third delay should be 4.0, got {sleep_calls[2]}"

        # Verify state transitions include reconnecting
        assert "connecting" in states
        assert "reconnecting" in states
