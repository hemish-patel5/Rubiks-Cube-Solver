import json
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from vision import face_scan


COLOUR_BGR = {
    "white": (235, 235, 235),
    "red": (20, 20, 220),
    "green": (30, 170, 30),
    "yellow": (20, 220, 220),
    "orange": (10, 110, 240),
    "blue": (220, 60, 20),
}


def sample(colour: str, row: int, column: int) -> face_scan.SampleResult:
    bgr = COLOUR_BGR[colour]
    pixel = np.array([[bgr]], dtype=np.uint8)
    hsv = tuple(int(v) for v in cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
    return face_scan.SampleResult(row, column, bgr, hsv)


def solved_cube_samples() -> dict[str, list[face_scan.SampleResult]]:
    captured = {}
    for face in face_scan.FACE_SEQUENCE:
        captured[face.notation] = [
            sample(face.colour, index // 3, index % 3) for index in range(9)
        ]
    return captured


class FaceScannerTests(unittest.TestCase):
    def test_grid_samples_all_nine_cells(self) -> None:
        frame = np.zeros((face_scan.FRAME_HEIGHT, face_scan.FRAME_WIDTH, 3), np.uint8)
        for index, (_, _, x, y) in enumerate(face_scan.get_grid_centres()):
            frame[y - 15 : y + 15, x - 15 : x + 15] = (index, index + 1, index + 2)
        results = face_scan.sample_grid(frame)
        self.assertEqual(len(results), 9)
        self.assertEqual(results[7].bgr, (7, 8, 9))

    def test_centre_calibration_classifies_solved_cube(self) -> None:
        captured = solved_cube_samples()
        classified = face_scan.classify_cube(captured)
        valid, problems = face_scan.validate_cube(classified)
        self.assertTrue(valid, problems)
        self.assertEqual(classified["F"], ["green"] * 9)
        self.assertEqual(
            face_scan.make_facelet_string(classified),
            "U" * 9 + "R" * 9 + "F" * 9 + "D" * 9 + "L" * 9 + "B" * 9,
        )

    def test_centre_calibration_classifies_mixed_face(self) -> None:
        captured = solved_cube_samples()
        mixed = ["white", "red", "green", "yellow", "orange", "blue",
                 "red", "green", "white"]
        samples = [sample(colour, index // 3, index % 3)
                   for index, colour in enumerate(mixed)]
        self.assertEqual(
            face_scan.classify_samples(samples, face_scan.centre_references(captured)),
            mixed,
        )

    def test_state_is_saved_with_colours_and_raw_samples(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = face_scan.save_state(solved_cube_samples(), Path(directory))
            state = json.loads(destination.read_text(encoding="utf-8"))
        self.assertTrue(state["complete"])
        self.assertTrue(state["colour_count_valid"])
        self.assertEqual(state["colour_counts"]["blue"], 9)
        self.assertEqual(state["faces"]["U"]["colours"][1][1], "white")
        self.assertEqual(len(state["faces"]["U"]["samples"]), 9)


if __name__ == "__main__":
    unittest.main()
