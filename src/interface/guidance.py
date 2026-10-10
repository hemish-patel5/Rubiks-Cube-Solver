"""Simple OpenCV move guidance with keyboard navigation."""

from __future__ import annotations

from dataclasses import dataclass

from vision.qt_runtime import configure_opencv_display

configure_opencv_display()

import cv2
import numpy as np


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
    current = navigator.current
    if current is None:
        heading = "Cube already solved"
        subheading = "0 moves"
    else:
        heading = current
        subheading = f"Move {navigator.index + 1} of {len(navigator.moves)}"
    cv2.putText(
        frame, heading, (90, 220), cv2.FONT_HERSHEY_SIMPLEX, 2.2,
        (255, 255, 255), 4, cv2.LINE_AA,
    )
    cv2.putText(
        frame, subheading, (185, 285), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
        (100, 230, 255), 2, cv2.LINE_AA,
    )
    cv2.putText(
        frame, "SPACE/N next | B back | Q cancel", (120, 430),
        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (190, 190, 190), 1, cv2.LINE_AA,
    )
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
    if navigator.current is None:
        cv2.imshow("Rubik's Cube Solution", draw_guidance(navigator))
        cv2.waitKey(500)
        cv2.destroyWindow("Rubik's Cube Solution")
        return "COMPLETE"

    try:
        while True:
            cv2.imshow("Rubik's Cube Solution", draw_guidance(navigator))
            key = cv2.waitKeyEx(50)
            action = _keyboard_action(key)
            if action == "cancel":
                return "CANCELLED"
            if action == "back":
                navigator.back()
            elif action == "next":
                if navigator.next():
                    return "COMPLETE"
    finally:
        cv2.destroyWindow("Rubik's Cube Solution")
