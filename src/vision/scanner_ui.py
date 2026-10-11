"""Camera overlay styling; never applied to the frames used for colour sampling."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT_DIR = Path(__file__).with_name("fonts")
WHITE = (250, 247, 246)
MUTED = (208, 196, 194)
LAVENDER = (255, 190, 182)
_clicked_keys: dict[str, int] = {}


@lru_cache(maxsize=32)
def _font(size: int, heading: bool) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(
        str(FONT_DIR / ("Inter.ttf" if heading else "Krub-Regular.ttf")), size
    )
    if heading:
        font.set_variation_by_axes([24, 600])
    return font


@lru_cache(maxsize=256)
def _text_tile(text: str, size: int, heading: bool) -> tuple[np.ndarray, np.ndarray]:
    font = _font(size, heading)
    left, top, right, bottom = font.getbbox(text)
    mask = Image.new("L", (max(1, right - left + 2), max(1, bottom - top + 2)))
    ImageDraw.Draw(mask).text((1 - left, 1 - top), text, font=font, fill=255)
    alpha = np.asarray(mask, dtype=np.float32)[:, :, None] / 255
    return alpha, np.array(alpha.shape[:2])


@lru_cache(maxsize=128)
def _wrap(value: str, width: int, size: int = 11) -> list[str]:
    """Keep longer validation messages and paths readable inside the hint card."""
    lines: list[str] = []
    line = ""
    font = _font(size, False)
    for character in value:
        if character == "\n" or font.getlength(line + character) > width:
            # Prefer a word boundary; split long paths when one is unavailable.
            split = line.rfind(" ")
            if character != "\n" and split > 0:
                lines.append(line[:split])
                line = line[split + 1:] + character
            else:
                lines.append(line)
                line = "" if character == "\n" else character
        else:
            line += character
    if line:
        lines.append(line)
    return lines or [""]


def text(
    frame: np.ndarray, value: str, x: int, y: int, size: int = 14,
    colour: tuple[int, int, int] = WHITE, *, heading: bool = False,
    centered: bool = False, vertically_centered: bool = False,
    max_width: int | None = None,
) -> None:
    """Draw cached TrueType glyphs directly into a BGR frame."""
    if max_width is not None:
        while size > 10 and _font(size, heading).getlength(value) > max_width:
            size -= 1
    alpha, dimensions = _text_tile(value, size, heading)
    height, width = (int(v) for v in dimensions)
    if centered:
        x -= width // 2
    if vertically_centered:
        y -= height // 2
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + width, frame.shape[1]), min(y + height, frame.shape[0])
    if x1 <= x0 or y1 <= y0:
        return
    alpha = alpha[y0 - y:y1 - y, x0 - x:x1 - x]
    region = frame[y0:y1, x0:x1]
    region[:] = region * (1 - alpha) + np.asarray(colour) * alpha


def rounded_panel(
    frame: np.ndarray, bounds: tuple[int, int, int, int],
    colour: tuple[int, int, int], radius: int = 12, opacity: float = 1,
) -> None:
    x0, y0, x1, y1 = bounds
    roi = frame[y0:y1, x0:x1]
    height, width = roi.shape[:2]
    layer = roi.copy()
    radius = min(radius, height // 2, width // 2)
    cv2.rectangle(layer, (radius, 0), (width - radius - 1, height - 1), colour, -1)
    cv2.rectangle(layer, (0, radius), (width - 1, height - radius - 1), colour, -1)
    for x in (radius, width - radius - 1):
        for y in (radius, height - radius - 1):
            cv2.circle(layer, (x, y), radius, colour, -1, cv2.LINE_AA)
    cv2.addWeighted(layer, opacity, roi, 1 - opacity, 0, dst=roi)


def draw_scanner_chrome(
    frame: np.ndarray, orientation: str, message: str, captured: dict,
    step: int, total: int, *, automatic: bool = False,
) -> None:
    width, height = frame.shape[1], frame.shape[0]
    # Fade over the live view instead of replacing it with a black header.
    top = frame[:36]
    fade = np.linspace(0.72, 0.1, 36)[:, None, None]
    top[:] = top * (1 - fade) + np.asarray((26, 20, 23)) * fade
    text(frame, "Scan Cube", width // 2, 9, 20, heading=True, centered=True)

    # Keep the card below the camera's top letterbox and above the guide at y=100.
    message_lines = _wrap(message, width - 210, 10)
    rounded_panel(frame, (80, 64, width - 80, 96 + 13 * (len(message_lines) - 1)),
                  (55, 33, 40), 8, 0.92)
    # Tiny scan corners echo the instruction badge in the reference.
    for x, y, dx, dy in ((94, 72, 1, 1), (108, 72, -1, 1),
                          (94, 86, 1, -1), (108, 86, -1, -1)):
        cv2.line(frame, (x, y), (x + dx * 4, y), LAVENDER, 1, cv2.LINE_AA)
        cv2.line(frame, (x, y), (x, y + dy * 4), LAVENDER, 1, cv2.LINE_AA)
    text(frame, orientation, 119, 67, 12, heading=True, max_width=width - 210)
    for index, line in enumerate(message_lines):
        text(frame, line, 119, 82 + index * 13, 10, MUTED)

    rounded_panel(frame, (12, height - 44, width - 12, height - 5), (29, 24, 28), 16, 0.94)
    # Six actual face indicators include the inferred / fallback bottom face.
    face_colours = {"U": (245, 245, 245), "R": (30, 30, 230), "F": (30, 180, 30),
                    "D": (20, 230, 230), "L": (0, 130, 255), "B": (230, 90, 20)}
    for index, face in enumerate("URFDLB"):
        cv2.circle(frame, (30 + index * 17, height - 25), 5,
                   face_colours[face] if face in captured else (92, 81, 84), -1, cv2.LINE_AA)
    text(frame, f"{min(step, total)}/{total}", 145, height - 32, 13, MUTED)
    rounded_panel(frame, (226, height - 40, 414, height - 9), (185, 118, 115), 13)
    text(frame, "Auto scanning" if automatic else "SPACE  ·  Capture", 320,
         height - 33, 14, heading=True, centered=True)
    text(frame, "B  Back", 440, height - 31, 12, MUTED)
    text(frame, "Q  Quit", width - 79, height - 31, 12, MUTED)


def scanner_key(window: str) -> int:
    """Let the visible controls dispatch the same keys as the keyboard."""
    def clicked(event: int, x: int, y: int, flags: int, userdata: object) -> None:
        if event != cv2.EVENT_LBUTTONUP:
            return
        if 430 <= x <= 510 and 440 <= y <= 475:
            _clicked_keys[window] = ord("b")
        elif 226 <= x <= 414 and 440 <= y <= 475:
            _clicked_keys[window] = ord(" ")
        elif 550 <= x <= 632 and 440 <= y <= 475:
            _clicked_keys[window] = ord("q")

    try:
        cv2.setMouseCallback(window, clicked)
    except cv2.error:
        # Headless regression runs replace imshow and have no native window.
        pass
    keyboard = cv2.waitKey(1) & 0xFF
    click = _clicked_keys.pop(window, None)
    return keyboard if keyboard != 255 else click if click is not None else 255
