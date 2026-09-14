"""Sense HAT feedback and joystick input with a no-hardware fallback."""

from __future__ import annotations

from typing import Literal


InputContext = Literal["scanner", "guidance"]

SCANNER_ACTIONS = {
    "middle": "capture",
    "left": "back",
    "down": "reset",
    "up": "cancel",
}

GUIDANCE_ACTIONS = {
    "right": "next",
    "middle": "next",
    "left": "back",
    "up": "cancel",
}

STATUS_DISPLAY = {
    "ready": ("R", (255, 255, 255)),
    "scanning": ("S", (0, 120, 255)),
    "accepted": ("A", (0, 255, 0)),
    "error": ("E", (255, 0, 0)),
    "calculating": ("C", (255, 255, 0)),
    "complete": ("D", (0, 255, 0)),
}


def map_joystick(direction: str, context: InputContext) -> str | None:
    """Map one Sense HAT direction to an application action."""
    actions = SCANNER_ACTIONS if context == "scanner" else GUIDANCE_ACTIONS
    return actions.get(direction)


class SenseHatAdapter:
    """Best-effort Sense HAT access that remains safe on ordinary laptops."""

    def __init__(self) -> None:
        self._sense = None
        try:
            from sense_hat import SenseHat

            self._sense = SenseHat()
            self._sense.low_light = True
        except (ImportError, OSError, RuntimeError):
            self._sense = None

    @property
    def available(self) -> bool:
        return self._sense is not None

    def _poll(self, context: InputContext) -> str | None:
        if self._sense is None:
            return None
        try:
            for event in self._sense.stick.get_events():
                if event.action == "pressed":
                    action = map_joystick(event.direction, context)
                    if action is not None:
                        return action
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError):
            self._sense = None
        return None

    def poll_scanner_action(self) -> str | None:
        return self._poll("scanner")

    def poll_guidance_action(self) -> str | None:
        return self._poll("guidance")

    def show_status(self, status: str, detail: str = "") -> None:
        if self._sense is None:
            return
        letter, colour = STATUS_DISPLAY.get(status, ("?", (255, 255, 255)))
        if status == "move" and detail:
            letter = detail[0].upper()
            colour = (180, 80, 255)
        try:
            self._sense.show_letter(letter, text_colour=colour, back_colour=(0, 0, 0))
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError):
            self._sense = None
