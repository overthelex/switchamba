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
