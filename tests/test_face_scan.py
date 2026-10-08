import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

AMBIGUOUS_BOTTOM_STATE = (
    "BRBUUDUDFRLLBRFBFRRRDBFDFRUDURFDDULDLBFRLLLULUFDLBBBUF"
)


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

    def test_angled_face_is_rectified_and_sampled_in_row_order(self) -> None:
        square = np.zeros((face_scan.FACE_SIZE, face_scan.FACE_SIZE, 3), np.uint8)
        expected = []
        cell_size = face_scan.FACE_SIZE // 3
        for index in range(9):
            colour = (20 + index, 70 + index, 120 + index)
            expected.append(colour)
            row, column = divmod(index, 3)
            square[
                row * cell_size : (row + 1) * cell_size,
                column * cell_size : (column + 1) * cell_size,
            ] = colour
        destination = np.asarray(
            ((0, 0), (face_scan.FACE_SIZE - 1, 0),
             (face_scan.FACE_SIZE - 1, face_scan.FACE_SIZE - 1),
             (0, face_scan.FACE_SIZE - 1)),
            dtype=np.float32,
        )
        source = np.asarray(face_scan.ANGLED_TOP_QUAD, dtype=np.float32)
        transform = cv2.getPerspectiveTransform(destination, source)
        frame = cv2.warpPerspective(
            square, transform, (face_scan.FRAME_WIDTH, face_scan.FRAME_HEIGHT)
        )
        samples, rectified = face_scan.sample_angled_face(
            frame, face_scan.ANGLED_TOP_QUAD
        )
        self.assertEqual(rectified.shape[:2], (face_scan.FACE_SIZE, face_scan.FACE_SIZE))
        for result, colour in zip(samples, expected):
            self.assertTrue(
                np.allclose(result.bgr, colour, atol=2),
                (result.row, result.column, result.bgr, colour),
            )

    def test_angled_scanner_captures_white_once_then_green_red_blue_orange(self) -> None:
        class FakeCamera:
            closed = False
            frame_number = 0

            def read(self) -> np.ndarray:
                frame = np.zeros(
                    (face_scan.FRAME_HEIGHT, face_scan.FRAME_WIDTH, 3), np.uint8
                )
                frame[0, 0, 0] = self.frame_number
                self.frame_number += 1
                return frame

            def close(self) -> None:
                self.closed = True

        camera = FakeCamera()
        def capture(frame, quad):
            if quad == face_scan.ANGLED_TOP_QUAD:
                colour = "white"
            else:
                colour = ("green", "red", "blue", "orange")[int(frame[0, 0, 0])]
            samples = [sample(colour, index // 3, index % 3) for index in range(9)]
            return samples, np.zeros(
                (face_scan.FACE_SIZE, face_scan.FACE_SIZE, 3), np.uint8
            )

        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            face_scan, "sample_angled_face", side_effect=capture
        ), mock.patch.object(face_scan, "draw_perspective_grid"), mock.patch.object(
            face_scan, "draw_angled_status"
        ), mock.patch.object(face_scan.cv2, "imshow"), mock.patch.object(
            face_scan.cv2, "waitKey", side_effect=[ord(" ")] * 4
        ), mock.patch.object(face_scan.cv2, "imwrite", return_value=True) as imwrite, mock.patch.object(
            face_scan.cv2, "destroyAllWindows"
        ), mock.patch("builtins.print"):
            outcome = face_scan.run_angled_scanner(camera, Path(directory))
            state = json.loads(
                (Path(directory) / "cube_state.json").read_text(encoding="utf-8")
            )

        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.facelets_urfdlb, "".join(face * 9 for face in "URFDLB"))
        saved_names = [Path(call.args[0]).name for call in imwrite.call_args_list]
        self.assertEqual(saved_names.count("face_U.jpg"), 1)
        self.assertEqual(
            [name for name in saved_names if name.startswith("face_")],
            ["face_F.jpg", "face_U.jpg", "face_R.jpg", "face_B.jpg", "face_L.jpg"],
        )
        self.assertEqual(set(state["faces"]), {"U", "R", "F", "D", "L", "B"})
        self.assertTrue(state["complete"])
        self.assertEqual(state["captured_faces"], ["F", "U", "R", "B", "L"])
        self.assertEqual(state["inferred_faces"], ["D"])
        self.assertTrue(state["faces"]["D"]["inferred"])
        self.assertTrue(camera.closed)

    def test_angled_scanner_requests_yellow_when_bottom_is_ambiguous(self) -> None:
        class FakeCamera:
            closed = False
            frame_number = 0

            def read(self) -> np.ndarray:
                frame = np.zeros(
                    (face_scan.FRAME_HEIGHT, face_scan.FRAME_WIDTH, 3), np.uint8
                )
                frame[0, 0, 0] = self.frame_number
                self.frame_number += 1
                return frame

            def close(self) -> None:
                self.closed = True

        notation_to_colour = {
            face.notation: face.colour for face in face_scan.FACE_SEQUENCE
        }
        face_colours = {
            notation: [
                notation_to_colour[value]
                for value in AMBIGUOUS_BOTTOM_STATE[index * 9 : index * 9 + 9]
            ]
            for index, notation in enumerate("URFDLB")
        }

        def samples(notation):
            return [
                sample(colour, index // 3, index % 3)
                for index, colour in enumerate(face_colours[notation])
            ]

        def capture(frame, quad):
            notation = "U" if quad == face_scan.ANGLED_TOP_QUAD else (
                "F", "R", "B", "L"
            )[int(frame[0, 0, 0])]
            return samples(notation), np.zeros(
                (face_scan.FACE_SIZE, face_scan.FACE_SIZE, 3), np.uint8
            )

        camera = FakeCamera()
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            face_scan, "sample_angled_face", side_effect=capture
        ), mock.patch.object(
            face_scan, "sample_grid", return_value=samples("D")
        ), mock.patch.object(face_scan, "draw_perspective_grid"), mock.patch.object(
            face_scan, "draw_angled_status"
        ), mock.patch.object(face_scan, "draw_grid"), mock.patch.object(
            face_scan, "draw_bottom_status"
        ), mock.patch.object(face_scan.cv2, "imshow"), mock.patch.object(
            face_scan.cv2, "waitKey", side_effect=[ord(" ")] * 5
        ), mock.patch.object(face_scan.cv2, "imwrite", return_value=True), mock.patch.object(
            face_scan.cv2, "destroyAllWindows"
        ), mock.patch("builtins.print"):
            outcome = face_scan.run_angled_scanner(camera, Path(directory))
            state = json.loads(
                (Path(directory) / "cube_state.json").read_text(encoding="utf-8")
            )

        self.assertEqual(outcome.facelets_urfdlb, AMBIGUOUS_BOTTOM_STATE)
        self.assertEqual(state["inferred_faces"], [])
        self.assertFalse(state["faces"]["D"]["inferred"])
        self.assertTrue(camera.closed)

    def test_motorized_scanner_captures_four_positions_and_returns_home(self) -> None:
        class FakePlatform:
            def __init__(self) -> None:
                self.position = 0
                self.rotate_calls = 0
                self.return_home_calls = 0

            def rotate_next_quarter(self) -> int:
                self.position = (self.position + 1) % 4
                self.rotate_calls += 1
                return 1

            def return_home(self) -> int:
                self.return_home_calls += 1
                self.position = 0
                return 0

            def close(self) -> None:
                pass

        platform = FakePlatform()

        class FakeCamera:
            closed = False

            def read(self) -> np.ndarray:
                frame = np.zeros(
                    (face_scan.FRAME_HEIGHT, face_scan.FRAME_WIDTH, 3), np.uint8
                )
                frame[0, 0, 0] = platform.position
                return frame

            def close(self) -> None:
                self.closed = True

        def capture(frame, quad):
            colour = (
                "white"
                if quad == face_scan.ANGLED_TOP_QUAD
                else ("green", "red", "blue", "orange")[int(frame[0, 0, 0])]
            )
            samples = [sample(colour, index // 3, index % 3) for index in range(9)]
            return samples, np.zeros(
                (face_scan.FACE_SIZE, face_scan.FACE_SIZE, 3), np.uint8
            )

        camera = FakeCamera()
        keys = [ord(" ")] + [-1] * 12
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            face_scan, "sample_angled_face", side_effect=capture
        ), mock.patch.object(face_scan, "draw_perspective_grid"), mock.patch.object(
            face_scan, "draw_angled_status"
        ), mock.patch.object(face_scan.cv2, "imshow"), mock.patch.object(
            face_scan.cv2, "waitKey", side_effect=keys
        ), mock.patch.object(
            face_scan.cv2, "imwrite", return_value=True
        ), mock.patch.object(
            face_scan.cv2, "destroyAllWindows"
        ), mock.patch("builtins.print"):
            outcome = face_scan.run_motorized_angled_scanner(
                camera, Path(directory), platform, settle_seconds=0
            )
            state = json.loads(
                (Path(directory) / "cube_state.json").read_text(encoding="utf-8")
            )

        self.assertEqual(outcome.facelets_urfdlb, "".join(face * 9 for face in "URFDLB"))
        self.assertEqual(platform.rotate_calls, 4)
        self.assertEqual(platform.position, 0)
        self.assertGreaterEqual(platform.return_home_calls, 1)
        self.assertEqual(state["captured_faces"], ["F", "U", "R", "B", "L"])
        self.assertEqual(state["inferred_faces"], ["D"])
        self.assertTrue(camera.closed)

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

    def test_shadowed_yellow_from_webcam_scan(self) -> None:
        # Real centre samples and the confirmed yellow U bottom-left sticker.
        references = {
            "white": (190, 177, 166), "red": (71, 70, 179),
            "green": (58, 111, 36), "yellow": (39, 216, 205),
            "orange": (38, 127, 192), "blue": (173, 51, 31),
        }
        samples = [
            face_scan.SampleResult(2, 0, (41, 152, 144), (32, 185, 152)),
            face_scan.SampleResult(0, 0, (57, 134, 191), (17, 179, 191)),
        ]
        self.assertEqual(
            face_scan.classify_samples(samples, references), ["yellow", "orange"]
        )

    def test_calibrated_colours_survive_brightness_changes(self) -> None:
        references = COLOUR_BGR
        for colour, bgr in references.items():
            for brightness in (0.3, 0.5, 0.8, 1.0):
                with self.subTest(colour=colour, brightness=brightness):
                    shaded = tuple(round(channel * brightness) for channel in bgr)
                    pixel = np.array([[shaded]], dtype=np.uint8)
                    hsv = tuple(int(v) for v in cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0])
                    result = face_scan.SampleResult(0, 0, shaded, hsv)
                    self.assertEqual(
                        face_scan.classify_samples([result], references), [colour]
                    )

    def test_solver_rejection_stays_in_scanner_for_back_rescan(self) -> None:
        class FakeCamera:
            def __init__(self) -> None:
                self.frame_number = 0
                self.closed = False

            def read(self) -> np.ndarray:
                frame = np.full(
                    (face_scan.FRAME_HEIGHT, face_scan.FRAME_WIDTH, 3),
                    min(self.frame_number, 5),
                    dtype=np.uint8,
                )
                self.frame_number += 1
                return frame

            def close(self) -> None:
                self.closed = True

        camera = FakeCamera()
        messages: list[str] = []

        def samples_for_frame(frame: np.ndarray) -> list[face_scan.SampleResult]:
            face = face_scan.FACE_SEQUENCE[int(frame[0, 0, 0])]
            return [sample(face.colour, index // 3, index % 3) for index in range(9)]

        def reject(_outcome: face_scan.ScanOutcome) -> None:
            raise ValueError("the stickers form an impossible cube state")

        def record_status(
            _frame: np.ndarray,
            _face_index: int,
            _captured: dict[str, list[face_scan.SampleResult]],
            message: str,
        ) -> None:
            messages.append(message)

        keys = [ord(" ")] * 6 + [ord("b"), ord("q")]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            face_scan, "sample_grid", side_effect=samples_for_frame
        ), mock.patch.object(face_scan, "draw_grid"), mock.patch.object(
            face_scan, "draw_status", side_effect=record_status
        ), mock.patch.object(face_scan.cv2, "imshow"), mock.patch.object(
            face_scan.cv2, "waitKey", side_effect=keys
        ), mock.patch.object(face_scan.cv2, "imwrite", return_value=True), mock.patch.object(
            face_scan.cv2, "destroyAllWindows"
        ):
            outcome = face_scan.scan_cube(
                camera, Path(directory), reject, mode="head-on"
            )
            saved = json.loads(
                (Path(directory) / "cube_state.json").read_text(encoding="utf-8")
            )

        self.assertIsNone(outcome)
        self.assertTrue(camera.closed)
        self.assertTrue(any("Invalid cube" in message for message in messages))
        self.assertFalse(saved["complete"])
        self.assertNotIn("B", saved["faces"])


if __name__ == "__main__":
    unittest.main()
