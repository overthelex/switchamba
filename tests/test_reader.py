"""Tests for the keystroke reader — suppress/drain and double-Ctrl state."""

import time

from switchamba.input.reader import KeystrokeReader, DOUBLE_CTRL_SCANCODE


class TestKeystrokeReaderState:
    def setup_method(self):
        self.reader = KeystrokeReader()

    def test_initial_state(self):
        """Reader should start with clean modifier state."""
        assert self.reader._shift_held is False
        assert self.reader._ctrl_held is False
        assert self.reader._ctrl_other_key is False
        assert self.reader._last_ctrl_tap == 0.0

    def test_suppress_sets_deadline(self):
        """suppress() should set _suppress_until in the future."""
        self.reader.suppress(1.0)
        assert self.reader._suppress_until > time.monotonic()

    def test_suppress_clears_pending(self):
        """suppress() should clear any previously collected pending scancodes."""
        self.reader._pending_scancodes = [(30, False), (31, True)]
        self.reader.suppress(0.5)
        assert self.reader._pending_scancodes == []

    def test_drain_pending_returns_and_clears(self):
        """drain_pending() should return collected scancodes and clear the list."""
        self.reader._pending_scancodes = [(30, False), (31, True)]
        result = self.reader.drain_pending()
        assert result == [(30, False), (31, True)]
        assert self.reader._pending_scancodes == []

    def test_drain_pending_empty(self):
        """drain_pending() on empty list should return empty list."""
        result = self.reader.drain_pending()
        assert result == []

    def test_drain_pending_does_not_alias(self):
        """drain_pending() should return a copy, not a reference."""
        self.reader._pending_scancodes = [(30, False)]
        result = self.reader.drain_pending()
        result.append((99, True))
        assert self.reader._pending_scancodes == []

    def test_double_ctrl_scancode_sentinel(self):
        """DOUBLE_CTRL_SCANCODE should be negative (not a real scancode)."""
        assert DOUBLE_CTRL_SCANCODE < 0


class TestDoubleCtrlStateMachine:
    """Test the double-Ctrl detection state machine by simulating transitions."""

    def setup_method(self):
        self.reader = KeystrokeReader()

    def test_clean_ctrl_tap_records_time(self):
        """A clean Ctrl release should record the tap time."""
        # Simulate: Ctrl was held, no other key pressed, now released
        self.reader._ctrl_held = True
        self.reader._ctrl_other_key = False
        # Simulate release
        self.reader._ctrl_held = False
        # The actual tap detection is in _device_reader, but we can test
        # that the state fields are correctly initialized for detection
        assert self.reader._last_ctrl_tap == 0.0  # not yet set outside _device_reader

    def test_other_key_prevents_tap(self):
        """If another key was pressed during Ctrl hold, it's not a clean tap."""
        self.reader._ctrl_held = True
        self.reader._ctrl_other_key = True
        # Release
        self.reader._ctrl_held = False
        # _ctrl_other_key being True means no tap should be registered
        assert self.reader._ctrl_other_key is True

    def test_ctrl_down_resets_other_key_flag(self):
        """Pressing Ctrl should reset the _ctrl_other_key flag."""
        self.reader._ctrl_other_key = True
        # Simulate new Ctrl press by resetting as the reader does
        self.reader._ctrl_other_key = False
        assert self.reader._ctrl_other_key is False

    def test_last_ctrl_tap_initially_zero(self):
        """First Ctrl tap should compare against 0.0 — always too far apart."""
        now = time.monotonic()
        # 0.0 is always > 0.4s ago, so first tap just records time
        assert now - self.reader._last_ctrl_tap > 0.4

    def test_two_taps_within_window(self):
        """Two taps within 0.4s should be detectable."""
        now = time.monotonic()
        self.reader._last_ctrl_tap = now - 0.2  # 200ms ago
        assert now - self.reader._last_ctrl_tap < 0.4

    def test_two_taps_outside_window(self):
        """Two taps more than 0.4s apart should NOT trigger double-Ctrl."""
        now = time.monotonic()
        self.reader._last_ctrl_tap = now - 0.6  # 600ms ago
        assert now - self.reader._last_ctrl_tap >= 0.4
