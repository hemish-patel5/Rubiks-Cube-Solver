"""Guided webcam scanner for all 54 stickers on a 3x3 Rubik's Cube.

The scanner supports an ordinary USB webcam through OpenCV and a Raspberry Pi
camera through Picamera2.  Each face is sampled from a fixed 3x3 guide.  The six
centre stickers are used as per-session colour references, which is substantially
more reliable than fixed HSV thresholds under different lighting.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

if __package__:
    from .qt_runtime import configure_opencv_display
else:
    from qt_runtime import configure_opencv_display

configure_opencv_display()

import cv2
import numpy as np


@dataclass(frozen=True)
class SampleResult:
    row: int
    column: int
    bgr: tuple[int, int, int]
    hsv: tuple[int, int, int]


@dataclass(frozen=True)
class FaceDefinition:
    notation: str
    colour: str
    orientation: str


@dataclass(frozen=True)
class ScanOutcome:
    """Minimal trusted handoff from the scanner to the solver."""

    facelets_urfdlb: str


GRID_SIZE = 3
SAMPLE_SIZE = 24
FRAME_WIDTH = 640
FRAME_HEIGHT = 480
FACE_SIZE = 270

# Experimental two-face view. Points are top-left, top-right, bottom-right,
# bottom-left in the 640x480 camera frame. The shared edge keeps the white top
# and current side aligned like a physical cube viewed from slightly above.
ANGLED_TOP_QUAD = ((235, 95), (405, 95), (475, 235), (165, 235))
ANGLED_FRONT_QUAD = ((165, 235), (475, 235), (450, 435), (190, 435))

# Singmaster/Kociemba order.  These instructions preserve sticker orientation,
# not just face colour, so the saved facelet string can later be sent to a solver.
FACE_SEQUENCE = (
    FaceDefinition("U", "white", "blue face at the TOP"),
    FaceDefinition("R", "red", "white face at the TOP"),
    FaceDefinition("F", "green", "white face at the TOP"),
    FaceDefinition("D", "yellow", "green face at the TOP"),
    FaceDefinition("L", "orange", "white face at the TOP"),
    FaceDefinition("B", "blue", "white face at the TOP"),
)

ANGLED_SIDE_SEQUENCE = (
    FaceDefinition("F", "green", "white face visible above"),
    FaceDefinition("R", "red", "white face visible above"),
    FaceDefinition("B", "blue", "white face visible above"),
    FaceDefinition("L", "orange", "white face visible above"),
)

DISPLAY_BGR = {
    "white": (245, 245, 245),
    "red": (30, 30, 230),
    "green": (30, 180, 30),
    "yellow": (20, 230, 230),
    "orange": (0, 130, 255),
    "blue": (230, 90, 20),
    "unknown": (128, 128, 128),
}


class Camera(Protocol):
    def read(self) -> np.ndarray: ...

    def close(self) -> None: ...


class ScannerControls(Protocol):
    def poll_scanner_action(self) -> str | None: ...

    def show_status(self, status: str, detail: str = "") -> None: ...


class OpenCVCamera:
    """USB/built-in webcam accessed through OpenCV."""

    def __init__(self, device: int) -> None:
        self.capture = cv2.VideoCapture(device)
        if not self.capture.isOpened():
            raise RuntimeError(f"Could not open webcam device {device}")
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        # A small buffer avoids classifying an old frame on some USB cameras.
        self.capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    def read(self) -> np.ndarray:
        ok, frame = self.capture.read()
        if not ok or frame is None:
            raise RuntimeError("The webcam stopped returning frames")
        if frame.shape[:2] != (FRAME_HEIGHT, FRAME_WIDTH):
            frame = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
        return frame

    def close(self) -> None:
        self.capture.release()


class Picamera2Camera:
    """Raspberry Pi camera; imported lazily so desktop webcams still work."""

    def __init__(self) -> None:
        try:
            from picamera2 import Picamera2
        except ImportError as exc:
            raise RuntimeError("Picamera2 is not installed on this device") from exc

        self.camera = Picamera2()
        configuration = self.camera.create_preview_configuration(
            main={"format": "BGR888", "size": (FRAME_WIDTH, FRAME_HEIGHT)}
        )
        self.camera.configure(configuration)
        self.camera.start()
        time.sleep(2)

    def read(self) -> np.ndarray:
        return self.camera.capture_array()

    def close(self) -> None:
        self.camera.stop()
        self.camera.close()


def create_camera(backend: str = "auto", device: int = 0) -> Camera:
    """Create the requested camera, preferring a USB webcam in auto mode."""
    errors: list[str] = []
    if backend in {"auto", "opencv"}:
        try:
            return OpenCVCamera(device)
        except RuntimeError as exc:
            errors.append(str(exc))
            if backend == "opencv":
                raise
    if backend in {"auto", "picamera2"}:
        try:
            return Picamera2Camera()
        except RuntimeError as exc:
            errors.append(str(exc))
    raise RuntimeError("; ".join(errors) or f"Unknown camera backend: {backend}")


def get_grid_centres() -> list[tuple[int, int, int, int]]:
    """Return ``(row, column, centre_x, centre_y)`` for all nine cells."""
    start_x = (FRAME_WIDTH - FACE_SIZE) // 2
    start_y = (FRAME_HEIGHT - FACE_SIZE) // 2
    cell_size = FACE_SIZE // GRID_SIZE
    return [
        (
            row,
            column,
            start_x + column * cell_size + cell_size // 2,
            start_y + row * cell_size + cell_size // 2,
        )
        for row in range(GRID_SIZE)
        for column in range(GRID_SIZE)
    ]


def sample_grid(frame: np.ndarray) -> list[SampleResult]:
    """Take glare-resistant median BGR and HSV samples from all nine cells."""
    if frame.shape[:2] != (FRAME_HEIGHT, FRAME_WIDTH):
        raise ValueError(
            f"Expected a {FRAME_WIDTH}x{FRAME_HEIGHT} frame, got "
            f"{frame.shape[1]}x{frame.shape[0]}"
        )
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    results: list[SampleResult] = []
    half = SAMPLE_SIZE // 2

    for row, column, centre_x, centre_y in get_grid_centres():
        bgr_region = frame[
            centre_y - half : centre_y + half,
            centre_x - half : centre_x + half,
        ]
        hsv_region = hsv_frame[
            centre_y - half : centre_y + half,
            centre_x - half : centre_x + half,
        ]
        median_bgr = np.median(
            np.asarray(bgr_region.reshape(-1, 3), dtype=np.float64), axis=0
        ).astype(int)
        median_hsv = np.median(
            np.asarray(hsv_region.reshape(-1, 3), dtype=np.float64), axis=0
        ).astype(int)
        results.append(
            SampleResult(
                row=row,
                column=column,
                bgr=(int(median_bgr[0]), int(median_bgr[1]), int(median_bgr[2])),
                hsv=(int(median_hsv[0]), int(median_hsv[1]), int(median_hsv[2])),
            )
        )
    return results


def rectify_face(
    frame: np.ndarray,
    quad: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> np.ndarray:
    """Perspective-correct one angled face into a square image."""
    source = np.asarray(quad, dtype=np.float32)
    destination = np.asarray(
        ((0, 0), (FACE_SIZE - 1, 0), (FACE_SIZE - 1, FACE_SIZE - 1),
         (0, FACE_SIZE - 1)),
        dtype=np.float32,
    )
    transform = cv2.getPerspectiveTransform(source, destination)
    return cv2.warpPerspective(frame, transform, (FACE_SIZE, FACE_SIZE))


def sample_rectified_face(face_image: np.ndarray) -> list[SampleResult]:
    """Sample a perspective-corrected FACE_SIZE square as a 3x3 face."""
    if face_image.shape[:2] != (FACE_SIZE, FACE_SIZE):
        raise ValueError(f"Expected a {FACE_SIZE}x{FACE_SIZE} rectified face")
    hsv_image = cv2.cvtColor(face_image, cv2.COLOR_BGR2HSV)
    cell_size = FACE_SIZE // GRID_SIZE
    half = SAMPLE_SIZE // 2
    results: list[SampleResult] = []
    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            centre_x = column * cell_size + cell_size // 2
            centre_y = row * cell_size + cell_size // 2
            bgr_region = face_image[
                centre_y - half : centre_y + half,
                centre_x - half : centre_x + half,
            ]
            hsv_region = hsv_image[
                centre_y - half : centre_y + half,
                centre_x - half : centre_x + half,
            ]
            median_bgr = np.median(bgr_region.reshape(-1, 3), axis=0).astype(int)
            median_hsv = np.median(hsv_region.reshape(-1, 3), axis=0).astype(int)
            results.append(SampleResult(
                row=row,
                column=column,
                bgr=tuple(int(value) for value in median_bgr),
                hsv=tuple(int(value) for value in median_hsv),
            ))
    return results


def sample_angled_face(
    frame: np.ndarray,
    quad: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
) -> tuple[list[SampleResult], np.ndarray]:
    """Return samples and a saved square image for one angled face."""
    rectified = rectify_face(frame, quad)
    return sample_rectified_face(rectified), rectified


def bgr_to_lab(bgr: tuple[int, int, int]) -> np.ndarray:
    pixel = np.array([[bgr]], dtype=np.uint8)
    return cv2.cvtColor(pixel, cv2.COLOR_BGR2LAB)[0, 0].astype(float)


def colour_reference_lab(bgr: tuple[int, int, int]) -> np.ndarray:
    """Compare colours at equal brightness while preserving channel ratios.

    A shadow can make yellow closer to orange in raw LAB distance. Scaling
    both stickers and centres to the same maximum channel removes that
    brightness difference without discarding saturation (needed for white).
    """
    channels = np.asarray(bgr, dtype=np.float64)
    brightness = float(channels.max())
    if brightness == 0:
        return bgr_to_lab(bgr)
    normalized = np.rint(channels * (255.0 / brightness)).astype(np.uint8)
    return bgr_to_lab(tuple(int(channel) for channel in normalized))


def heuristic_colour(hsv: tuple[int, int, int]) -> str:
    """Fallback live-preview classifier used before all centres are captured."""
    hue, saturation, value = hsv
    if value < 35:
        return "unknown"
    if saturation < 55:
        return "white"
    if hue < 9 or hue >= 170:
        return "red"
    if hue < 24:
        return "orange"
    if hue < 38:
        return "yellow"
    if hue < 88:
        return "green"
    if hue < 140:
        return "blue"
    return "red"


def centre_references(
    captured: dict[str, list[SampleResult]],
) -> dict[str, tuple[int, int, int]]:
    references: dict[str, tuple[int, int, int]] = {}
    for face in FACE_SEQUENCE:
        samples = captured.get(face.notation)
        if samples:
            references[face.colour] = samples[4].bgr
    return references


def classify_samples(
    samples: list[SampleResult],
    references: dict[str, tuple[int, int, int]],
) -> list[str]:
    """Classify stickers by brightness-normalized session centres in LAB."""
    if len(references) < 6:
        return [heuristic_colour(sample.hsv) for sample in samples]
    reference_lab = {
        colour: colour_reference_lab(bgr) for colour, bgr in references.items()
    }
    colours: list[str] = []
    for sample in samples:
        sample_lab = colour_reference_lab(sample.bgr)
        colours.append(
            min(
                reference_lab,
                key=lambda colour: float(
                    np.linalg.norm(sample_lab - reference_lab[colour])
                ),
            )
        )
    return colours


def classify_cube(
    captured: dict[str, list[SampleResult]],
) -> dict[str, list[str]]:
    references = centre_references(captured)
    classified: dict[str, list[str]] = {}
    for face in FACE_SEQUENCE:
        samples = captured.get(face.notation)
        if samples is None:
            continue
        colours = classify_samples(samples, references)
        # A centre defines its face by construction.  Pinning it also makes any
        # centre mismatch caused by glare explicit in the surrounding count check.
        colours[4] = face.colour
        classified[face.notation] = colours
    return classified


def colour_counts(classified: dict[str, list[str]]) -> dict[str, int]:
    counts = {face.colour: 0 for face in FACE_SEQUENCE}
    for face_colours in classified.values():
        for colour in face_colours:
            counts[colour] = counts.get(colour, 0) + 1
    return counts


def validate_cube(classified: dict[str, list[str]]) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if set(classified) != {face.notation for face in FACE_SEQUENCE}:
        problems.append("not all six faces have been captured")
    counts = colour_counts(classified)
    for face in FACE_SEQUENCE:
        count = counts.get(face.colour, 0)
        if count != 9:
            problems.append(f"{face.colour}: detected {count}, expected 9")
    return not problems, problems


def make_facelet_string(classified: dict[str, list[str]]) -> str | None:
    if len(classified) != 6:
        return None
    colour_to_face = {face.colour: face.notation for face in FACE_SEQUENCE}
    return "".join(
        colour_to_face.get(colour, "?")
        for face in FACE_SEQUENCE
        for colour in classified[face.notation]
    )


def build_state(captured: dict[str, list[SampleResult]]) -> dict[str, object]:
    classified = classify_cube(captured)
    valid, problems = validate_cube(classified)
    counts = colour_counts(classified)
    faces: dict[str, object] = {}

    for face in FACE_SEQUENCE:
        samples = captured.get(face.notation)
        if samples is None:
            continue
        colours = classified[face.notation]
        faces[face.notation] = {
            "centre_colour": face.colour,
            "orientation": face.orientation,
            "colours": [colours[row * 3 : row * 3 + 3] for row in range(3)],
            "samples": [asdict(sample) for sample in samples],
        }

    return {
        "format_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "face_order": [face.notation for face in FACE_SEQUENCE],
        "complete": len(captured) == 6,
        "colour_counts": counts,
        "colour_count_valid": valid,
        "validation_problems": problems,
        "facelets_URFDLB": make_facelet_string(classified),
        "faces": faces,
    }


def build_scan_outcome(
    captured: dict[str, list[SampleResult]],
) -> ScanOutcome | None:
    """Return a solver handoff only after all existing scan checks pass."""
    state = build_state(captured)
    facelets = state["facelets_URFDLB"]
    if not state["colour_count_valid"] or not isinstance(facelets, str):
        return None
    return ScanOutcome(facelets_urfdlb=facelets)


def save_state(captured: dict[str, list[SampleResult]], output_dir: Path) -> Path:
    """Atomically save raw samples and classified colours as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "cube_state.json"
    temporary = output_dir / "cube_state.json.tmp"
    temporary.write_text(json.dumps(build_state(captured), indent=2), encoding="utf-8")
    temporary.replace(destination)
    return destination


def draw_grid(
    frame: np.ndarray,
    preview_colours: list[str] | None = None,
) -> None:
    start_x = (FRAME_WIDTH - FACE_SIZE) // 2
    start_y = (FRAME_HEIGHT - FACE_SIZE) // 2
    cell_size = FACE_SIZE // GRID_SIZE
    cv2.rectangle(
        frame,
        (start_x, start_y),
        (start_x + FACE_SIZE, start_y + FACE_SIZE),
        (255, 255, 255),
        2,
    )
    for index in range(1, GRID_SIZE):
        x = start_x + index * cell_size
        y = start_y + index * cell_size
        cv2.line(frame, (x, start_y), (x, start_y + FACE_SIZE), (255, 255, 255), 1)
        cv2.line(frame, (start_x, y), (start_x + FACE_SIZE, y), (255, 255, 255), 1)

    for index, (row, column, centre_x, centre_y) in enumerate(get_grid_centres()):
        half = SAMPLE_SIZE // 2
        colour_name = preview_colours[index] if preview_colours else "unknown"
        draw_colour = DISPLAY_BGR.get(colour_name, DISPLAY_BGR["unknown"])
        cv2.rectangle(
            frame,
            (centre_x - half, centre_y - half),
            (centre_x + half, centre_y + half),
            draw_colour,
            3,
        )
        cv2.putText(
            frame,
            colour_name[0].upper() if preview_colours else str(row * 3 + column + 1),
            (centre_x - 7, centre_y + 6),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 0, 0) if colour_name in {"white", "yellow"} else (255, 255, 255),
            2,
            cv2.LINE_AA,
        )


def draw_perspective_grid(
    frame: np.ndarray,
    quad: tuple[tuple[int, int], tuple[int, int], tuple[int, int], tuple[int, int]],
    label: str,
    colour: tuple[int, int, int],
    preview_colours: list[str] | None = None,
) -> None:
    """Draw a labelled 3x3 guide over a perspective face quadrilateral."""
    points = np.asarray(quad, dtype=np.int32)
    cv2.polylines(frame, [points], True, colour, 2, cv2.LINE_AA)
    top_left, top_right, bottom_right, bottom_left = np.asarray(quad, dtype=float)
    for index in range(1, GRID_SIZE):
        fraction = index / GRID_SIZE
        upper = top_left + fraction * (top_right - top_left)
        lower = bottom_left + fraction * (bottom_right - bottom_left)
        left = top_left + fraction * (bottom_left - top_left)
        right = top_right + fraction * (bottom_right - top_right)
        cv2.line(frame, tuple(upper.astype(int)), tuple(lower.astype(int)), colour, 1,
                 cv2.LINE_AA)
        cv2.line(frame, tuple(left.astype(int)), tuple(right.astype(int)), colour, 1,
                 cv2.LINE_AA)
    if preview_colours is None:
        centre = points.mean(axis=0).astype(int)
        cv2.putText(frame, label, (int(centre[0]) - 12, int(centre[1]) + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2, cv2.LINE_AA)
        return

    destination_centres = np.asarray([[
        ((column + 0.5) * FACE_SIZE / GRID_SIZE,
         (row + 0.5) * FACE_SIZE / GRID_SIZE)
        for row in range(GRID_SIZE) for column in range(GRID_SIZE)
    ]], dtype=np.float32)
    destination_corners = np.asarray(
        ((0, 0), (FACE_SIZE - 1, 0), (FACE_SIZE - 1, FACE_SIZE - 1),
         (0, FACE_SIZE - 1)), dtype=np.float32,
    )
    inverse = cv2.getPerspectiveTransform(
        destination_corners, np.asarray(quad, dtype=np.float32)
    )
    camera_centres = cv2.perspectiveTransform(destination_centres, inverse)[0]
    for centre, colour_name in zip(camera_centres, preview_colours):
        x, y = (int(value) for value in centre)
        draw_colour = DISPLAY_BGR.get(colour_name, DISPLAY_BGR["unknown"])
        cv2.circle(frame, (x, y), 12, draw_colour, 3, cv2.LINE_AA)
        cv2.putText(
            frame, colour_name[0].upper(), (x - 6, y + 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5,
            (0, 0, 0) if colour_name in {"white", "yellow"} else (255, 255, 255),
            2, cv2.LINE_AA,
        )


def draw_angled_status(
    frame: np.ndarray,
    stage_index: int,
    captured: dict[str, list[SampleResult]],
    message: str,
) -> None:
    side = ANGLED_SIDE_SEQUENCE[stage_index]
    cv2.rectangle(frame, (0, 0), (FRAME_WIDTH, 72), (0, 0, 0), -1)
    heading = (
        f"Angled {stage_index + 1}/4: {side.colour.upper()} front, WHITE top"
    )
    cv2.putText(frame, heading, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, message, (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (100, 230, 255), 1, cv2.LINE_AA)
    footer = (
        f"Saved: {' '.join(captured) or '-'} | SPACE capture | B back | "
        "R reset | Q quit"
    )
    cv2.rectangle(frame, (0, FRAME_HEIGHT - 34), (FRAME_WIDTH, FRAME_HEIGHT),
                  (0, 0, 0), -1)
    cv2.putText(frame, footer, (10, FRAME_HEIGHT - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1,
                cv2.LINE_AA)


def draw_status(
    frame: np.ndarray,
    face_index: int,
    captured: dict[str, list[SampleResult]],
    message: str,
) -> None:
    complete = face_index >= len(FACE_SEQUENCE)
    if complete:
        heading = "All 6 faces captured - press B to rescan the last face"
    else:
        face = FACE_SEQUENCE[face_index]
        heading = (
            f"Face {face_index + 1}/6: {face.notation} ({face.colour.upper()}) - "
            f"{face.orientation}"
        )
    cv2.rectangle(frame, (0, 0), (FRAME_WIDTH, 68), (0, 0, 0), -1)
    cv2.putText(frame, heading, (12, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(frame, message, (12, 54), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                (100, 230, 255), 1, cv2.LINE_AA)
    footer = f"Captured: {' '.join(captured) or '-'} | SPACE capture | B back | R reset | Q quit"
    cv2.rectangle(frame, (0, FRAME_HEIGHT - 34), (FRAME_WIDTH, FRAME_HEIGHT), (0, 0, 0), -1)
    cv2.putText(frame, footer, (10, FRAME_HEIGHT - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.45, (255, 255, 255), 1, cv2.LINE_AA)


def run_scanner(
    camera: Camera,
    output_dir: Path,
    validate_outcome: Callable[[ScanOutcome], None] | None = None,
    exit_on_valid: bool = False,
    controls: ScannerControls | None = None,
) -> ScanOutcome | None:
    captured: dict[str, list[SampleResult]] = {}
    face_index = 0
    message = "Fill the grid with the cube face, then press SPACE"
    last_preview = 0.0
    preview_colours: list[str] | None = None

    if controls is not None:
        controls.show_status("scanning", FACE_SEQUENCE[0].notation)

    try:
        while True:
            frame = camera.read()
            now = time.monotonic()
            if now - last_preview >= 0.15:
                live_samples = sample_grid(frame)
                preview_colours = classify_samples(
                    live_samples, centre_references(captured)
                )
                last_preview = now

            display_frame = frame.copy()
            draw_grid(display_frame, preview_colours)
            draw_status(display_frame, face_index, captured, message)
            cv2.imshow("Rubik's Cube 3x3 Scanner", display_frame)
            key = cv2.waitKey(1) & 0xFF
            joystick_action = (
                controls.poll_scanner_action() if controls is not None else None
            )

            if key == ord("q") or joystick_action == "cancel":
                return None
            if key == ord("r") or joystick_action == "reset":
                captured.clear()
                face_index = 0
                message = "Scan reset"
                if controls is not None:
                    controls.show_status("scanning", FACE_SEQUENCE[0].notation)
            elif key == ord("b") or joystick_action == "back":
                if face_index > 0:
                    face_index -= 1
                    removed = FACE_SEQUENCE[face_index].notation
                    captured.pop(removed, None)
                    # Later faces no longer belong to a continuous guided scan.
                    for later in FACE_SEQUENCE[face_index + 1 :]:
                        captured.pop(later.notation, None)
                    message = f"Rescan face {removed}"
                    save_state(captured, output_dir)
                    if controls is not None:
                        controls.show_status("scanning", removed)
            elif (
                key == ord(" ") or joystick_action == "capture"
            ) and face_index < len(FACE_SEQUENCE):
                face = FACE_SEQUENCE[face_index]
                samples = sample_grid(frame)
                captured[face.notation] = samples
                output_dir.mkdir(parents=True, exist_ok=True)
                image_path = output_dir / f"face_{face.notation}.jpg"
                cv2.imwrite(str(image_path), frame)
                state_path = save_state(captured, output_dir)
                face_index += 1
                if controls is not None:
                    controls.show_status("accepted", face.notation)

                if face_index == len(FACE_SEQUENCE):
                    state = build_state(captured)
                    outcome = build_scan_outcome(captured)
                    if outcome is not None:
                        try:
                            if validate_outcome is not None:
                                if controls is not None:
                                    controls.show_status("calculating")
                                validate_outcome(outcome)
                        except ValueError as exc:
                            message = f"Invalid cube: {exc}. Press B to rescan"
                            if controls is not None:
                                controls.show_status("error")
                        else:
                            message = f"Complete and valid - saved to {state_path}"
                            print(json.dumps(state, indent=2))
                            if controls is not None:
                                controls.show_status("complete")
                            if exit_on_valid:
                                return outcome
                    else:
                        problems = state["validation_problems"]
                        message = "Check/rescan: " + "; ".join(problems)  # type: ignore[arg-type]
                        if controls is not None:
                            controls.show_status("error")
                        print(json.dumps(state, indent=2))
                else:
                    message = f"Saved {face.notation}; rotate to the next instructed face"
    finally:
        camera.close()
        cv2.destroyAllWindows()


def run_angled_scanner(
    camera: Camera,
    output_dir: Path,
    controls: ScannerControls | None = None,
) -> dict[str, list[SampleResult]] | None:
    """Capture U+F, then R, B, L from four above-cube camera views.

    This is an experimental capture-only workflow. D is intentionally absent,
    so the resulting state is not handed to the solver.
    """
    captured: dict[str, list[SampleResult]] = {}
    stage_index = 0
    message = "Align both faces with the guides, then press SPACE"
    last_preview = 0.0
    side_preview: list[str] | None = None
    top_preview: list[str] | None = None
    if controls is not None:
        controls.show_status("scanning", "F+U")

    try:
        while True:
            frame = camera.read()
            now = time.monotonic()
            if now - last_preview >= 0.15:
                live_side, _ = sample_angled_face(frame, ANGLED_FRONT_QUAD)
                live_top, _ = sample_angled_face(frame, ANGLED_TOP_QUAD)
                references = centre_references(captured)
                side_preview = classify_samples(live_side, references)
                top_preview = classify_samples(live_top, references)
                last_preview = now
            display_frame = frame.copy()
            draw_perspective_grid(
                display_frame, ANGLED_TOP_QUAD, "U", DISPLAY_BGR["white"],
                top_preview,
            )
            side = ANGLED_SIDE_SEQUENCE[stage_index]
            draw_perspective_grid(
                display_frame, ANGLED_FRONT_QUAD, side.notation,
                DISPLAY_BGR[side.colour], side_preview,
            )
            draw_angled_status(display_frame, stage_index, captured, message)
            cv2.imshow("Rubik's Cube Angled Scanner", display_frame)
            key = cv2.waitKey(1) & 0xFF
            joystick_action = (
                controls.poll_scanner_action() if controls is not None else None
            )

            if key == ord("q") or joystick_action == "cancel":
                return None
            if key == ord("r") or joystick_action == "reset":
                captured.clear()
                stage_index = 0
                message = "Scan reset; align GREEN front and WHITE top"
                if controls is not None:
                    controls.show_status("scanning", "F+U")
            elif key == ord("b") or joystick_action == "back":
                if stage_index > 0:
                    stage_index -= 1
                    removed = ANGLED_SIDE_SEQUENCE[stage_index]
                    captured.pop(removed.notation, None)
                    for later in ANGLED_SIDE_SEQUENCE[stage_index + 1 :]:
                        captured.pop(later.notation, None)
                    if stage_index == 0:
                        captured.pop("U", None)
                    save_state(captured, output_dir)
                    message = f"Rescan {removed.colour.upper()} front"
                    if controls is not None:
                        controls.show_status("scanning", removed.notation)
            elif key == ord(" ") or joystick_action == "capture":
                side_samples, side_image = sample_angled_face(
                    frame, ANGLED_FRONT_QUAD
                )
                captured[side.notation] = side_samples
                output_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(output_dir / f"face_{side.notation}.jpg"), side_image)

                if stage_index == 0:
                    top_samples, top_image = sample_angled_face(
                        frame, ANGLED_TOP_QUAD
                    )
                    captured["U"] = top_samples
                    cv2.imwrite(str(output_dir / "face_U.jpg"), top_image)

                cv2.imwrite(
                    str(output_dir / f"capture_{stage_index + 1}_{side.colour}.jpg"),
                    frame,
                )
                state_path = save_state(captured, output_dir)
                stage_index += 1
                if controls is not None:
                    controls.show_status("accepted", side.notation)

                if stage_index == len(ANGLED_SIDE_SEQUENCE):
                    state = build_state(captured)
                    print(json.dumps(state, indent=2))
                    print(
                        "Angled capture complete: U, F, R, B, L saved; "
                        "D is intentionally not scanned."
                    )
                    print(f"Saved state: {state_path}")
                    if controls is not None:
                        controls.show_status("complete")
                    return captured

                next_side = ANGLED_SIDE_SEQUENCE[stage_index]
                message = (
                    f"Saved {side.notation}; rotate cube to "
                    f"{next_side.colour.upper()} front, keep WHITE top"
                )
                if controls is not None:
                    controls.show_status("scanning", next_side.notation)
    finally:
        camera.close()
        cv2.destroyAllWindows()


def scan_cube(
    camera: Camera,
    output_dir: Path,
    validate_outcome: Callable[[ScanOutcome], None],
    controls: ScannerControls | None = None,
) -> ScanOutcome | None:
    """Scan until a valid cube is accepted or the user cancels."""
    return run_scanner(
        camera,
        output_dir,
        validate_outcome=validate_outcome,
        exit_on_valid=True,
        controls=controls,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("head-on", "angled-sides"),
        default="head-on",
        help=(
            "head-on scans all six faces; angled-sides captures U+F, then R, B, "
            "L and intentionally leaves D missing"
        ),
    )
    parser.add_argument(
        "--backend",
        choices=("auto", "opencv", "picamera2"),
        default="auto",
        help="camera API (default: try OpenCV webcam, then Picamera2)",
    )
    parser.add_argument(
        "--device", type=int, default=0, help="OpenCV webcam device number"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("scan_output"),
        help="directory for cube_state.json and six face images",
    )
    return parser.parse_args()


def main() -> None:
    if str(Path(__file__).parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).parents[1]))
    from hardware.sense_hat_adapter import SenseHatAdapter

    args = parse_args()
    controls = SenseHatAdapter()
    controls.show_status("ready")
    try:
        camera = create_camera(args.backend, args.device)
    except RuntimeError as exc:
        controls.show_status("error")
        raise SystemExit(f"Camera error: {exc}") from exc
    if args.mode == "angled-sides":
        run_angled_scanner(camera, args.output, controls=controls)
    else:
        run_scanner(camera, args.output, controls=controls)


if __name__ == "__main__":
    main()
