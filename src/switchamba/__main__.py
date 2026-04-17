"""Switchamba entry point.

Word-boundary correction: collects keystrokes during word typing,
analyzes on space/enter, and corrects if wrong layout detected.
"""

import asyncio
import logging
import sys

from .config import load_config
from .detection.detector import LanguageDetector, Confidence
from .input.reader import KeystrokeReader, DOUBLE_CTRL_SCANCODE, DOUBLE_ALT_SCANCODE
from .input.keymap import scancodes_to_text, WORD_BOUNDARY_SCANCODES
from .switching.switcher import LayoutSwitcher

logger = logging.getLogger("switchamba")

_bedrock_client = None

# Terminal apps where Shift+Home / Ctrl+C behave differently
_TERMINAL_WM_CLASSES = frozenset({
    "gnome-terminal", "gnome-terminal-server",
    "kitty", "alacritty", "foot", "wezterm",
    "konsole", "xterm", "tilix", "terminator",
    "org.gnome.terminal", "com.raggesilver.blackbox",
    "org.wezfurlong.wezterm",
})


async def _get_focused_wm_class() -> str | None:
    """Get WM_CLASS of the focused window via switchamba GNOME extension D-Bus."""
    try:
        from .switching.switcher import DBUS_DEST
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: __import__("subprocess").run(
                [
                    "gdbus", "call", "--session",
                    "--dest", DBUS_DEST,
                    "--object-path", "/com/switchamba/WindowInfo",
                    "--method", "com.switchamba.WindowInfo.GetFocusedApp",
                ],
                capture_output=True, text=True, timeout=2,
            ),
        )
        if result.returncode == 0:
            # Output: ('gnome-terminal-server',)
            out = result.stdout.strip()
            import re
            m = re.search(r"'(.+?)'", out)
            if m:
                return m.group(1).lower()
    except Exception as e:
        logger.debug("Could not get focused window class: %s", e)
    return None


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

    # Stats tracking
    stats = {"ngram": 0, "dict": 0, "script_family": 0, "bedrock": 0, "total": 0}

    # Double-Alt reliteration cycle: RU → UA → EN → RU ...
    reliterate_cycle = ["ru", "ua", "en"]
    reliterate_idx = 0  # current position in cycle
    reliterate_last_scancodes: list[int] = []  # scancodes of word being cycled

    await switcher.initialize()
    detector.current_layout = switcher.current_layout

    await _init_bedrock(config)

    await reader.start()
    logger.info("Switchamba started. Listening for keystrokes...")

    await _set_indicator_active(True)
    asyncio.create_task(_poll_layout(detector, switcher))

    # Sync layout before first keystroke
    actual = await switcher.poll_current()
    if actual:
        detector.current_layout = actual

    try:
        async for key_event in reader.read_events():
            # Sync layout at start of each word or after Ctrl (paste/cut)
            if len(detector._word_scancodes) == 0 or detector._force_layout_sync:
                actual = await switcher.poll_current()
                if actual != detector.current_layout:
                    detector.current_layout = actual
                detector._force_layout_sync = False

            # Double-Ctrl: select line left of cursor, send to Bedrock for correction
            if key_event.scancode == DOUBLE_CTRL_SCANCODE:
                await _handle_line_correction(reader, switcher, detector)
                continue

            # Double-Alt: cycle last word through RU → UA → EN
            if key_event.scancode == DOUBLE_ALT_SCANCODE:
                word_sc = detector._last_word_scancodes
                word_sh = detector._last_word_shifts
                if not word_sc:
                    continue

                # First tap on a new word — start cycle from current layout
                if word_sc != reliterate_last_scancodes:
                    reliterate_last_scancodes = word_sc.copy()
                    try:
                        reliterate_idx = reliterate_cycle.index(detector.current_layout)
                    except ValueError:
                        reliterate_idx = 0

                # Advance to next language in cycle
                reliterate_idx = (reliterate_idx + 1) % len(reliterate_cycle)
                target = reliterate_cycle[reliterate_idx]

                old_text = scancodes_to_text(word_sc, detector.current_layout, word_sh)
                new_text = scancodes_to_text(word_sc, target, word_sh)

                # Delete word + trailing boundary char
                delete_count = len(word_sc) + 1
                suppress_time = delete_count * 0.02 + 0.15 + len(word_sc) * 0.02 + 0.1
                reader.suppress(suppress_time)

                corrected = await switcher.backspace_and_switch(target, delete_count)
                if corrected:
                    await switcher.replay_scancodes(word_sc, word_sh)
                    # Re-type boundary (space)
                    from evdev import ecodes as _ec
                    await switcher.replay_scancodes([_ec.KEY_SPACE], [False])
                    detector.current_layout = target
                    logger.info(
                        "[double-alt] '%s' → '%s' (%s)",
                        old_text, new_text, target,
                    )

                reader.drain_pending()
                continue

            detection = detector.on_key(key_event.scancode, key_event.shifted, key_event.ctrl)

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
                    detection._channel = "bedrock"
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

            # Suppress evdev for the detector and grab the keyboard so user
            # keystrokes typed during correction are queued and don't
            # interleave with our backspace/replay.
            suppress_time = delete_count * 0.02 + 0.15 + len(word_sc) * 0.02 + 0.1
            reader.suppress(suppress_time)
            reader.grab()

            try:
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

                    # Classify detection channel
                    channel = getattr(detection, "_channel", None)
                    if channel is None:
                        reason = detection.reason
                        if "ngram+dict" in reason:
                            channel = "dict" if any(
                                f": {v}" in reason for v in ["1.0", "0.5"]
                            ) else "ngram"
                        elif "script-family" in reason:
                            channel = "script_family"
                        elif "exclusive" in reason:
                            channel = "script_family"
                        else:
                            channel = "ngram"

                    stats[channel] = stats.get(channel, 0) + 1
                    stats["total"] += 1

                    logger.info(
                        "[%s] '%s' → '%s' (%s) | stats: ngram=%d dict=%d family=%d bedrock=%d total=%d",
                        channel, wrong_text, correct_text, target_lang,
                        stats["ngram"], stats["dict"], stats["script_family"],
                        stats["bedrock"], stats["total"],
                    )

                # Flush keys the user typed while the keyboard was grabbed.
                # Replay them via UInput in the (now current) layout and feed
                # into the detector so the next word's buffer is accurate.
                pending = reader.drain_pending()
                if pending:
                    await switcher.replay_scancodes(
                        [sc for sc, _ in pending],
                        [sh for _, sh in pending],
                    )
                    for sc, sh in pending:
                        detector.on_key(sc, sh, False)
                    logger.debug("Replayed %d key(s) typed during correction", len(pending))
            finally:
                reader.ungrab()
    finally:
        await _set_indicator_active(False)
        await reader.stop()


async def _handle_line_correction(reader, switcher, detector) -> None:
    """Handle double-Ctrl: select line left of cursor, correct via Bedrock Sonnet."""
    if _bedrock_client is None:
        logger.debug("Double-Ctrl ignored: Bedrock not configured")
        return

    # Skip in terminal apps where Shift+Home/Ctrl+C don't work as expected
    wm_class = await _get_focused_wm_class()
    if wm_class and wm_class in _TERMINAL_WM_CLASSES:
        logger.info("Double-Ctrl ignored: terminal app '%s'", wm_class)
        return

    # Suppress reader during the entire operation
    reader.suppress(15.0)
    detector.reset()

    # Preserve user's existing clipboard so we can restore it after
    old_clipboard = await switcher.read_clipboard()

    try:
        # Clear clipboard first so an empty selection cannot leak prior
        # clipboard content into Bedrock / paste path
        await switcher.clear_clipboard()
        await asyncio.sleep(0.05)

        # Select text from cursor to line start
        await switcher.select_to_line_start()
        await asyncio.sleep(0.05)

        # Copy selection
        await switcher.copy_selection()
        await asyncio.sleep(0.1)

        # Read clipboard. If still empty, selection was empty — abort.
        text = await switcher.read_clipboard()
        if not text or not text.strip():
            await switcher.cancel_selection()
            logger.debug("Double-Ctrl: empty selection, nothing to correct")
            return

        logger.info("Double-Ctrl: correcting '%s'", text)

        # Send to Bedrock Sonnet
        corrected = await _bedrock_client.correct_text(text)

        if corrected and corrected != text:
            # Paste corrected text (selection is still active, will be replaced)
            await switcher.write_clipboard_and_paste(corrected)
            logger.info("Double-Ctrl corrected: '%s' → '%s'", text, corrected)
        else:
            # No changes — cancel selection
            await switcher.cancel_selection()
            logger.debug("Double-Ctrl: no corrections needed")

    except Exception as e:
        logger.warning("Double-Ctrl correction failed: %s", e)
        await switcher.cancel_selection()
    finally:
        # Let any pending paste settle before we stomp on the clipboard
        await asyncio.sleep(0.15)
        if old_clipboard is not None:
            await switcher.write_clipboard(old_clipboard)
        # Discard any keys pressed during the operation
        reader.drain_pending()
        reader.suppress(0.3)


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
