"""Language detector with word-boundary correction.

Collects scancodes during word typing. On space/enter, analyzes the
complete word and returns a correction if it was typed in the wrong layout.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

from evdev import ecodes

from ..input.keymap import (
    EN, RU, UA, LAYOUTS,
    ALPHA_SCANCODES, DIGIT_SCANCODES, WORD_BOUNDARY_SCANCODES, EDIT_SCANCODES,
    RU_EXCLUSIVE_SCANCODES, KEYMAP,
    scancodes_to_text,
)
from .ngram import score_all_languages
from .dictionary import DictionaryMatcher

logger = logging.getLogger(__name__)


class Confidence(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3


@dataclass
class Detection:
    language: str
    confidence: Confidence
    scores: dict[str, float] = field(default_factory=dict)
    reason: str = ""
    # Full word scancodes for correction
    word_scancodes: list[int] = field(default_factory=list)
    word_shifts: list[bool] = field(default_factory=list)


# Minimum word length to attempt detection
MIN_WORD_LENGTH = 2

# Score difference threshold
SCORE_THRESHOLD = 0.3

# Inertia: current layout must be beaten by this margin
INERTIA_MARGIN = 0.4

# Weight factors
NGRAM_WEIGHT = 0.7
DICT_WEIGHT = 0.3


class LanguageDetector:
    """Detects language at word boundaries (space/enter)."""

    def __init__(self):
        self._word_scancodes: list[int] = []
        self._word_shifts: list[bool] = []
        self._last_word_scancodes: list[int] = []
        self._last_word_shifts: list[bool] = []
        self._dictionary = DictionaryMatcher()
        self._current_layout: str = EN
        self._preferred_cyrillic: str = RU
        self._force_layout_sync: bool = False

    @property
    def current_layout(self) -> str:
        return self._current_layout

    @current_layout.setter
    def current_layout(self, value: str) -> None:
        self._current_layout = value

    def on_key(self, scancode: int, shifted: bool = False, ctrl: bool = False) -> Detection | None:
        """Process a keystroke. Returns Detection on word boundary if wrong layout."""

        # Ctrl + any key → buffer is unreliable (paste, cut, undo, etc.)
        # Reset buffer but keep current_layout — it will be re-synced
        # at the start of the next word in the main loop
        if ctrl:
            self.reset()
            self._force_layout_sync = True
            return None

        # Word boundary — analyze completed word
        if scancode in WORD_BOUNDARY_SCANCODES:
            self._last_word_scancodes = self._word_scancodes.copy()
            self._last_word_shifts = self._word_shifts.copy()
            detection = self._analyze_word()
            self._word_scancodes.clear()
            self._word_shifts.clear()
            return detection

        # Edit keys — adjust buffer
        if scancode in EDIT_SCANCODES:
            if scancode == ecodes.KEY_BACKSPACE:
                # Remove last character from buffer
                if self._word_scancodes:
                    self._word_scancodes.pop()
                    self._word_shifts.pop()
            else:
                # Arrows, Home, End, Delete — cursor moved, buffer unreliable
                self.reset()
            return None

        # Collect all mapped keys into word buffer (alpha, digits, punctuation)
        # so that URLs like "legal.org.ua/blog" are replayed intact
        if scancode in KEYMAP:
            self._word_scancodes.append(scancode)
            self._word_shifts.append(shifted)

        return None

    def _analyze_word(self) -> Detection | None:
        """Analyze completed word and decide if layout switch is needed."""
        alpha_count = sum(1 for sc in self._word_scancodes if sc in ALPHA_SCANCODES)
        if alpha_count < MIN_WORD_LENGTH:
            return None

        scancodes = self._word_scancodes.copy()
        shifts = self._word_shifts.copy()

        # Build candidate texts
        texts = {}
        for lang in LAYOUTS:
            texts[lang] = scancodes_to_text(scancodes, lang, shifts)

        # Tier 1: Exclusive letter check (RU vs UA)
        has_ru_exclusive = False
        has_ua_indicator = False
        for sc in scancodes:
            if sc in RU_EXCLUSIVE_SCANCODES:
                entry = KEYMAP[sc]
                ru_char = entry[RU][0]
                ua_char = entry[UA][0]
                # These scancodes produce different chars in RU vs UA
                if ru_char in "ыэъё":
                    has_ru_exclusive = True
                if ua_char in "іїєґ":
                    has_ua_indicator = True

        # Tier 2: N-gram scoring
        ngram_scores = score_all_languages(texts)

        # Tier 3: Dictionary scoring (exact word match)
        dict_scores = self._dictionary.score_prefix(texts)

        # Combined scores — dictionary match is a strong signal
        combined = {}
        for lang in LAYOUTS:
            ngram = ngram_scores.get(lang, -1.0)
            dict_match = dict_scores.get(lang, 0.0)
            # Dictionary bonus: if word found, add significant boost
            combined[lang] = NGRAM_WEIGHT * ngram + DICT_WEIGHT * dict_match * 2.0

        # Rank
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        best_lang, best_score = ranked[0]
        second_lang, second_score = ranked[1]
        third_lang, third_score = ranked[2]

        # Determine confidence
        score_diff = best_score - second_score

        if score_diff > SCORE_THRESHOLD:
            confidence = Confidence.MEDIUM
            reason = f"ngram+dict: {best_lang}={best_score:.2f} vs {second_lang}={second_score:.2f}"
        else:
            # Check script family gap
            family_gap = second_score - third_score
            if family_gap > SCORE_THRESHOLD:
                # Both top candidates are same script family
                if {best_lang, second_lang} == {RU, UA}:
                    # Pick based on exclusive letters or preference
                    if has_ru_exclusive and not has_ua_indicator:
                        best_lang = RU
                    elif has_ua_indicator and not has_ru_exclusive:
                        best_lang = UA
                    else:
                        best_lang = self._preferred_cyrillic
                confidence = Confidence.MEDIUM
                reason = f"script-family: {best_lang}(pref) >> {third_lang}={third_score:.2f}"
            else:
                confidence = Confidence.LOW
                reason = f"ambiguous: {best_lang}={best_score:.2f} vs {second_lang}={second_score:.2f}"

        # Log
        logger.debug(
            "Word: en='%s' ru='%s' ua='%s' → %s (conf=%s) scores=%s",
            texts[EN], texts[RU], texts[UA],
            best_lang, confidence.name,
            {k: f"{v:.2f}" for k, v in combined.items()},
        )

        # Same as current layout — no action
        if best_lang == self._current_layout:
            return None

        # LOW confidence — return for Bedrock disambiguation (don't filter out)
        if confidence == Confidence.LOW:
            return Detection(
                language=best_lang,
                confidence=confidence,
                scores=combined,
                reason=reason,
                word_scancodes=scancodes,
                word_shifts=shifts,
            )

        # INERTIA: current layout text must be clearly worse
        current_score = combined.get(self._current_layout, -2.0)
        if current_score > -0.5 and (best_score - current_score) < INERTIA_MARGIN:
            logger.debug(
                "Inertia: staying on %s (current=%.2f, best %s=%.2f)",
                self._current_layout, current_score, best_lang, best_score,
            )
            return None

        return Detection(
            language=best_lang,
            confidence=confidence,
            scores=combined,
            reason=reason,
            word_scancodes=scancodes,
            word_shifts=shifts,
        )

    def reset(self) -> None:
        self._word_scancodes.clear()
        self._word_shifts.clear()
