from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np
from picamera2 import Picamera2


@dataclass(frozen=True)
class SampleResult:
    row: int
    column: int
    bgr: tuple[int, int, int]
    hsv: tuple[int, int, int]


GRID_SIZE = 3
SAMPLE_SIZE = 18
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# Size of the complete 3x3 scanning region.
FACE_SIZE = 270


def create_camera() -> Picamera2:
    camera = Picamera2()

    configuration = camera.create_preview_configuration(
        main={
            "format": "BGR888",
            "size": (FRAME_WIDTH, FRAME_HEIGHT),
        }
    )

    camera.configure(configuration)
    camera.start()

    # Allow exposure and white balance to settle.
    time.sleep(2)

    return camera


def get_grid_centres() -> list[tuple[int, int, int, int]]:
    """
    Return:
        [(row, column, centre_x, centre_y), ...]
    """

    start_x = (FRAME_WIDTH - FACE_SIZE) // 2
    start_y = (FRAME_HEIGHT - FACE_SIZE) // 2
    cell_size = FACE_SIZE // GRID_SIZE

    centres = []

    for row in range(GRID_SIZE):
        for column in range(GRID_SIZE):
            centre_x = start_x + column * cell_size + cell_size // 2
            centre_y = start_y + row * cell_size + cell_size // 2

            centres.append((row, column, centre_x, centre_y))

    return centres


def sample_grid(frame: np.ndarray) -> list[SampleResult]:
    hsv_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    results: list[SampleResult] = []

    for row, column, centre_x, centre_y in get_grid_centres():
        half = SAMPLE_SIZE // 2

        bgr_region = frame[
            centre_y - half : centre_y + half,
            centre_x - half : centre_x + half,
        ]

        hsv_region = hsv_frame[
            centre_y - half : centre_y + half,
            centre_x - half : centre_x + half,
        ]

        # Median is less affected by glare and noise than a single pixel.
        median_bgr = np.median(
            bgr_region.reshape(-1, 3),
            axis=0,
        ).astype(int)

        median_hsv = np.median(
            hsv_region.reshape(-1, 3),
            axis=0,
        ).astype(int)

        results.append(
            SampleResult(
                row=row,
                column=column,
                bgr=tuple(int(value) for value in median_bgr),
                hsv=tuple(int(value) for value in median_hsv),
            )
        )

    return results


def draw_grid(frame: np.ndarray) -> None:
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

        cv2.line(
            frame,
            (x, start_y),
            (x, start_y + FACE_SIZE),
            (255, 255, 255),
            1,
        )

        cv2.line(
            frame,
            (start_x, y),
            (start_x + FACE_SIZE, y),
            (255, 255, 255),
            1,
        )

    for row, column, centre_x, centre_y in get_grid_centres():
        half = SAMPLE_SIZE // 2

        cv2.rectangle(
            frame,
            (centre_x - half, centre_y - half),
            (centre_x + half, centre_y + half),
            (0, 255, 0),
            2,
        )

        cv2.putText(
            frame,
            str(row * 3 + column + 1),
            (centre_x - 8, centre_y - 25),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )


def print_results(results: list[SampleResult]) -> None:
    print("\nCaptured face:")
    print("-" * 55)

    for result in results:
        print(
            f"Cell {result.row + 1},{result.column + 1} "
            f"BGR={result.bgr} HSV={result.hsv}"
        )

    print("-" * 55)


def main() -> None:
    camera = create_camera()

    try:
        while True:
            frame = camera.capture_array()

            display_frame = frame.copy()
            draw_grid(display_frame)

            cv2.putText(
                display_frame,
                "Align one cube face with the grid",
                (20, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.putText(
                display_frame,
                "SPACE: capture | Q: quit",
                (20, FRAME_HEIGHT - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("Rubik's Cube Scanner", display_frame)

            key = cv2.waitKey(1) & 0xFF

            if key == ord("q"):
                break

            if key == ord(" "):
                results = sample_grid(frame)
                print_results(results)

                timestamp = int(time.time())
                filename = f"captured_face_{timestamp}.jpg"

                cv2.imwrite(filename, frame)
                print(f"Saved image: {filename}")

    finally:
        camera.stop()
        camera.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
