"""Tests for _handle_line_correction (double-Ctrl flow)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import switchamba.__main__ as main_module
from switchamba.__main__ import _handle_line_correction


class FakeReader:
    def __init__(self):
        self.suppress_calls = []
        self.drain_called = False

    def suppress(self, duration):
        self.suppress_calls.append(duration)

    def drain_pending(self):
        self.drain_called = True
        return []


class FakeDetector:
    def __init__(self):
        self.reset_called = False

    def reset(self):
        self.reset_called = True


class TestHandleLineCorrection:
    def setup_method(self):
        self.reader = FakeReader()
        self.detector = FakeDetector()
        self.switcher = AsyncMock()

    @pytest.mark.asyncio
    async def test_no_bedrock_client(self):
        """Should return early if Bedrock is not configured."""
        with patch.object(main_module, "_bedrock_client", None):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        # Should not call any switcher methods
        self.switcher.select_to_line_start.assert_not_called()

    @pytest.mark.asyncio
    async def test_suppresses_reader(self):
        """Should suppress reader at start and reset at end."""
        with patch.object(main_module, "_bedrock_client", None):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        # Even with no bedrock, early return doesn't suppress
        # Test with bedrock configured
        self.reader = FakeReader()
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value=None)
        self.switcher.read_clipboard = AsyncMock(return_value="hello")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        assert self.reader.suppress_calls[0] == 15.0  # initial suppress
        assert self.reader.suppress_calls[-1] == 0.3  # final suppress
        assert self.reader.drain_called

    @pytest.mark.asyncio
    async def test_resets_detector(self):
        """Should reset detector buffer on double-Ctrl."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value=None)
        self.switcher.read_clipboard = AsyncMock(return_value="text")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        assert self.detector.reset_called

    @pytest.mark.asyncio
    async def test_selects_and_copies(self):
        """Should send Shift+Home then Ctrl+C."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value=None)
        self.switcher.read_clipboard = AsyncMock(return_value="hello world")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.select_to_line_start.assert_called_once()
        self.switcher.copy_selection.assert_called_once()
        self.switcher.read_clipboard.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_clipboard_cancels(self):
        """Should cancel selection if clipboard is empty."""
        mock_bedrock = AsyncMock()
        self.switcher.read_clipboard = AsyncMock(return_value="")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.cancel_selection.assert_called_once()
        mock_bedrock.correct_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_none_clipboard_cancels(self):
        """Should cancel selection if clipboard returns None."""
        mock_bedrock = AsyncMock()
        self.switcher.read_clipboard = AsyncMock(return_value=None)
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.cancel_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_whitespace_only_clipboard_cancels(self):
        """Should cancel selection if clipboard has only whitespace."""
        mock_bedrock = AsyncMock()
        self.switcher.read_clipboard = AsyncMock(return_value="   \n  ")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.cancel_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_correction_applied(self):
        """Should paste corrected text when Bedrock returns a different string."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value="hello world")
        self.switcher.read_clipboard = AsyncMock(return_value="helo wrold")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        mock_bedrock.correct_text.assert_called_once_with("helo wrold")
        self.switcher.write_clipboard_and_paste.assert_called_once_with("hello world")
        self.switcher.cancel_selection.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_correction_needed(self):
        """Should cancel selection if Bedrock returns same text."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value="hello world")
        self.switcher.read_clipboard = AsyncMock(return_value="hello world")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.write_clipboard_and_paste.assert_not_called()
        self.switcher.cancel_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_bedrock_returns_none(self):
        """Should cancel selection if Bedrock returns None (timeout/error)."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value=None)
        self.switcher.read_clipboard = AsyncMock(return_value="some text")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.write_clipboard_and_paste.assert_not_called()
        self.switcher.cancel_selection.assert_called_once()

    @pytest.mark.asyncio
    async def test_exception_cancels_selection(self):
        """Should cancel selection and not crash on unexpected errors."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(side_effect=RuntimeError("boom"))
        self.switcher.read_clipboard = AsyncMock(return_value="text")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        self.switcher.cancel_selection.assert_called()

    @pytest.mark.asyncio
    async def test_drains_pending_after_correction(self):
        """Should drain pending scancodes after the operation."""
        mock_bedrock = AsyncMock()
        mock_bedrock.correct_text = AsyncMock(return_value="fixed")
        self.switcher.read_clipboard = AsyncMock(return_value="broken")
        with patch.object(main_module, "_bedrock_client", mock_bedrock):
            await _handle_line_correction(self.reader, self.switcher, self.detector)
        assert self.reader.drain_called
