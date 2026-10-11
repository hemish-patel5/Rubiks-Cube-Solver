"""Simple OpenCV move guidance with keyboard navigation."""

from __future__ import annotations

from dataclasses import dataclass

from vision.qt_runtime import configure_opencv_display

configure_opencv_display()

import cv2
import numpy as np

from vision.scanner_ui import LAVENDER, MUTED, rounded_panel, text


@dataclass
class MoveNavigator:
    moves: tuple[str, ...]
    index: int = 0

    @property
    def current(self) -> str | None:
        if not self.moves:
            return None
        return self.moves[self.index]

    def next(self) -> bool:
        """Advance and return True when every move has been shown."""
        if not self.moves or self.index == len(self.moves) - 1:
            return True
        self.index += 1
        return False

    def back(self) -> None:
        self.index = max(0, self.index - 1)


def draw_guidance(navigator: MoveNavigator) -> np.ndarray:
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    frame[:] = (20, 16, 19)
    text(frame, "Solve Cube", 320, 9, 20, heading=True, centered=True)
    current = navigator.current
    if current is None:
        heading = "Cube already solved"
        subheading = "0 moves"
    else:
        heading = current
        subheading = f"Move {navigator.index + 1} of {len(navigator.moves)}"
    text(frame, heading, 320, 240, 132 if current else 36,
         heading=True, centered=True, vertically_centered=True)
    text(frame, subheading, 320, 330, 18, LAVENDER, centered=True)

    rounded_panel(frame, (12, 436, 628, 475), (29, 24, 28), 16)
    text(frame, f"{navigator.index + 1} / {len(navigator.moves)}" if current else "0 moves",
         30, 449, 13, MUTED)
    rounded_panel(frame, (226, 440, 414, 471), (185, 118, 115), 13)
    text(frame, "SPACE / N  ·  Next" if current else "Solved", 320, 447, 14,
         heading=True, centered=True)
    if current:
        text(frame, "B  Back", 440, 449, 12, MUTED)
        text(frame, "Q  Cancel", 548, 449, 12, MUTED)
    return frame


def _keyboard_action(key: int) -> str | None:
    if key in (ord("q"), 27):
        return "cancel"
    if key in (ord("b"), 81, 2424832):
        return "back"
    if key in (ord("n"), ord(" "), 13, 83, 2555904):
        return "next"
    return None


def show_guidance(moves: list[str]) -> str:
    """Show moves until the user completes or cancels guidance."""
    navigator = MoveNavigator(tuple(moves))
    pending_action: str | None = None

    def clicked(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        nonlocal pending_action
        if event != cv2.EVENT_LBUTTONUP or not 440 <= y <= 475:
            return
        if 226 <= x <= 414:
            pending_action = "next"
        elif 430 <= x <= 510:
            pending_action = "back"
        elif 540 <= x <= 632:
            pending_action = "cancel"

    if navigator.current is None:
        cv2.imshow("Rubik's Cube Solution", draw_guidance(navigator))
        cv2.waitKey(500)
        cv2.destroyWindow("Rubik's Cube Solution")
        return "COMPLETE"

    try:
        while True:
            cv2.imshow("Rubik's Cube Solution", draw_guidance(navigator))
            try:
                cv2.setMouseCallback("Rubik's Cube Solution", clicked)
            except cv2.error:
                # Headless regression runs replace imshow and have no native window.
                pass
            key = cv2.waitKeyEx(50)
            action = _keyboard_action(key) or pending_action
            pending_action = None
            if action == "cancel":
                return "CANCELLED"
            if action == "back":
                navigator.back()
            elif action == "next":
                if navigator.next():
                    return "COMPLETE"
    finally:
        cv2.destroyWindow("Rubik's Cube Solution")
