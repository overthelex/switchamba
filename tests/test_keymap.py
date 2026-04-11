"""Tests for scancode-to-character mapping."""

from evdev import ecodes

from switchamba.input.keymap import (
    scancode_to_char,
    scancodes_to_text,
    EN, RU, UA,
    RU_EXCLUSIVE_SCANCODES,
)


class TestScancodeToChar:
    def test_english_letters(self):
        assert scancode_to_char(ecodes.KEY_Q, EN) == "q"
        assert scancode_to_char(ecodes.KEY_Q, EN, shifted=True) == "Q"
        assert scancode_to_char(ecodes.KEY_A, EN) == "a"
        assert scancode_to_char(ecodes.KEY_Z, EN) == "z"

    def test_russian_letters(self):
        assert scancode_to_char(ecodes.KEY_Q, RU) == "й"
        assert scancode_to_char(ecodes.KEY_Q, RU, shifted=True) == "Й"
        assert scancode_to_char(ecodes.KEY_A, RU) == "ф"
        assert scancode_to_char(ecodes.KEY_F, RU) == "а"

    def test_ukrainian_letters(self):
        assert scancode_to_char(ecodes.KEY_Q, UA) == "й"
        assert scancode_to_char(ecodes.KEY_A, UA) == "ф"

    def test_ru_ua_discriminators(self):
        # KEY_S: ы (RU) vs і (UA)
        assert scancode_to_char(ecodes.KEY_S, RU) == "ы"
        assert scancode_to_char(ecodes.KEY_S, UA) == "і"

        # KEY_APOSTROPHE: э (RU) vs є (UA)
        assert scancode_to_char(ecodes.KEY_APOSTROPHE, RU) == "э"
        assert scancode_to_char(ecodes.KEY_APOSTROPHE, UA) == "є"

        # KEY_RIGHTBRACE: ъ (RU) vs ї (UA)
        assert scancode_to_char(ecodes.KEY_RIGHTBRACE, RU) == "ъ"
        assert scancode_to_char(ecodes.KEY_RIGHTBRACE, UA) == "ї"

    def test_unknown_scancode(self):
        assert scancode_to_char(999, EN) is None

    def test_scancodes_to_text(self):
        # "the" in English scancodes
        scancodes = [ecodes.KEY_T, ecodes.KEY_H, ecodes.KEY_E]
        assert scancodes_to_text(scancodes, EN) == "the"
        # Same scancodes in Russian: T=е, H=р, E=у → "еру"
        assert scancodes_to_text(scancodes, RU) == "еру"

    def test_exclusive_scancodes_present(self):
        assert ecodes.KEY_S in RU_EXCLUSIVE_SCANCODES
        assert ecodes.KEY_APOSTROPHE in RU_EXCLUSIVE_SCANCODES
        assert ecodes.KEY_RIGHTBRACE in RU_EXCLUSIVE_SCANCODES
