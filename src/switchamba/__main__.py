"""Switchamba entry point.

Word-boundary correction: collects keystrokes during word typing,
analyzes on space/enter, and corrects if wrong layout detected.
"""

import asyncio
import logging
import sys

from .config import load_config
from .detection.detector import LanguageDetector, Confidence
from .input.reader import KeystrokeReader
from .input.keymap import scancodes_to_text, WORD_BOUNDARY_SCANCODES
from .switching.switcher import LayoutSwitcher

logger = logging.getLogger("switchamba")

_bedrock_client = None


async def _init_bedrock(config):
    global _bedrock_client
    if not config.bedrock.enabled:
        logger.info("Bedrock disambiguation disabled")
        return
    try:
        from .bedrock.client import BedrockDisambiguator
        _bedrock_client = BedrockDisambiguator(config.bedrock)
        logger.info("Bedrock disambiguation enabled (model: %s)", config.bedrock.model_quick)
    except Exception as e:
        logger.warning("Could not initialize Bedrock: %s", e)


async def run(config) -> None:
    """Main run loop."""
    reader = KeystrokeReader(device_path=config.device_path)
    detector = LanguageDetector()
    switcher = LayoutSwitcher()

    await switcher.initialize()
    detector.current_layout = switcher.current_layout

    await _init_bedrock(config)

    await reader.start()
    logger.info("Switchamba started. Listening for keystrokes...")

    await _set_indicator_active(True)
    asyncio.create_task(_poll_layout(detector, switcher))

    try:
        async for key_event in reader.read_events():
            # Sync layout at start of each word
            if len(detector._word_scancodes) == 0:
                actual = await switcher.poll_current()
                if actual != detector.current_layout:
                    detector.current_layout = actual

            detection = detector.on_key(key_event.scancode, key_event.shifted)

            if detection is None:
                continue

            target_lang = detection.language

            # LOW confidence → ask Bedrock if available
            if detection.confidence == Confidence.LOW and _bedrock_client is not None:
                word_sc = detection.word_scancodes
                word_sh = detection.word_shifts
                texts = {
                    lang: scancodes_to_text(word_sc, lang, word_sh)
                    for lang in ("en", "ru", "ua")
                }
                bedrock_answer = await _bedrock_client.disambiguate(
                    texts, detection.scores
                )
                if bedrock_answer and bedrock_answer != detector.current_layout:
                    target_lang = bedrock_answer
                    detection.confidence = Confidence.MEDIUM
                    detection.reason = f"bedrock: {bedrock_answer} (was {detection.reason})"
                    logger.info("Bedrock resolved: %s → %s", texts, bedrock_answer)
                else:
                    # Bedrock agrees with current layout or failed
                    continue

            if detection.confidence.value < Confidence.MEDIUM.value:
                continue

            # Word-boundary correction: backspace whole word, switch, replay
            word_sc = detection.word_scancodes
            word_sh = detection.word_shifts
            wrong_text = scancodes_to_text(word_sc, detector.current_layout, word_sh)
            correct_text = scancodes_to_text(word_sc, target_lang, word_sh)

            # +1 for the space/enter that triggered the boundary
            delete_count = len(word_sc) + 1

            # Suppress evdev during correction
            suppress_time = delete_count * 0.02 + 0.15 + len(word_sc) * 0.02 + 0.1
            reader.suppress(suppress_time)

            corrected = await switcher.backspace_and_switch(
                target_lang, delete_count
            )

            if corrected:
                # Replay word scancodes in correct layout + space
                await switcher.replay_scancodes(word_sc, word_sh)
                await switcher.replay_scancodes(
                    [key_event.scancode], [key_event.shifted]
                )
                detector.current_layout = target_lang
                logger.info(
                    "Corrected: '%s' → '%s' (%s) — %s",
                    wrong_text, correct_text,
                    target_lang,
                    detection.reason,
                )
    finally:
        await _set_indicator_active(False)
        await reader.stop()


async def _set_indicator_active(active: bool) -> None:
    try:
        import subprocess
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                [
                    "gdbus", "call", "--session",
                    "--dest", "org.gnome.Shell",
                    "--object-path", "/com/switchamba/LayoutSwitcher",
                    "--method", "com.switchamba.LayoutSwitcher.SetActive",
                    str(active).lower(),
                ],
                capture_output=True, text=True, timeout=2,
            ),
        )
    except Exception:
        pass


async def _poll_layout(detector, switcher) -> None:
    while True:
        await asyncio.sleep(1.0)
        try:
            actual = await switcher.poll_current()
            if actual != detector.current_layout:
                detector.current_layout = actual
        except Exception:
            pass


def main():
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    logger.info("Switchamba v0.1.0 — automatic EN/RU/UA layout switching")

    try:
        asyncio.run(run(config))
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Switchamba stopped.")


if __name__ == "__main__":
    main()
