"""Three-tier language detector with rolling buffer.

Tier 1: Exclusive letter detection (instant RU vs UA discrimination)
Tier 2: N-gram frequency analysis
Tier 3: Dictionary prefix matching

Outputs a language prediction with confidence score.
"""

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from ..input.keymap import (
    EN, RU, UA, LAYOUTS,
    KEYMAP, ALPHA_SCANCODES, WORD_BOUNDARY_SCANCODES,
    RU_EXCLUSIVE_SCANCODES,
    scancodes_to_text,
)
from .ngram import score_all_languages
from .dictionary import DictionaryMatcher

logger = logging.getLogger(__name__)


class Confidence(Enum):
    """Detection confidence level."""
    NONE = 0       # Not enough data
    LOW = 1        # Ambiguous, consider Bedrock
    MEDIUM = 2     # Likely correct
    HIGH = 3       # Certain (exclusive letter detected)


@dataclass
class Detection:
    """Result of language detection."""
    language: str           # "en", "ru", or "ua"
    confidence: Confidence
    scores: dict[str, float] = field(default_factory=dict)
    reason: str = ""


# Minimum characters before making a detection
MIN_BUFFER_SIZE = 3

# Score difference threshold for confident detection
SCORE_THRESHOLD = 0.3

# Weight factors for combining scores
NGRAM_WEIGHT = 0.7
DICT_WEIGHT = 0.3


class LanguageDetector:
    """Detects intended language from a rolling buffer of scancodes."""

    def __init__(self, buffer_size: int = 8):
        self._buffer: deque[int] = deque(maxlen=buffer_size)
        self._shift_buffer: deque[bool] = deque(maxlen=buffer_size)
        self._dictionary = DictionaryMatcher()
        self._last_detection: Detection | None = None
        self._current_layout: str = EN
        self._preferred_cyrillic: str = RU  # Default Cyrillic preference
        self._corrected_this_word: bool = False  # Prevent re-correction within same word

    @property
    def current_layout(self) -> str:
        return self._current_layout

    @current_layout.setter
    def current_layout(self, value: str) -> None:
        self._current_layout = value
        # Only update preferred Cyrillic when explicitly set by user
        # (e.g., exclusive UA letters detected, not just ambiguous detection)

    def mark_corrected(self) -> None:
        """Mark that correction was applied for this word. Prevents re-triggering."""
        self._corrected_this_word = True

    def set_preferred_cyrillic(self, value: str) -> None:
        """Explicitly set preferred Cyrillic layout (e.g., after exclusive letter detection)."""
        if value in (RU, UA):
            self._preferred_cyrillic = value

    def on_key(self, scancode: int, shifted: bool = False) -> Detection | None:
        """Process a new keystroke and return detection if confident enough.

        Returns None if no switch is needed (same language, or not enough data).
        Returns Detection if a layout switch should happen.
        """
        # Word boundary — reset buffer and correction flag
        if scancode in WORD_BOUNDARY_SCANCODES:
            self._buffer.clear()
            self._shift_buffer.clear()
            self._corrected_this_word = False
            return None

        # Only process alpha keys
        if scancode not in ALPHA_SCANCODES:
            return None

        self._buffer.append(scancode)
        self._shift_buffer.append(shifted)

        # Not enough data yet
        if len(self._buffer) < MIN_BUFFER_SIZE:
            return None

        # Already corrected this word — don't re-trigger
        if self._corrected_this_word:
            return None

        # Run detection tiers
        detection = self._detect()

        if detection is None:
            return None

        # Log every detection for debugging
        buf_texts = {lang: scancodes_to_text(list(self._buffer), lang, list(self._shift_buffer)) for lang in LAYOUTS}
        logger.debug(
            "Detection: %s (conf=%s) | buf=[%s] en='%s' ru='%s' ua='%s' | scores=%s",
            detection.language, detection.confidence.name,
            ",".join(str(s) for s in self._buffer),
            buf_texts[EN], buf_texts[RU], buf_texts[UA],
            {k: f"{v:.2f}" for k, v in detection.scores.items()},
        )

        # Only return if detected language differs from current
        if detection.language == self._current_layout:
            self._last_detection = detection
            return None

        # INERTIA: Don't switch if current layout produces reasonable text.
        # Only switch when current layout text is clearly worse (gibberish).
        current_score = detection.scores.get(self._current_layout, -2.0)
        best_score = detection.scores.get(detection.language, -2.0)
        inertia_margin = 0.5  # Must beat current layout by this much

        if current_score > -0.5:
            # Current layout produces reasonable text — require strong evidence
            if best_score - current_score < inertia_margin:
                logger.debug(
                    "Inertia: staying on %s (current=%.2f, best %s=%.2f, margin=%.2f)",
                    self._current_layout, current_score,
                    detection.language, best_score, best_score - current_score,
                )
                return None

        # For MEDIUM/HIGH confidence, switch
        if detection.confidence.value >= Confidence.MEDIUM.value:
            self._last_detection = detection
            return detection

        # LOW confidence — return for potential Bedrock disambiguation
        if detection.confidence == Confidence.LOW:
            self._last_detection = detection
            return detection

        return None

    def _detect(self) -> Detection | None:
        """Run all detection tiers and produce a result."""
        scancodes = list(self._buffer)
        shifts = list(self._shift_buffer)

        # Tier 1: Exclusive letter check
        tier1 = self._tier1_exclusive(scancodes)
        if tier1 is not None:
            return tier1

        # Build candidate texts for each layout
        texts = {}
        for lang in LAYOUTS:
            texts[lang] = scancodes_to_text(scancodes, lang, shifts)

        # Tier 2: N-gram scoring
        ngram_scores = score_all_languages(texts)

        # Tier 3: Dictionary prefix scoring
        dict_scores = self._dictionary.score_prefix(texts)

        # Combine scores
        combined = {}
        for lang in LAYOUTS:
            combined[lang] = (
                NGRAM_WEIGHT * ngram_scores.get(lang, -2.0) +
                DICT_WEIGHT * dict_scores.get(lang, 0.0)
            )

        # Find best and second-best
        ranked = sorted(combined.items(), key=lambda x: x[1], reverse=True)
        best_lang, best_score = ranked[0]
        second_lang, second_score = ranked[1]

        score_diff = best_score - second_score
        third_lang, third_score = ranked[2]

        if score_diff > SCORE_THRESHOLD:
            confidence = Confidence.MEDIUM
            reason = f"ngram+dict: {best_lang}={best_score:.2f} vs {second_lang}={second_score:.2f}"
        else:
            # Best and second are close. But check if they are BOTH much better
            # than the third — means we're confident about the script family
            # (e.g. both RU and UA >> EN means it's definitely Cyrillic).
            family_gap = second_score - third_score
            if family_gap > SCORE_THRESHOLD:
                # We know the script family. If both are Cyrillic (RU/UA),
                # use preferred Cyrillic layout since we can't distinguish.
                if {best_lang, second_lang} == {RU, UA}:
                    best_lang = self._preferred_cyrillic
                confidence = Confidence.MEDIUM
                reason = (
                    f"script-family: {best_lang}(preferred) "
                    f"scores=[{ranked[0][0]}={ranked[0][1]:.2f}, "
                    f"{ranked[1][0]}={ranked[1][1]:.2f}] >> "
                    f"{third_lang}={third_score:.2f}"
                )
            else:
                confidence = Confidence.LOW
                reason = f"ambiguous: {best_lang}={best_score:.2f} vs {second_lang}={second_score:.2f}"

        return Detection(
            language=best_lang,
            confidence=confidence,
            scores=combined,
            reason=reason,
        )

    def _tier1_exclusive(self, scancodes: list[int]) -> Detection | None:
        """Tier 1: Check for RU/UA exclusive letters.

        If any scancode maps to a letter that exists only in one Cyrillic
        layout, we can immediately determine the intended language.
        """
        # First check: are we even typing Cyrillic?
        # If all characters form valid English text, probably English.
        texts = {}
        for lang in LAYOUTS:
            texts[lang] = scancodes_to_text(scancodes, lang)

        en_text = texts[EN]
        # If the text is all ASCII printable and looks like English, it's English
        if en_text.isascii() and en_text.isalpha():
            # Check if this looks like English via quick heuristic
            # (has vowels and consonants in reasonable proportion)
            vowels = sum(1 for c in en_text.lower() if c in "aeiou")
            if 0 < vowels < len(en_text):  # Has both vowels and consonants
                # Could be English, let n-gram analysis decide
                pass

        # Check for RU/UA discriminator scancodes in buffer
        for sc in scancodes:
            if sc in RU_EXCLUSIVE_SCANCODES:
                entry = KEYMAP[sc]
                ru_char = entry[RU][0]
                ua_char = entry[UA][0]

                # These keys produce different letters in RU vs UA.
                # The character that is "exclusive" to one layout:
                # KEY_S: ы (RU-only) vs і (UA-only)
                # KEY_APOSTROPHE: э (RU-only) vs є (UA-only)
                # KEY_RIGHTBRACE: ъ (RU-only) vs ї (UA-only)
                # KEY_GRAVE: ё (RU-only) vs ' (UA - not Cyrillic)

                # We can't determine intent from the scancode alone —
                # the user pressed the key expecting one specific letter.
                # But we know it must be Cyrillic (not English) if
                # context suggests Cyrillic.

                # Use n-gram to decide RU vs UA for the discriminator
                ru_score = 0.0
                ua_score = 0.0

                ru_text = texts[RU]
                ua_text = texts[UA]

                from .ngram import score_bigrams
                ru_score = score_bigrams(ru_text, RU)
                ua_score = score_bigrams(ua_text, UA)

                if ru_score > ua_score + 0.1:
                    return Detection(
                        language=RU,
                        confidence=Confidence.HIGH,
                        scores={RU: ru_score, UA: ua_score},
                        reason=f"exclusive letter discrimination: RU ({ru_char}) > UA ({ua_char})",
                    )
                elif ua_score > ru_score + 0.1:
                    return Detection(
                        language=UA,
                        confidence=Confidence.HIGH,
                        scores={RU: ru_score, UA: ua_score},
                        reason=f"exclusive letter discrimination: UA ({ua_char}) > RU ({ru_char})",
                    )

        return None

    def reset(self) -> None:
        """Clear the buffer and reset state."""
        self._buffer.clear()
        self._shift_buffer.clear()
        self._last_detection = None

    def get_buffer_text(self, layout: str) -> str:
        """Get the current buffer interpreted as a specific layout."""
        return scancodes_to_text(
            list(self._buffer),
            layout,
            list(self._shift_buffer),
        )
