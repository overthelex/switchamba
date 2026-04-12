"""Layout switching via GNOME Shell extension D-Bus API.

Uses the switchamba@vovkes GNOME Shell extension which exposes
com.switchamba.LayoutSwitcher D-Bus interface. This is the only
reliable way to switch layouts on GNOME/Wayland programmatically,
because it calls source.activate() inside GNOME Shell which triggers
Meta.Backend.lock_layout_group().
"""

import asyncio
import logging
import os
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Sound file for switch notification
_SOUND_FILE = Path(__file__).parent.parent.parent.parent / "sounds" / "switch.wav"
_SOUND_PLAYER = "pw-play"

DBUS_DEST = "org.gnome.Shell"
DBUS_PATH = "/com/switchamba/LayoutSwitcher"
DBUS_IFACE = "com.switchamba.LayoutSwitcher"

# Layout index mapping (matching GNOME input-sources order)
DEFAULT_LAYOUT_INDICES = {
    "en": 0,
    "ru": 1,
    "ua": 2,
}

# Minimum time between switches (seconds)
DEBOUNCE_INTERVAL = 0.3


class LayoutSwitcher:
    """Switches keyboard layout via GNOME Shell extension D-Bus API."""

    def __init__(self, layout_indices: dict[str, int] | None = None, sound: bool = True):
        self._indices = layout_indices or DEFAULT_LAYOUT_INDICES
        self._reverse = {v: k for k, v in self._indices.items()}
        self._last_switch_time: float = 0.0
        self._current_layout: str = "en"
        self._lock = asyncio.Lock()
        self._sound = sound and _SOUND_FILE.exists()

    def _play_sound(self) -> None:
        """Play switch notification sound (non-blocking)."""
        if self._sound:
            try:
                subprocess.Popen(
                    [_SOUND_PLAYER, str(_SOUND_FILE)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    @property
    def current_layout(self) -> str:
        return self._current_layout

    async def initialize(self) -> None:
        """Read current layout from GNOME Shell extension."""
        await self.poll_current()

    async def poll_current(self) -> str:
        """Read current layout via D-Bus and update internal state."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    [
                        "gdbus", "call", "--session",
                        "--dest", DBUS_DEST,
                        "--object-path", DBUS_PATH,
                        "--method", f"{DBUS_IFACE}.GetCurrent",
                    ],
                    capture_output=True, text=True, timeout=2,
                ),
            )
            if result.returncode == 0:
                # Output is like "(uint32 0,)"
                raw = result.stdout.strip()
                # Extract number
                idx = int("".join(c for c in raw if c.isdigit()))
                lang = self._reverse.get(idx)
                if lang:
                    if lang != self._current_layout:
                        logger.info("Layout changed externally: %s → %s",
                                   self._current_layout, lang)
                    self._current_layout = lang
        except Exception as e:
            logger.debug("Could not poll layout: %s", e)
        return self._current_layout

    def _replay_keys(self, scancodes: list[int], shift_states: list[bool]) -> None:
        """Send scancodes via UInput (blocking, run in executor)."""
        from evdev import UInput, ecodes as e

        ui = UInput()
        for sc, shifted in zip(scancodes, shift_states):
            if shifted:
                ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 1)
                ui.syn()
            ui.write(e.EV_KEY, sc, 1)
            ui.syn()
            time.sleep(0.008)
            ui.write(e.EV_KEY, sc, 0)
            ui.syn()
            if shifted:
                ui.write(e.EV_KEY, e.KEY_LEFTSHIFT, 0)
                ui.syn()
            time.sleep(0.008)
        ui.close()

    async def replay_scancodes(self, scancodes: list[int], shift_states: list[bool]) -> None:
        """Replay additional scancodes (e.g. keys typed during correction)."""
        if not scancodes:
            return
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._replay_keys(scancodes, shift_states)
        )

    async def backspace_and_switch(self, language: str, delete_count: int) -> bool:
        """Backspace wrong chars and switch layout. Does NOT replay."""
        if language not in self._indices:
            return False

        now = time.monotonic()
        if now - self._last_switch_time < DEBOUNCE_INTERVAL:
            return False

        async with self._lock:
            loop = asyncio.get_event_loop()
            index = self._indices[language]
            n = delete_count

            def _do():
                from evdev import UInput, ecodes as e
                ui = UInput()
                for _ in range(n):
                    ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
                    ui.syn()
                    time.sleep(0.008)
                    ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
                    ui.syn()
                    time.sleep(0.008)
                ui.close()
                time.sleep(0.03)

                subprocess.run(
                    [
                        "gdbus", "call", "--session",
                        "--dest", DBUS_DEST,
                        "--object-path", DBUS_PATH,
                        "--method", f"{DBUS_IFACE}.SwitchTo",
                        str(index),
                    ],
                    capture_output=True, text=True, timeout=3,
                )
                time.sleep(0.08)

            await loop.run_in_executor(None, _do)

            old = self._current_layout
            self._current_layout = language
            self._last_switch_time = time.monotonic()
            self._play_sound()
            logger.info("Corrected: %s → %s (deleted %d)", old, language, n)
            return True

    async def correct_and_switch(
        self, language: str,
        scancodes: list[int], shift_states: list[bool],
    ) -> bool:
        """Erase wrong characters, switch layout, replay scancodes correctly.

        Deletes exactly len(scancodes) characters, switches layout,
        then replays the same scancodes in the new layout.
        """
        if language not in self._indices:
            return False

        now = time.monotonic()
        if now - self._last_switch_time < DEBOUNCE_INTERVAL:
            return False

        async with self._lock:
            loop = asyncio.get_event_loop()
            index = self._indices[language]
            n = len(scancodes)

            def _do_correct():
                from evdev import UInput, ecodes as e

                ui = UInput()

                # Step 1: Backspace exactly n characters
                for _ in range(n):
                    ui.write(e.EV_KEY, e.KEY_BACKSPACE, 1)
                    ui.syn()
                    time.sleep(0.008)
                    ui.write(e.EV_KEY, e.KEY_BACKSPACE, 0)
                    ui.syn()
                    time.sleep(0.008)

                ui.close()
                time.sleep(0.03)

                # Step 2: Switch layout via D-Bus
                subprocess.run(
                    [
                        "gdbus", "call", "--session",
                        "--dest", DBUS_DEST,
                        "--object-path", DBUS_PATH,
                        "--method", f"{DBUS_IFACE}.SwitchTo",
                        str(index),
                    ],
                    capture_output=True, text=True, timeout=3,
                )
                time.sleep(0.08)

                # Step 3: Replay the same scancodes in new layout
                self._replay_keys(scancodes, shift_states)

            await loop.run_in_executor(None, _do_correct)

            old = self._current_layout
            self._current_layout = language
            self._last_switch_time = time.monotonic()
            from ..input.keymap import scancodes_to_text
            correct_text = scancodes_to_text(scancodes, language, shift_states)
            logger.info("Corrected: %s → %s (deleted %d, typed '%s')",
                       old, language, n, correct_text)
            return True

    def _send_key_combo(self, modifier: int, key: int) -> None:
        """Send modifier+key combo via UInput (blocking, run in executor)."""
        from evdev import UInput, ecodes as e
        ui = UInput()
        ui.write(e.EV_KEY, modifier, 1)
        ui.syn()
        time.sleep(0.008)
        ui.write(e.EV_KEY, key, 1)
        ui.syn()
        time.sleep(0.008)
        ui.write(e.EV_KEY, key, 0)
        ui.syn()
        time.sleep(0.008)
        ui.write(e.EV_KEY, modifier, 0)
        ui.syn()
        ui.close()

    def _send_single_key(self, key: int) -> None:
        """Send a single key press/release via UInput (blocking)."""
        from evdev import UInput, ecodes as e
        ui = UInput()
        ui.write(e.EV_KEY, key, 1)
        ui.syn()
        time.sleep(0.008)
        ui.write(e.EV_KEY, key, 0)
        ui.syn()
        ui.close()

    async def select_to_line_start(self) -> None:
        """Send Shift+Home to select text from cursor to line start."""
        from evdev import ecodes as e
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._send_key_combo(e.KEY_LEFTSHIFT, e.KEY_HOME)
        )

    async def copy_selection(self) -> None:
        """Send Ctrl+C to copy selection to clipboard."""
        from evdev import ecodes as e
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._send_key_combo(e.KEY_LEFTCTRL, e.KEY_C)
        )

    async def cancel_selection(self) -> None:
        """Send Right arrow to cancel selection without moving cursor."""
        from evdev import ecodes as e
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._send_single_key(e.KEY_RIGHT)
        )

    async def read_clipboard(self) -> str | None:
        """Read clipboard contents via wl-paste (Wayland)."""
        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: subprocess.run(
                    ["wl-paste", "--no-newline"],
                    capture_output=True, text=True, timeout=2,
                ),
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout
        except Exception as e:
            logger.warning("wl-paste failed: %s", e)
        return None

    async def write_clipboard_and_paste(self, text: str) -> None:
        """Write text to clipboard via wl-copy, then Ctrl+V to paste."""
        from evdev import ecodes as e
        await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: subprocess.run(
                ["wl-copy", "--", text],
                capture_output=True, text=True, timeout=2,
            ),
        )
        await asyncio.sleep(0.05)
        await asyncio.get_event_loop().run_in_executor(
            None, lambda: self._send_key_combo(e.KEY_LEFTCTRL, e.KEY_V)
        )

    async def switch_to(self, language: str) -> bool:
        """Switch layout without correction (just switch)."""
        if language == self._current_layout:
            return False

        if language not in self._indices:
            return False

        now = time.monotonic()
        if now - self._last_switch_time < DEBOUNCE_INTERVAL:
            return False

        async with self._lock:
            index = self._indices[language]
            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [
                            "gdbus", "call", "--session",
                            "--dest", DBUS_DEST,
                            "--object-path", DBUS_PATH,
                            "--method", f"{DBUS_IFACE}.SwitchTo",
                            str(index),
                        ],
                        capture_output=True, text=True, timeout=5,
                    ),
                )
                if result.returncode == 0 and "true" in result.stdout.lower():
                    old = self._current_layout
                    self._current_layout = language
                    self._last_switch_time = time.monotonic()
                    logger.info("Switched layout: %s → %s", old, language)
                    return True
                else:
                    return False
            except Exception as e:
                logger.error("Layout switch failed: %s", e)
                return False
