import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from interface import guidance
from interface.guidance import MoveNavigator


class MoveNavigationTests(unittest.TestCase):
    def test_next_back_and_completion(self) -> None:
        navigator = MoveNavigator(("R", "U'", "F2"))
        self.assertEqual(navigator.current, "R")
        self.assertFalse(navigator.next())
        self.assertEqual(navigator.current, "U'")
        navigator.back()
        self.assertEqual(navigator.current, "R")
        navigator.back()
        self.assertEqual(navigator.current, "R")
        self.assertFalse(navigator.next())
        self.assertFalse(navigator.next())
        self.assertTrue(navigator.next())

    def test_zero_moves_is_complete(self) -> None:
        navigator = MoveNavigator(())
        self.assertIsNone(navigator.current)
        self.assertTrue(navigator.next())

    def test_guidance_mirrors_current_moves_and_completion(self) -> None:
        with mock.patch.object(guidance.cv2, "imshow"), mock.patch.object(
            guidance.cv2, "waitKeyEx", side_effect=[ord(" "), ord(" ")]
        ), mock.patch.object(guidance.cv2, "destroyWindow"):
            result = guidance.show_guidance(["R", "U'"])

        self.assertEqual(result, "COMPLETE")


if __name__ == "__main__":
    unittest.main()
