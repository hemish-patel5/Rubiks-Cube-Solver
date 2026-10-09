"""Guided webcam scanner for all 54 stickers on a 3x3 Rubik's Cube.

The scanner supports an ordinary USB webcam through OpenCV and a Raspberry Pi
camera through Picamera2. Faces are sampled from fixed perspective or head-on
3x3 guides. Visible centre stickers provide per-session colour references; the
hidden yellow class uses hue until a fallback yellow scan is requested.
"""

from __future__ import annotations

import argparse
import itertools
import json
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

# Two-face guide fitted to the 640x480 webcam captures. Points are top-left,
# top-right, bottom-right, bottom-left. Both faces share the cube's horizontal
# edge so the guide follows the visible sticker boundaries in the angled view.
ANGLED_TOP_QUAD = ((197, 100), (430, 100), (453, 238), (167, 238))
ANGLED_FRONT_QUAD = ((167, 238), (453, 238), (434, 428), (200, 428))

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


class RotatingPlatform(Protocol):
    def rotate_next_quarter(self) -> int: ...

    def return_home(self) -> int: ...

    def close(self) -> None: ...


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
    angled_five_centre_mode = len(references) == 5 and "yellow" not in references
    if len(references) < 6 and not angled_five_centre_mode:
        return [heuristic_colour(sample.hsv) for sample in samples]
    reference_lab = {
        colour: colour_reference_lab(bgr) for colour, bgr in references.items()
    }
    colours: list[str] = []
    for sample in samples:
        # Angled scanning never sees the yellow centre. Yellow remains reliably
        # separable by hue, while the other five colours use session centres.
        if "yellow" not in references and heuristic_colour(sample.hsv) == "yellow":
            colours.append("yellow")
            continue
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
    infer_bottom: bool = False,
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
    if infer_bottom and set(classified) == {"U", "R", "F", "L", "B"}:
        classified["D"] = infer_bottom_face(classified)
    return classified


def infer_bottom_face(classified: dict[str, list[str]]) -> list[str]:
    """Return D only when the five visible faces have one physical completion."""
    required = {"U", "R", "F", "L", "B"}
    if set(classified) != required:
        raise ValueError("bottom inference requires exactly U, R, F, L, and B")
    if any(len(classified[face]) != 9 for face in required):
        raise ValueError("bottom inference requires nine stickers on every visible face")

    white, red, green, yellow, orange, blue = (
        "white", "red", "green", "yellow", "orange", "blue"
    )
    u, r, f, left, b = (
        classified["U"], classified["R"], classified["F"],
        classified["L"], classified["B"],
    )
    all_edges = [frozenset(pair) for pair in (
        (white, red), (white, green), (white, orange), (white, blue),
        (yellow, red), (yellow, green), (yellow, orange), (yellow, blue),
        (green, red), (green, orange), (blue, orange), (blue, red),
    )]
    visible_edges = (
        (u[5], r[1]), (u[7], f[1]), (u[3], left[1]), (u[1], b[1]),
        (f[5], r[3]), (f[3], left[5]), (b[5], left[3]), (b[3], r[5]),
    )
    remaining_edges = all_edges.copy()
    try:
        for colours in visible_edges:
            remaining_edges.remove(frozenset(colours))
    except ValueError as exc:
        raise ValueError("visible stickers contain a duplicate or invalid edge cubie") from exc

    # D2, D6, D8, D4 are adjacent to F8, R8, B8, L8 respectively.
    edge_observations = (f[7], r[7], b[7], left[7])
    edge_completions: list[tuple[str, ...]] = []
    for assignment in itertools.permutations(remaining_edges):
        if all(observed in cubie for observed, cubie in zip(edge_observations, assignment)):
            edge_completions.append(tuple(
                next(iter(cubie - {observed}))
                for observed, cubie in zip(edge_observations, assignment)
            ))

    all_corners = [frozenset(triple) for triple in (
        (white, red, green), (white, green, orange),
        (white, orange, blue), (white, blue, red),
        (yellow, green, red), (yellow, orange, green),
        (yellow, blue, orange), (yellow, red, blue),
    )]
    visible_corners = (
        (u[8], r[0], f[2]), (u[6], f[0], left[2]),
        (u[0], left[0], b[2]), (u[2], b[0], r[2]),
    )
    remaining_corners = all_corners.copy()
    try:
        for colours in visible_corners:
            remaining_corners.remove(frozenset(colours))
    except ValueError as exc:
        raise ValueError("visible stickers contain a duplicate or invalid corner cubie") from exc

    # D1, D3, D7, D9 expose two stickers on L/F, F/R, B/L, R/B.
    corner_observations = (
        (left[8], f[6]), (f[8], r[6]), (b[8], left[6]), (r[8], b[6]),
    )
    corner_completions: list[tuple[str, ...]] = []
    for assignment in itertools.permutations(remaining_corners):
        if all(
            len(set(observed)) == 2 and set(observed) < cubie
            for observed, cubie in zip(corner_observations, assignment)
        ):
            corner_completions.append(tuple(
                next(iter(cubie - set(observed)))
                for observed, cubie in zip(corner_observations, assignment)
            ))

    if not edge_completions or not corner_completions:
        raise ValueError("visible stickers cannot form the missing bottom cubies")

    try:
        from kociemba.pykociemba.tools import verify
    except ImportError as exc:
        raise RuntimeError("Kociemba is required for bottom-face inference") from exc

    physical_completions: set[tuple[str, ...]] = set()
    for edges in edge_completions:
        for corners in corner_completions:
            bottom = (
                corners[0], edges[0], corners[1], edges[3], yellow,
                edges[1], corners[2], edges[2], corners[3],
            )
            candidate = dict(classified)
            candidate["D"] = list(bottom)
            facelets = make_facelet_string(candidate)
            if facelets is not None and verify(facelets) == 0:
                physical_completions.add(bottom)

    if not physical_completions:
        raise ValueError("visible stickers have no physically valid bottom face")
    if len(physical_completions) > 1:
        raise ValueError(
            f"bottom face is ambiguous ({len(physical_completions)} physical completions); "
            "scan yellow to continue"
        )
    return list(physical_completions.pop())


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


def build_state(
    captured: dict[str, list[SampleResult]],
    infer_bottom: bool = False,
) -> dict[str, object]:
    inference_problem: str | None = None
    try:
        classified = classify_cube(captured, infer_bottom=infer_bottom)
    except ValueError as exc:
        classified = classify_cube(captured)
        inference_problem = str(exc)
    valid, problems = validate_cube(classified)
    if inference_problem is not None:
        problems.insert(0, inference_problem)
    counts = colour_counts(classified)
    faces: dict[str, object] = {}

    for face in FACE_SEQUENCE:
        samples = captured.get(face.notation)
        if samples is None and face.notation not in classified:
            continue
        colours = classified[face.notation]
        faces[face.notation] = {
            "centre_colour": face.colour,
            "orientation": face.orientation,
            "colours": [colours[row * 3 : row * 3 + 3] for row in range(3)],
            "samples": [asdict(sample) for sample in samples] if samples else [],
            "inferred": samples is None,
        }

    return {
        "format_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "face_order": [face.notation for face in FACE_SEQUENCE],
        "complete": len(classified) == 6,
        "captured_faces": list(captured),
        "inferred_faces": [face for face in classified if face not in captured],
        "colour_counts": counts,
        "colour_count_valid": valid,
        "validation_problems": problems,
        "facelets_URFDLB": make_facelet_string(classified),
        "faces": faces,
    }


def build_scan_outcome(
    captured: dict[str, list[SampleResult]],
    infer_bottom: bool = False,
) -> ScanOutcome | None:
    """Return a solver handoff only after all existing scan checks pass."""
    state = build_state(captured, infer_bottom=infer_bottom)
    facelets = state["facelets_URFDLB"]
    if not state["colour_count_valid"] or not isinstance(facelets, str):
        return None
    return ScanOutcome(facelets_urfdlb=facelets)


def save_state(
    captured: dict[str, list[SampleResult]],
    output_dir: Path,
    infer_bottom: bool = False,
) -> Path:
    """Atomically save raw samples and classified colours as JSON."""
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "cube_state.json"
    temporary = output_dir / "cube_state.json.tmp"
    temporary.write_text(
        json.dumps(build_state(captured, infer_bottom=infer_bottom), indent=2),
        encoding="utf-8",
    )
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
    motorized: bool = False,
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
    if motorized and captured:
        footer = f"Saved: {' '.join(captured)} | AUTO capture | R restart | Q quit"
    elif motorized:
        footer = "Align GREEN + WHITE | SPACE start | R reset | Q quit"
    else:
        footer = (
            f"Saved: {' '.join(captured) or '-'} | SPACE capture | B back | "
            "R reset | Q quit"
        )
    cv2.rectangle(frame, (0, FRAME_HEIGHT - 34), (FRAME_WIDTH, FRAME_HEIGHT),
                  (0, 0, 0), -1)
    cv2.putText(frame, footer, (10, FRAME_HEIGHT - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.43, (255, 255, 255), 1,
                cv2.LINE_AA)


def draw_bottom_status(
    frame: np.ndarray,
    captured: dict[str, list[SampleResult]],
    message: str,
) -> None:
    cv2.rectangle(frame, (0, 0), (FRAME_WIDTH, 72), (0, 0, 0), -1)
    cv2.putText(
        frame, "Fallback: YELLOW face toward camera, GREEN edge at TOP",
        (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (255, 255, 255), 2,
        cv2.LINE_AA,
    )
    cv2.putText(frame, message, (12, 56), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                (100, 230, 255), 1, cv2.LINE_AA)
    footer = (
        f"Saved: {' '.join(captured) or '-'} | SPACE capture D | B rescan ORANGE | "
        "R reset | Q quit"
    )
    cv2.rectangle(frame, (0, FRAME_HEIGHT - 34), (FRAME_WIDTH, FRAME_HEIGHT),
                  (0, 0, 0), -1)
    cv2.putText(frame, footer, (10, FRAME_HEIGHT - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1,
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
) -> ScanOutcome | None:
    captured: dict[str, list[SampleResult]] = {}
    face_index = 0
    message = "Fill the grid with the cube face, then press SPACE"
    last_preview = 0.0
    preview_colours: list[str] | None = None

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

            if key == ord("q"):
                return None
            if key == ord("r"):
                captured.clear()
                face_index = 0
                message = "Scan reset"
            elif key == ord("b"):
                if face_index > 0:
                    face_index -= 1
                    removed = FACE_SEQUENCE[face_index].notation
                    captured.pop(removed, None)
                    # Later faces no longer belong to a continuous guided scan.
                    for later in FACE_SEQUENCE[face_index + 1 :]:
                        captured.pop(later.notation, None)
                    message = f"Rescan face {removed}"
                    save_state(captured, output_dir)
            elif key == ord(" ") and face_index < len(FACE_SEQUENCE):
                face = FACE_SEQUENCE[face_index]
                samples = sample_grid(frame)
                captured[face.notation] = samples
                output_dir.mkdir(parents=True, exist_ok=True)
                image_path = output_dir / f"face_{face.notation}.jpg"
                cv2.imwrite(str(image_path), frame)
                state_path = save_state(captured, output_dir)
                face_index += 1

                if face_index == len(FACE_SEQUENCE):
                    state = build_state(captured)
                    outcome = build_scan_outcome(captured)
                    if outcome is not None:
                        try:
                            if validate_outcome is not None:
                                validate_outcome(outcome)
                        except ValueError as exc:
                            message = f"Invalid cube: {exc}. Press B to rescan"
                        else:
                            message = f"Complete and valid - saved to {state_path}"
                            print(json.dumps(state, indent=2))
                            if exit_on_valid:
                                return outcome
                    else:
                        problems = state["validation_problems"]
                        message = "Check/rescan: " + "; ".join(problems)  # type: ignore[arg-type]
                        print(json.dumps(state, indent=2))
                else:
                    message = f"Saved {face.notation}; rotate to the next instructed face"
    finally:
        camera.close()
        cv2.destroyAllWindows()


def run_angled_scanner(
    camera: Camera,
    output_dir: Path,
    validate_outcome: Callable[[ScanOutcome], None] | None = None,
    exit_on_valid: bool = True,
) -> ScanOutcome | None:
    """Capture four angled views, inferring D or requesting a fallback scan."""
    captured: dict[str, list[SampleResult]] = {}
    stage_index = 0
    bottom_required = False
    message = "Align both faces with the guides, then press SPACE"
    last_preview = 0.0
    side_preview: list[str] | None = None
    top_preview: list[str] | None = None
    try:
        while True:
            frame = camera.read()
            now = time.monotonic()
            display_frame = frame.copy()
            references = centre_references(captured)
            if bottom_required:
                if now - last_preview >= 0.15:
                    side_preview = classify_samples(sample_grid(frame), references)
                    last_preview = now
                draw_grid(display_frame, side_preview)
                draw_bottom_status(display_frame, captured, message)
            else:
                if now - last_preview >= 0.15:
                    live_side, _ = sample_angled_face(frame, ANGLED_FRONT_QUAD)
                    live_top, _ = sample_angled_face(frame, ANGLED_TOP_QUAD)
                    side_preview = classify_samples(live_side, references)
                    top_preview = classify_samples(live_top, references)
                    last_preview = now
                side = ANGLED_SIDE_SEQUENCE[stage_index]
                draw_perspective_grid(
                    display_frame, ANGLED_TOP_QUAD, "U", DISPLAY_BGR["white"],
                    top_preview,
                )
                draw_perspective_grid(
                    display_frame, ANGLED_FRONT_QUAD, side.notation,
                    DISPLAY_BGR[side.colour], side_preview,
                )
                draw_angled_status(display_frame, stage_index, captured, message)
            cv2.imshow("Rubik's Cube Angled Scanner", display_frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                return None
            if key == ord("r"):
                captured.clear()
                stage_index = 0
                bottom_required = False
                message = "Scan reset; align GREEN front and WHITE top"
            elif key == ord("b"):
                if bottom_required:
                    bottom_required = False
                    stage_index = len(ANGLED_SIDE_SEQUENCE) - 1
                    captured.pop("D", None)
                    captured.pop("L", None)
                    save_state(captured, output_dir)
                    message = "Rescan ORANGE front, keep WHITE top"
                elif stage_index > 0:
                    stage_index -= 1
                    removed = ANGLED_SIDE_SEQUENCE[stage_index]
                    captured.pop(removed.notation, None)
                    for later in ANGLED_SIDE_SEQUENCE[stage_index + 1 :]:
                        captured.pop(later.notation, None)
                    if stage_index == 0:
                        captured.pop("U", None)
                    save_state(captured, output_dir)
                    message = f"Rescan {removed.colour.upper()} front"
            elif key == ord(" "):
                if bottom_required:
                    captured["D"] = sample_grid(frame)
                    output_dir.mkdir(parents=True, exist_ok=True)
                    cv2.imwrite(str(output_dir / "face_D.jpg"), frame)
                    state_path = save_state(captured, output_dir)
                    outcome = build_scan_outcome(captured)
                    if outcome is None:
                        captured.pop("D", None)
                        save_state(captured, output_dir)
                        message = "Yellow scan has invalid colour counts; rescan it or press B"
                        continue
                    try:
                        if validate_outcome is not None:
                            validate_outcome(outcome)
                    except ValueError as exc:
                        captured.pop("D", None)
                        save_state(captured, output_dir)
                        message = f"Invalid cube: {exc}; rescan YELLOW or press B"
                        continue
                    print("Angled capture complete with a scanned D fallback.")
                    print(f"Saved state: {state_path}")
                    return outcome

                side = ANGLED_SIDE_SEQUENCE[stage_index]
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
                final_stage = stage_index == len(ANGLED_SIDE_SEQUENCE) - 1
                state_path = save_state(
                    captured, output_dir, infer_bottom=final_stage
                )
                stage_index += 1

                if stage_index == len(ANGLED_SIDE_SEQUENCE):
                    state = build_state(captured, infer_bottom=True)
                    outcome = build_scan_outcome(captured, infer_bottom=True)
                    print(json.dumps(state, indent=2))
                    if outcome is None:
                        bottom_required = True
                        message = "D is not uniquely inferable; scan YELLOW with GREEN at top"
                        save_state(captured, output_dir)
                        continue
                    try:
                        if validate_outcome is not None:
                            validate_outcome(outcome)
                    except ValueError as exc:
                        message = f"Inference rejected ({exc}); scan YELLOW with GREEN at top"
                        bottom_required = True
                        save_state(captured, output_dir)
                        continue
                    print("Angled capture complete: D inferred from U, F, R, B, L.")
                    print(f"Saved state: {state_path}")
                    return outcome

                next_side = ANGLED_SIDE_SEQUENCE[stage_index]
                message = (
                    f"Saved {side.notation}; rotate cube to "
                    f"{next_side.colour.upper()} front, keep WHITE top"
                )
    finally:
        camera.close()
        cv2.destroyAllWindows()


def run_motorized_angled_scanner(
    camera: Camera,
    output_dir: Path,
    platform: RotatingPlatform,
    validate_outcome: Callable[[ScanOutcome], None] | None = None,
    settle_seconds: float = 1.0,
) -> ScanOutcome | None:
    """Capture U/F, R, B, L automatically between calibrated quarter turns."""
    if settle_seconds < 0:
        raise ValueError("settle_seconds must not be negative")

    captured: dict[str, list[SampleResult]] = {}
    stage_index = 0
    automatic_capture_at: float | None = None
    bottom_required = False
    message = "Align GREEN front and WHITE top, then press SPACE once"
    last_preview = 0.0
    side_preview: list[str] | None = None
    top_preview: list[str] | None = None

    try:
        while True:
            frame = camera.read()
            now = time.monotonic()
            display_frame = frame.copy()
            references = centre_references(captured)

            if bottom_required:
                if now - last_preview >= 0.15:
                    side_preview = classify_samples(sample_grid(frame), references)
                    last_preview = now
                draw_grid(display_frame, side_preview)
                draw_bottom_status(display_frame, captured, message)
            else:
                if now - last_preview >= 0.15:
                    live_side, _ = sample_angled_face(frame, ANGLED_FRONT_QUAD)
                    live_top, _ = sample_angled_face(frame, ANGLED_TOP_QUAD)
                    side_preview = classify_samples(live_side, references)
                    top_preview = classify_samples(live_top, references)
                    last_preview = now
                side = ANGLED_SIDE_SEQUENCE[stage_index]
                draw_perspective_grid(
                    display_frame,
                    ANGLED_TOP_QUAD,
                    "U",
                    DISPLAY_BGR["white"],
                    top_preview,
                )
                draw_perspective_grid(
                    display_frame,
                    ANGLED_FRONT_QUAD,
                    side.notation,
                    DISPLAY_BGR[side.colour],
                    side_preview,
                )
                draw_angled_status(
                    display_frame, stage_index, captured, message, motorized=True
                )

            cv2.imshow("Rubik's Cube Motorized Scanner", display_frame)
            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                platform.return_home()
                return None

            if key in (ord("r"), ord("b")):
                platform.return_home()
                captured.clear()
                stage_index = 0
                automatic_capture_at = None
                bottom_required = False
                message = "Scan reset; align GREEN front and WHITE top, then press SPACE"
                save_state(captured, output_dir)
                continue

            if bottom_required:
                if key != ord(" "):
                    continue
                captured["D"] = sample_grid(frame)
                output_dir.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(output_dir / "face_D.jpg"), frame)
                state_path = save_state(captured, output_dir)
                outcome = build_scan_outcome(captured)
                if outcome is None:
                    captured.pop("D", None)
                    save_state(captured, output_dir)
                    message = "Yellow scan has invalid colour counts; rescan it"
                    continue
                try:
                    if validate_outcome is not None:
                        validate_outcome(outcome)
                except ValueError as exc:
                    captured.pop("D", None)
                    save_state(captured, output_dir)
                    message = f"Invalid cube: {exc}; rescan YELLOW"
                    continue
                print("Motorized capture complete with a scanned D fallback.")
                print(f"Saved state: {state_path}")
                return outcome

            capture_due = (
                automatic_capture_at is not None and now >= automatic_capture_at
            )
            first_capture_requested = stage_index == 0 and key == ord(" ")
            if not (capture_due or first_capture_requested):
                continue

            side = ANGLED_SIDE_SEQUENCE[stage_index]
            side_samples, side_image = sample_angled_face(frame, ANGLED_FRONT_QUAD)
            captured[side.notation] = side_samples
            output_dir.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(output_dir / f"face_{side.notation}.jpg"), side_image)

            if stage_index == 0:
                top_samples, top_image = sample_angled_face(frame, ANGLED_TOP_QUAD)
                captured["U"] = top_samples
                cv2.imwrite(str(output_dir / "face_U.jpg"), top_image)

            cv2.imwrite(
                str(output_dir / f"capture_{stage_index + 1}_{side.colour}.jpg"),
                frame,
            )
            final_stage = stage_index == len(ANGLED_SIDE_SEQUENCE) - 1
            state_path = save_state(captured, output_dir, infer_bottom=final_stage)
            stage_index += 1
            automatic_capture_at = None

            message = f"Saved {side.colour.upper()}; rotating platform"
            draw_angled_status(
                display_frame,
                min(stage_index - 1, len(ANGLED_SIDE_SEQUENCE) - 1),
                captured,
                message,
                motorized=True,
            )
            cv2.imshow("Rubik's Cube Motorized Scanner", display_frame)
            cv2.waitKey(1)
            platform.rotate_next_quarter()

            if stage_index == len(ANGLED_SIDE_SEQUENCE):
                state = build_state(captured, infer_bottom=True)
                outcome = build_scan_outcome(captured, infer_bottom=True)
                print(json.dumps(state, indent=2))
                if outcome is None:
                    bottom_required = True
                    message = (
                        "Platform returned to GREEN. D is ambiguous; "
                        "scan YELLOW with GREEN at top"
                    )
                    save_state(captured, output_dir)
                    continue
                try:
                    if validate_outcome is not None:
                        validate_outcome(outcome)
                except ValueError as exc:
                    bottom_required = True
                    message = (
                        f"Platform returned to GREEN. Inference rejected ({exc}); "
                        "scan YELLOW"
                    )
                    save_state(captured, output_dir)
                    continue
                print("Motorized capture complete: platform returned to GREEN.")
                print(f"Saved state: {state_path}")
                return outcome

            next_side = ANGLED_SIDE_SEQUENCE[stage_index]
            message = (
                f"At {next_side.colour.upper()}; settling for "
                f"{settle_seconds:g} second(s) before automatic capture"
            )
            automatic_capture_at = time.monotonic() + settle_seconds
    finally:
        try:
            platform.return_home()
        except Exception:
            # The original motor/camera error remains the useful failure.
            pass
        camera.close()
        cv2.destroyAllWindows()


def scan_cube(
    camera: Camera,
    output_dir: Path,
    validate_outcome: Callable[[ScanOutcome], None],
    mode: str = "angled-sides",
    platform: RotatingPlatform | None = None,
    motor_settle_seconds: float = 1.0,
) -> ScanOutcome | None:
    """Scan until a valid cube is accepted or the user cancels."""
    if mode == "motorized-angled":
        if platform is None:
            raise ValueError("motorized-angled mode requires a rotating platform")
        return run_motorized_angled_scanner(
            camera,
            output_dir,
            platform,
            validate_outcome=validate_outcome,
            settle_seconds=motor_settle_seconds,
        )
    if mode == "angled-sides":
        return run_angled_scanner(
            camera,
            output_dir,
            validate_outcome=validate_outcome,
            exit_on_valid=True,
        )
    return run_scanner(
        camera,
        output_dir,
        validate_outcome=validate_outcome,
        exit_on_valid=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=("head-on", "angled-sides", "motorized-angled"),
        default="angled-sides",
        help=(
            "motorized-angled rotates automatically; angled-sides rotates manually; "
            "head-on scans all six faces"
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
    parser.add_argument("--motor-in1-pin", type=int, default=17)
    parser.add_argument("--motor-in2-pin", type=int, default=18)
    parser.add_argument("--motor-in3-pin", type=int, default=27)
    parser.add_argument("--motor-in4-pin", type=int, default=22)
    parser.add_argument(
        "--motor-direction",
        choices=("clockwise", "counterclockwise"),
        default="clockwise",
    )
    parser.add_argument("--motor-steps-per-revolution", type=int, default=4_096)
    parser.add_argument("--motor-settle-seconds", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    platform = None
    if args.mode == "motorized-angled":
        from hardware.stepper_spin import create_stepper_platform

        try:
            platform = create_stepper_platform(
                in1_pin=args.motor_in1_pin,
                in2_pin=args.motor_in2_pin,
                in3_pin=args.motor_in3_pin,
                in4_pin=args.motor_in4_pin,
                clockwise=args.motor_direction == "clockwise",
                steps_per_revolution=args.motor_steps_per_revolution,
            )
        except Exception as exc:
            raise SystemExit(f"Platform error: {exc}") from exc
    try:
        camera = create_camera(args.backend, args.device)
    except RuntimeError as exc:
        if platform is not None:
            platform.close()
        raise SystemExit(f"Camera error: {exc}") from exc
    try:
        if args.mode == "motorized-angled":
            run_motorized_angled_scanner(
                camera,
                args.output,
                platform,
                settle_seconds=args.motor_settle_seconds,
            )
        elif args.mode == "angled-sides":
            run_angled_scanner(camera, args.output)
        else:
            run_scanner(camera, args.output)
    finally:
        if platform is not None:
            platform.close()


if __name__ == "__main__":
    main()
