"""Async evdev keystroke reader.

Captures raw keyboard events from /dev/input/event* devices.
Auto-detects the keyboard device by checking capabilities.
"""

import asyncio
import logging
from dataclasses import dataclass

import evdev
from evdev import ecodes

from .keymap import KEYMAP, EDIT_SCANCODES

logger = logging.getLogger(__name__)

# Sentinel scancode emitted on double-Ctrl tap
DOUBLE_CTRL_SCANCODE = -1
# Sentinel scancode emitted on double-Alt tap
DOUBLE_ALT_SCANCODE = -2


@dataclass
class KeyEvent:
    """A processed key event."""
    scancode: int
    pressed: bool  # True = key down, False = key up
    shifted: bool  # True if Shift was held
    ctrl: bool  # True if Ctrl was held
    timestamp: float


def find_keyboard_devices() -> list[evdev.InputDevice]:
    """Find all keyboard input devices.

    Keyboards are identified by having EV_KEY capability with letter keys
    and EV_REP (key repeat) capability.
    """
    keyboards = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities()

            has_keys = ecodes.EV_KEY in caps

            if has_keys:
                key_caps = caps[ecodes.EV_KEY]
                # Must have letter keys (Q, W, E, R, T, A...)
                has_letters = (
                    ecodes.KEY_Q in key_caps
                    and ecodes.KEY_A in key_caps
                    and ecodes.KEY_Z in key_caps
                )
                if has_letters:
                    keyboards.append(device)
                    logger.info("Found keyboard: %s (%s)", device.name, device.path)
                else:
                    device.close()
            else:
                device.close()
        except (PermissionError, OSError) as e:
            logger.debug("Cannot access %s: %s", path, e)

    return keyboards


class KeystrokeReader:
    """Async reader for keyboard events from evdev devices."""

    def __init__(self, device_path: str | None = None):
        self._device_path = device_path
        self._devices: list[evdev.InputDevice] = []
        self._shift_held = False
        self._ctrl_held = False
        self._ctrl_other_key = False  # True if non-modifier pressed while Ctrl held
        self._last_ctrl_tap: float = 0.0  # monotonic time of last clean Ctrl tap
        self._alt_held = False
        self._alt_other_key = False  # True if non-modifier pressed while Alt held
        self._last_alt_tap: float = 0.0  # monotonic time of last clean Alt tap
        self._running = False
        self._suppress_until: float = 0.0  # Ignore events until this timestamp
        self._pending_scancodes: list[tuple[int, bool]] = []  # Collected during suppress

    def suppress(self, duration: float = 0.3) -> None:
        """Suppress event processing for `duration` seconds.

        Events during suppression are collected in _pending_scancodes
        so they can be replayed after correction.
        """
        import time
        self._pending_scancodes.clear()
        self._suppress_until = time.monotonic() + duration

    def drain_pending(self) -> list[tuple[int, bool]]:
        """Get and clear scancodes collected during suppression."""
        pending = self._pending_scancodes.copy()
        self._pending_scancodes.clear()
        return pending

    async def start(self) -> None:
        """Open device(s) and prepare for reading."""
        if self._device_path:
            device = evdev.InputDevice(self._device_path)
            self._devices = [device]
            logger.info("Using specified device: %s (%s)", device.name, device.path)
        else:
            self._devices = find_keyboard_devices()
            if not self._devices:
                raise RuntimeError(
                    "No keyboard devices found. "
                    "Make sure you are in the 'input' group: "
                    "sudo usermod -aG input $USER"
                )

        self._running = True

    async def stop(self) -> None:
        """Close all devices."""
        self._running = False
        for device in self._devices:
            try:
                device.close()
            except OSError:
                pass
        self._devices = []

    async def read_events(self):
        """Async generator yielding KeyEvent objects from all keyboards.

        Only yields events for keys that are in our keymap (letters, punctuation).
        Tracks shift state internally.
        """
        if not self._devices:
            raise RuntimeError("Call start() before read_events()")

        # Merge events from all devices into a single queue
        merged: asyncio.Queue[KeyEvent | None] = asyncio.Queue()
        for device in self._devices:
            asyncio.create_task(self._device_reader(device, merged))

        while self._running:
            event = await merged.get()
            if event is None:
                break
            yield event

    async def _device_reader(
        self, device: evdev.InputDevice, queue: asyncio.Queue
    ) -> None:
        """Read events from a single device and put them into a queue."""
        try:
            async for event in device.async_read_loop():
                if not self._running:
                    break
                if event.type != ecodes.EV_KEY:
                    continue

                # During correction replay: collect scancodes but don't emit
                import time as _time
                if _time.monotonic() < self._suppress_until:
                    key_event_raw = evdev.categorize(event)
                    if key_event_raw.keystate == key_event_raw.key_down:
                        if event.code in KEYMAP:
                            self._pending_scancodes.append((event.code, self._shift_held))
                    # Track modifiers even during suppress
                    if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                        self._shift_held = key_event_raw.keystate in (
                            key_event_raw.key_down, key_event_raw.key_hold,
                        )
                    if event.code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                        self._ctrl_held = key_event_raw.keystate in (
                            key_event_raw.key_down, key_event_raw.key_hold,
                        )
                    if event.code in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT):
                        self._alt_held = key_event_raw.keystate in (
                            key_event_raw.key_down, key_event_raw.key_hold,
                        )
                    continue

                key_event = evdev.categorize(event)

                # Track shift state
                if event.code in (ecodes.KEY_LEFTSHIFT, ecodes.KEY_RIGHTSHIFT):
                    self._shift_held = key_event.keystate in (
                        key_event.key_down,
                        key_event.key_hold,
                    )
                    continue

                # Track ctrl state and detect double-tap
                if event.code in (ecodes.KEY_LEFTCTRL, ecodes.KEY_RIGHTCTRL):
                    was_held = self._ctrl_held
                    self._ctrl_held = key_event.keystate in (
                        key_event.key_down,
                        key_event.key_hold,
                    )
                    if key_event.keystate == key_event.key_down:
                        self._ctrl_other_key = False
                    elif was_held and not self._ctrl_held and not self._ctrl_other_key:
                        # Clean Ctrl release (no other key pressed during hold)
                        import time as _t2
                        now = _t2.monotonic()
                        if now - self._last_ctrl_tap < 0.4:
                            self._last_ctrl_tap = 0.0
                            ke = KeyEvent(
                                scancode=DOUBLE_CTRL_SCANCODE,
                                pressed=True, shifted=False, ctrl=False,
                                timestamp=event.timestamp(),
                            )
                            await queue.put(ke)
                        else:
                            self._last_ctrl_tap = now
                    continue

                # Track alt state and detect double-tap
                if event.code in (ecodes.KEY_LEFTALT, ecodes.KEY_RIGHTALT):
                    was_held = self._alt_held
                    self._alt_held = key_event.keystate in (
                        key_event.key_down,
                        key_event.key_hold,
                    )
                    if key_event.keystate == key_event.key_down:
                        self._alt_other_key = False
                    elif was_held and not self._alt_held and not self._alt_other_key:
                        # Clean Alt release (no other key pressed during hold)
                        import time as _t3
                        now = _t3.monotonic()
                        if now - self._last_alt_tap < 0.4:
                            self._last_alt_tap = 0.0
                            ke = KeyEvent(
                                scancode=DOUBLE_ALT_SCANCODE,
                                pressed=True, shifted=False, ctrl=False,
                                timestamp=event.timestamp(),
                            )
                            await queue.put(ke)
                        else:
                            self._last_alt_tap = now
                    continue

                # Mark if non-modifier key pressed while Ctrl or Alt held
                if self._ctrl_held and key_event.keystate == key_event.key_down:
                    self._ctrl_other_key = True
                if self._alt_held and key_event.keystate == key_event.key_down:
                    self._alt_other_key = True

                # Only process key-down events for mapped or edit keys
                if key_event.keystate != key_event.key_down:
                    continue

                if event.code not in KEYMAP and event.code not in EDIT_SCANCODES:
                    continue

                ke = KeyEvent(
                    scancode=event.code,
                    pressed=True,
                    shifted=self._shift_held,
                    ctrl=self._ctrl_held,
                    timestamp=event.timestamp(),
                )
                await queue.put(ke)

        except OSError as e:
            logger.error("Device %s disconnected: %s", device.name, e)
        finally:
            await queue.put(None)

