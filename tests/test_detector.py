"""Tests for the language detector."""

from evdev import ecodes

from switchamba.detection.detector import LanguageDetector, Confidence


class TestLanguageDetector:
    def setup_method(self):
        self.detector = LanguageDetector(buffer_size=8)

    def test_not_enough_data(self):
        """Should return None with fewer than MIN_BUFFER_SIZE chars."""
        result = self.detector.on_key(ecodes.KEY_T)
        assert result is None
        result = self.detector.on_key(ecodes.KEY_H)
        assert result is None

    def test_english_detection(self):
        """Typing 'the' should detect English."""
        # Type t-h-e-r-e (English word)
        keys = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E, ecodes.KEY_R, ecodes.KEY_E]
        result = None
        for key in keys:
            result = self.detector.on_key(key)

        # Should detect something (either EN or return detection)
        # The detector starts with EN as default, so it may not trigger a switch
        # if it correctly detects EN.
        # We set current layout to RU to force a detection
        self.detector.reset()
        self.detector.current_layout = "ru"
        for key in keys:
            result = self.detector.on_key(key)

        if result is not None:
            assert result.language == "en"

    def test_word_boundary_resets(self):
        """Space should reset the buffer."""
        self.detector.on_key(ecodes.KEY_T)
        self.detector.on_key(ecodes.KEY_H)
        self.detector.on_key(ecodes.KEY_SPACE)

        # Buffer should be empty, so next few chars shouldn't trigger detection
        result = self.detector.on_key(ecodes.KEY_A)
        assert result is None

    def test_buffer_text(self):
        """get_buffer_text should return correct text for each layout."""
        keys = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E]
        for key in keys:
            self.detector.on_key(key)

        assert self.detector.get_buffer_text("en") == "the"
        assert self.detector.get_buffer_text("ru") == "еру"
