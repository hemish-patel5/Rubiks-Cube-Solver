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
