"""Dictionary-based word matching for language detection.

Loads words from system hunspell dictionaries. Uses set for O(1) exact match.
"""

import logging
import os

logger = logging.getLogger(__name__)

DICT_PATHS = {
    "en": ["/usr/share/dict/american-english", "/usr/share/dict/british-english"],
    "ru": ["/usr/share/hunspell/ru_RU.dic"],
    "ua": ["/usr/share/hunspell/uk_UA.dic"],
}


def _load_dict_file(path: str, is_hunspell: bool = True) -> set[str]:
    words = set()
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if is_hunspell and i == 0:
                    continue
                word = line.strip().split("/")[0].lower()
                if word and len(word) >= 2 and word.isalpha():
                    words.add(word)
    except OSError:
        pass
    return words


class DictionaryMatcher:
    """Matches words against system dictionaries."""

    def __init__(self):
        self.wordsets: dict[str, set[str]] = {}
        self._load()

    def _load(self) -> None:
        for lang, paths in DICT_PATHS.items():
            for path in paths:
                if os.path.exists(path):
                    is_hunspell = path.endswith(".dic")
                    words = _load_dict_file(path, is_hunspell=is_hunspell)
                    self.wordsets[lang] = words
                    logger.info("Loaded %d words for %s from %s", len(words), lang, path)
                    break
            else:
                self.wordsets[lang] = set()
                logger.warning("No dictionary found for %s", lang)

    def score_prefix(self, texts: dict[str, str]) -> dict[str, float]:
        """Score each language's text interpretation.

        Returns 1.0 if the last word is in the dictionary, 0.0 otherwise.
        """
        scores: dict[str, float] = {}
        for lang, text in texts.items():
            words = text.strip().lower().split()
            if not words:
                scores[lang] = 0.0
                continue

            last_word = words[-1]
            wordset = self.wordsets.get(lang, set())

            if last_word in wordset:
                scores[lang] = 1.0
            else:
                scores[lang] = 0.0

        return scores
