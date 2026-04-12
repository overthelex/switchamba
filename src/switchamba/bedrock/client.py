"""Async AWS Bedrock client for language disambiguation.

Called when local n-gram analysis is uncertain (typically RU vs UA).
Uses Claude Haiku for fast, low-cost disambiguation.
"""

import asyncio
import json
import logging

import boto3

logger = logging.getLogger(__name__)

DISAMBIGUATION_PROMPT = """You are a keyboard layout detector. Given text that could be typed in different keyboard layouts, determine which language was intended.

The user typed on a physical keyboard. The same keystrokes produce different text depending on the active layout:
- English: {text_en}
- Russian: {text_ru}
- Ukrainian: {text_ua}

Language scores from n-gram analysis:
- English: {score_en:.2f}
- Russian: {score_ru:.2f}
- Ukrainian: {score_ua:.2f}

Which language did the user intend to type? Consider:
1. Does the text form valid words or word prefixes in any language?
2. Russian uses ы, э, ъ, ё which Ukrainian does not
3. Ukrainian uses і, ї, є, ґ which Russian does not

Respond with ONLY the language code: en, ru, or ua"""

CORRECTION_PROMPT = """Fix any spelling, grammar, or typing errors in this text.
The text may be in English, Russian, or Ukrainian (or mixed).
Return ONLY the corrected text, nothing else.
If no corrections are needed, return the text exactly as is.
Do not add punctuation at the end if there was none.
Do not change the language or style of the text.
Do not add explanations.

Text: {text}"""


class BedrockDisambiguator:
    """Async Bedrock client for language disambiguation."""

    def __init__(self, config):
        self._config = config
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=config.aws_region,
            aws_access_key_id=config.aws_access_key_id,
            aws_secret_access_key=config.aws_secret_access_key,
        )
        self._model_id = config.model_quick
        self._timeout = config.timeout_ms / 1000.0
        self._cache: dict[str, str] = {}
        self._cache_max = config.cache_size
        self._executor = None

    async def disambiguate(
        self,
        texts: dict[str, str],
        scores: dict[str, float],
    ) -> str | None:
        """Ask Bedrock to disambiguate between languages.

        Args:
            texts: {"en": "...", "ru": "...", "ua": "..."} — same keystrokes in each layout
            scores: {"en": 0.5, "ru": 0.8, "ua": 0.75} — local n-gram scores

        Returns:
            Language code ("en", "ru", "ua") or None on failure/timeout.
        """
        # Check cache
        cache_key = f"{texts.get('en', '')}|{texts.get('ru', '')}|{texts.get('ua', '')}"
        if cache_key in self._cache:
            logger.debug("Bedrock cache hit: %s", self._cache[cache_key])
            return self._cache[cache_key]

        prompt = DISAMBIGUATION_PROMPT.format(
            text_en=texts.get("en", ""),
            text_ru=texts.get("ru", ""),
            text_ua=texts.get("ua", ""),
            score_en=scores.get("en", 0),
            score_ru=scores.get("ru", 0),
            score_ua=scores.get("ua", 0),
        )

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 5,
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        })

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda: self._client.invoke_model(
                        modelId=self._model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json",
                    ),
                ),
                timeout=self._timeout,
            )

            response_body = json.loads(result["body"].read())
            answer = response_body["content"][0]["text"].strip().lower()

            if answer in ("en", "ru", "ua"):
                # Cache the result
                if len(self._cache) >= self._cache_max:
                    # Evict oldest entry
                    oldest_key = next(iter(self._cache))
                    del self._cache[oldest_key]
                self._cache[cache_key] = answer

                logger.info("Bedrock disambiguated: %s (texts: en=%s, ru=%s, ua=%s)",
                           answer, texts.get("en"), texts.get("ru"), texts.get("ua"))
                return answer
            else:
                logger.warning("Bedrock returned unexpected answer: %s", answer)
                return None

        except asyncio.TimeoutError:
            logger.debug("Bedrock timeout after %.0fms", self._timeout * 1000)
            return None
        except Exception as e:
            logger.warning("Bedrock call failed: %s", e)
            return None

    async def correct_text(self, text: str) -> str | None:
        """Send text to Bedrock Sonnet for spelling/grammar correction.

        Returns corrected text, or None on failure/timeout.
        """
        if not text.strip():
            return None

        model_id = self._config.model_standard
        if not model_id:
            logger.warning("No model_standard configured for text correction")
            return None

        prompt = CORRECTION_PROMPT.format(text=text)
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max(len(text) * 2, 200),
            "temperature": 0,
            "messages": [{"role": "user", "content": prompt}],
        })

        try:
            result = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    lambda: self._client.invoke_model(
                        modelId=model_id,
                        body=body,
                        contentType="application/json",
                        accept="application/json",
                    ),
                ),
                timeout=8.0,
            )

            response_body = json.loads(result["body"].read())
            corrected = response_body["content"][0]["text"].strip()
            logger.info("Bedrock correction: '%s' → '%s'", text, corrected)
            return corrected

        except asyncio.TimeoutError:
            logger.warning("Bedrock correction timeout")
            return None
        except Exception as e:
            logger.warning("Bedrock correction failed: %s", e)
            return None
