import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from hardware.sense_hat_adapter import map_joystick
from interface import guidance
from interface.guidance import MoveNavigator


class JoystickMappingTests(unittest.TestCase):
    def test_scanner_mapping(self) -> None:
        self.assertEqual(map_joystick("middle", "scanner"), "capture")
        self.assertEqual(map_joystick("left", "scanner"), "back")
        self.assertEqual(map_joystick("down", "scanner"), "reset")
        self.assertEqual(map_joystick("up", "scanner"), "cancel")
        self.assertIsNone(map_joystick("right", "scanner"))

    def test_guidance_mapping(self) -> None:
        self.assertEqual(map_joystick("right", "guidance"), "next")
        self.assertEqual(map_joystick("middle", "guidance"), "next")
        self.assertEqual(map_joystick("left", "guidance"), "back")
        self.assertEqual(map_joystick("up", "guidance"), "cancel")
        self.assertIsNone(map_joystick("down", "guidance"))


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
        class FakeControls:
            def __init__(self) -> None:
                self.statuses: list[tuple[str, str]] = []

            def poll_guidance_action(self) -> str | None:
                return None

            def show_status(self, status: str, detail: str = "") -> None:
                self.statuses.append((status, detail))

        controls = FakeControls()
        with mock.patch.object(guidance.cv2, "imshow"), mock.patch.object(
            guidance.cv2, "waitKeyEx", side_effect=[ord(" "), ord(" ")]
        ), mock.patch.object(guidance.cv2, "destroyWindow"):
            result = guidance.show_guidance(["R", "U'"], controls)

        self.assertEqual(result, "COMPLETE")
        self.assertEqual(
            controls.statuses,
            [("move", "R"), ("move", "U'"), ("complete", "")],
        )


if __name__ == "__main__":
    unittest.main()
