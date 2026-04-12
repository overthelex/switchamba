"""Tests for the language detector."""

from evdev import ecodes

from switchamba.detection.detector import LanguageDetector, Confidence
from switchamba.input.keymap import WORD_BOUNDARY_SCANCODES


class TestLanguageDetector:
    def setup_method(self):
        self.detector = LanguageDetector()

    def test_no_detection_mid_word(self):
        """Should return None while typing (no space yet)."""
        keys = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_E]
        for key in keys:
            result = self.detector.on_key(key)
            assert result is None

    def test_detection_on_space(self):
        """Should detect language when space is pressed."""
        # Type "there" then space
        self.detector.current_layout = "ru"  # Wrong layout
        keys = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_E]
        for key in keys:
            self.detector.on_key(key)
        result = self.detector.on_key(ecodes.KEY_SPACE)
        # Should detect EN
        if result is not None:
            assert result.language == "en"
            assert len(result.word_scancodes) == 5

    def test_short_word_ignored(self):
        """Single character words should not trigger detection."""
        self.detector.on_key(ecodes.KEY_A)
        result = self.detector.on_key(ecodes.KEY_SPACE)
        assert result is None

    def test_same_layout_no_detection(self):
        """Should return None if detected language matches current."""
        self.detector.current_layout = "en"
        keys = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_E]
        for key in keys:
            self.detector.on_key(key)
        result = self.detector.on_key(ecodes.KEY_SPACE)
        # "there" is EN, current is EN — no switch needed
        assert result is None

    def test_russian_detection(self):
        """Typing 'привет' scancodes should detect Russian."""
        self.detector.current_layout = "en"
        # привет = g-h-b-d-t-n
        keys = [ecodes.KEY_G, ecodes.KEY_H, ecodes.KEY_B,
                ecodes.KEY_D, ecodes.KEY_T, ecodes.KEY_N]
        for key in keys:
            self.detector.on_key(key)
        result = self.detector.on_key(ecodes.KEY_SPACE)
        if result is not None:
            assert result.language == "ru"
            assert len(result.word_scancodes) == 6

    # --- Backspace handling ---

    def test_backspace_removes_last_char(self):
        """Backspace should pop the last scancode from the buffer."""
        self.detector.current_layout = "ru"
        # Type "ther" then backspace then "re" → "there"
        for key in [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_R]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_BACKSPACE)
        for key in [ecodes.KEY_R, ecodes.KEY_E]:
            self.detector.on_key(key)
        result = self.detector.on_key(ecodes.KEY_SPACE)
        if result is not None:
            assert result.language == "en"
            assert len(result.word_scancodes) == 5

    def test_backspace_on_empty_buffer(self):
        """Backspace on empty buffer should not crash."""
        result = self.detector.on_key(ecodes.KEY_BACKSPACE)
        assert result is None
        # Buffer still works after
        for key in [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E]:
            self.detector.on_key(key)
        assert len(self.detector._word_scancodes) == 3

    def test_backspace_all_then_retype(self):
        """Backspacing entire word and retyping should work."""
        for key in [ecodes.KEY_A, ecodes.KEY_B]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_BACKSPACE)
        self.detector.on_key(ecodes.KEY_BACKSPACE)
        assert len(self.detector._word_scancodes) == 0
        # Retype
        for key in [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E]:
            self.detector.on_key(key)
        assert len(self.detector._word_scancodes) == 3

    def test_backspace_keeps_shift_in_sync(self):
        """Shift states should stay in sync with scancodes after backspace."""
        self.detector.on_key(ecodes.KEY_H, shifted=True)   # H
        self.detector.on_key(ecodes.KEY_E)                   # e
        self.detector.on_key(ecodes.KEY_L)                   # l
        self.detector.on_key(ecodes.KEY_BACKSPACE)           # remove l
        assert self.detector._word_scancodes == [ecodes.KEY_H, ecodes.KEY_E]
        assert self.detector._word_shifts == [True, False]

    # --- Arrow keys / navigation resets buffer ---

    def test_left_arrow_resets_buffer(self):
        """Left arrow means cursor moved — buffer should reset."""
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_LEFT)
        assert len(self.detector._word_scancodes) == 0

    def test_right_arrow_resets_buffer(self):
        for key in [ecodes.KEY_H, ecodes.KEY_E]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_RIGHT)
        assert len(self.detector._word_scancodes) == 0

    def test_up_arrow_resets_buffer(self):
        self.detector.on_key(ecodes.KEY_A)
        self.detector.on_key(ecodes.KEY_UP)
        assert len(self.detector._word_scancodes) == 0

    def test_down_arrow_resets_buffer(self):
        self.detector.on_key(ecodes.KEY_A)
        self.detector.on_key(ecodes.KEY_DOWN)
        assert len(self.detector._word_scancodes) == 0

    def test_home_resets_buffer(self):
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_HOME)
        assert len(self.detector._word_scancodes) == 0

    def test_end_resets_buffer(self):
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_END)
        assert len(self.detector._word_scancodes) == 0

    def test_delete_resets_buffer(self):
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_DELETE)
        assert len(self.detector._word_scancodes) == 0

    def test_nav_key_returns_none(self):
        """Navigation keys should return None, not a Detection."""
        self.detector.on_key(ecodes.KEY_A)
        result = self.detector.on_key(ecodes.KEY_LEFT)
        assert result is None

    # --- Ctrl resets buffer ---

    def test_ctrl_key_resets_buffer(self):
        """Any key with Ctrl held should reset the buffer."""
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L]:
            self.detector.on_key(key)
        # Ctrl+A (select all / home)
        self.detector.on_key(ecodes.KEY_A, ctrl=True)
        assert len(self.detector._word_scancodes) == 0

    def test_ctrl_v_resets_buffer(self):
        """Ctrl+V (paste) should reset — pasted text is invisible to us."""
        self.detector.on_key(ecodes.KEY_T)
        self.detector.on_key(ecodes.KEY_V, ctrl=True)
        assert len(self.detector._word_scancodes) == 0

    def test_ctrl_backspace_resets_buffer(self):
        """Ctrl+Backspace (delete word) should reset entire buffer."""
        for key in [ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_L, ecodes.KEY_L, ecodes.KEY_O]:
            self.detector.on_key(key)
        self.detector.on_key(ecodes.KEY_BACKSPACE, ctrl=True)
        assert len(self.detector._word_scancodes) == 0

    def test_ctrl_returns_none(self):
        """Ctrl combos should return None."""
        self.detector.on_key(ecodes.KEY_A)
        result = self.detector.on_key(ecodes.KEY_C, ctrl=True)
        assert result is None

    # --- Typing resumes after reset ---

    def test_typing_after_arrow_reset(self):
        """Buffer should accumulate normally after a nav-key reset."""
        self.detector.on_key(ecodes.KEY_X)
        self.detector.on_key(ecodes.KEY_LEFT)
        assert len(self.detector._word_scancodes) == 0
        # Type fresh word
        for key in [ecodes.KEY_H, ecodes.KEY_I]:
            self.detector.on_key(key)
        assert len(self.detector._word_scancodes) == 2

    def test_typing_after_ctrl_reset(self):
        """Buffer should accumulate normally after a Ctrl reset."""
        self.detector.on_key(ecodes.KEY_X)
        self.detector.on_key(ecodes.KEY_A, ctrl=True)
        assert len(self.detector._word_scancodes) == 0
        for key in [ecodes.KEY_O, ecodes.KEY_K]:
            self.detector.on_key(key)
        assert len(self.detector._word_scancodes) == 2
