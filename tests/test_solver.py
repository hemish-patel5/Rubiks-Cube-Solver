import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from cube.solver import InvalidCubeState, SOLVED_STATE, solve_3x3
from vision import face_scan


KNOWN_SCRAMBLE = "DRLUUBFBRBLURRLRUBLRDDFDLFUFUFFDBRDUBRUFLLFDDBFLUBLRBD"


class SolverTests(unittest.TestCase):
    def test_solved_cube_has_zero_moves(self) -> None:
        self.assertEqual(solve_3x3(SOLVED_STATE), [])

    def test_known_scramble_has_solution(self) -> None:
        self.assertGreater(len(solve_3x3(KNOWN_SCRAMBLE)), 0)

    def test_bottom_face_is_reconstructed_from_five_visible_faces(self) -> None:
        notation_to_colour = {
            face.notation: face.colour for face in face_scan.FACE_SEQUENCE
        }
        classified = {}
        for index, notation in enumerate("URFDLB"):
            if notation != "D":
                classified[notation] = [
                    notation_to_colour[facelet]
                    for facelet in KNOWN_SCRAMBLE[index * 9 : index * 9 + 9]
                ]
        inferred = face_scan.infer_bottom_face(classified)
        expected = [notation_to_colour[value] for value in KNOWN_SCRAMBLE[27:36]]
        self.assertEqual(inferred, expected)

    def test_bottom_inference_rejects_impossible_adjacent_colours(self) -> None:
        classified = {
            notation: [colour] * 9
            for notation, colour in (
                ("U", "white"), ("R", "red"), ("F", "green"),
                ("L", "orange"), ("B", "blue"),
            )
        }
        classified["U"][5] = "green"
        with self.assertRaisesRegex(ValueError, "duplicate or invalid edge"):
            face_scan.infer_bottom_face(classified)

    def test_bottom_inference_reports_multiple_physical_completions(self) -> None:
        ambiguous = "BRBUUDUDFRLLBRFBFRRRDBFDFRUDURFDDULDLBFRLLLULUFDLBBBUF"
        notation_to_colour = {
            face.notation: face.colour for face in face_scan.FACE_SEQUENCE
        }
        classified = {}
        for index, notation in enumerate("URFDLB"):
            if notation != "D":
                classified[notation] = [
                    notation_to_colour[facelet]
                    for facelet in ambiguous[index * 9 : index * 9 + 9]
                ]
        with self.assertRaisesRegex(ValueError, r"ambiguous \(2 physical completions\)"):
            face_scan.infer_bottom_face(classified)

    def test_colour_balanced_impossible_cube_is_rejected(self) -> None:
        impossible = list(SOLVED_STATE)
        # Swap the two stickers on the U-F edge to create one flipped edge.
        impossible[7], impossible[19] = impossible[19], impossible[7]
        with self.assertRaisesRegex(InvalidCubeState, "impossible"):
            solve_3x3("".join(impossible))

    def test_scan_outcome_requires_existing_colour_validation(self) -> None:
        captured = {}
        for face in face_scan.FACE_SEQUENCE:
            captured[face.notation] = [
                face_scan.SampleResult(index // 3, index % 3, (0, 0, 0), (0, 0, 0))
                for index in range(9)
            ]
        self.assertIsNone(face_scan.build_scan_outcome(captured))


if __name__ == "__main__":
    unittest.main()
