"""Tests for n-gram scoring."""

from switchamba.detection.ngram import score_bigrams, score_all_languages


class TestNgramScoring:
    def test_english_scores_high_for_english(self):
        """English text should score better as EN than as RU/UA."""
        en_score = score_bigrams("the quick brown", "en")
        ru_score = score_bigrams("the quick brown", "ru")
        assert en_score > ru_score

    def test_russian_scores_high_for_russian(self):
        """Russian text should score better as RU than as EN."""
        ru_score = score_bigrams("привет мир", "ru")
        en_score = score_bigrams("привет мир", "en")
        assert ru_score > en_score

    def test_ukrainian_scores_high_for_ukrainian(self):
        """Ukrainian text should score better as UA than as EN."""
        ua_score = score_bigrams("привіт світ", "ua")
        en_score = score_bigrams("привіт світ", "en")
        assert ua_score > en_score

    def test_cross_language_mismatch(self):
        """English text should score low against Russian bigrams."""
        en_as_ru = score_bigrams("the quick", "ru")
        en_as_en = score_bigrams("the quick", "en")
        assert en_as_en > en_as_ru

    def test_short_text(self):
        """Single character should return 0."""
        assert score_bigrams("a", "en") == 0.0

    def test_score_all_languages(self):
        texts = {"en": "hello", "ru": "руддщ", "ua": "руддщ"}
        scores = score_all_languages(texts)
        assert "en" in scores
        assert "ru" in scores
        assert "ua" in scores
        # "hello" should score highest as English
        assert scores["en"] > scores["ru"]
