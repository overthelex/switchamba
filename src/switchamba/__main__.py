"""Switchamba entry point.

Runs the async event loop that reads keystrokes, detects language,
and switches layouts automatically.
"""

import asyncio
import logging
import sys

from .config import load_config
from .detection.detector import LanguageDetector, Confidence
from .input.reader import KeystrokeReader
from .switching.switcher import LayoutSwitcher

logger = logging.getLogger("switchamba")

# Optional Bedrock import
_bedrock_client = None


async def _init_bedrock(config):
    """Initialize Bedrock client if enabled."""
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
    # Initialize components
    reader = KeystrokeReader(device_path=config.device_path)
    detector = LanguageDetector(buffer_size=config.detection.buffer_size)
    switcher = LayoutSwitcher()

    await switcher.initialize()
    detector.current_layout = switcher.current_layout

    await _init_bedrock(config)

    await reader.start()
    logger.info("Switchamba started. Listening for keystrokes...")
    logger.info("Layouts: %s", config.switching.layout_indices)

    # Signal GNOME Shell extension that switchamba is active
    await _set_indicator_active(True)

    # Start background layout polling (detects manual switches)
    asyncio.create_task(_poll_layout(detector, switcher))

    try:
        async for key_event in reader.read_events():
            # Sync detector with actual layout on every word start
            if len(detector._buffer) == 0:
                actual = await switcher.poll_current()
                if actual != detector.current_layout:
                    detector.current_layout = actual

            detection = detector.on_key(key_event.scancode, key_event.shifted)

            if detection is None:
                continue

            if detection.confidence == Confidence.LOW and _bedrock_client is not None:
                asyncio.create_task(
                    _bedrock_disambiguate(detector, switcher, detection)
                )
            elif detection.confidence.value >= Confidence.MEDIUM.value:
                # Get buffer scancodes to replay after layout switch
                buf_scancodes = list(detector._buffer)
                buf_shifts = list(detector._shift_buffer)
                wrong_text = detector.get_buffer_text(detector.current_layout)
                correct_text = detector.get_buffer_text(detection.language)

                # Suppress evdev — collect pending keystrokes during backspace+switch
                reader.suppress(0.2)

                # Do backspace + layout switch (but NOT replay yet)
                corrected = await switcher.backspace_and_switch(
                    detection.language, len(buf_scancodes)
                )

                # Drain keys typed during backspace+switch phase
                pending = reader.drain_pending()

                # Combine: original buffer + pending = all scancodes to replay
                all_scancodes = buf_scancodes + [p[0] for p in pending]
                all_shifts = buf_shifts + [p[1] for p in pending]

                # Suppress during replay
                reader.suppress(len(all_scancodes) * 0.02 + 0.1)
                await switcher.replay_scancodes(all_scancodes, all_shifts)

                if pending:
                    logger.info("Replayed %d + %d pending keys", len(buf_scancodes), len(pending))
                if corrected:
                    detector.current_layout = detection.language
                    detector.mark_corrected()
                    logger.info(
                        "Corrected to %s (%s): '%s' → '%s' — %s",
                        detection.language,
                        detection.confidence.name,
                        wrong_text,
                        correct_text,
                        detection.reason,
                    )
    finally:
        await _set_indicator_active(False)
        await reader.stop()


async def _set_indicator_active(active: bool) -> None:
    """Signal GNOME Shell extension indicator about switchamba status."""
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
    """Periodically poll actual layout to detect manual switches."""
    while True:
        await asyncio.sleep(1.0)
        try:
            actual = await switcher.poll_current()
            if actual != detector.current_layout:
                detector.current_layout = actual
        except Exception:
            pass


async def _bedrock_disambiguate(detector, switcher, detection) -> None:
    """Handle async Bedrock disambiguation for low-confidence detections."""
    try:
        texts = {}
        for lang in ("en", "ru", "ua"):
            texts[lang] = detector.get_buffer_text(lang)

        result = await _bedrock_client.disambiguate(texts, detection.scores)
        if result and result != switcher.current_layout:
            switched = await switcher.switch_to(result)
            if switched:
                detector.current_layout = result
                logger.info("Bedrock switched to %s", result)
    except Exception as e:
        logger.debug("Bedrock disambiguation failed: %s", e)


def main():
    """CLI entry point."""
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
