import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from hardware.stepper_spin import SpinSettings, StepperSpinner, step_period_us


class FakePin:
    def __init__(self) -> None:
        self.events: list[str] = []

    def on(self) -> None:
        self.events.append("on")

    def off(self) -> None:
        self.events.append("off")

    def close(self) -> None:
        self.events.append("close")


class StepperSpinnerTests(unittest.TestCase):
    def test_ramp_matches_configured_start_and_cruise_rates(self) -> None:
        settings = SpinSettings()
        self.assertEqual(step_period_us(0, settings), 10_000)
        self.assertEqual(step_period_us(7_000, settings), 666)
        self.assertEqual(step_period_us(20_000, settings), 666)

    def test_finite_spin_sets_direction_and_emits_requested_pulses(self) -> None:
        direction = FakePin()
        step = FakePin()
        sleeps: list[float] = []
        spinner = StepperSpinner(
            direction, step, SpinSettings(), clockwise_high=False, sleep=sleeps.append
        )

        self.assertEqual(spinner.spin(3), 3)
        self.assertEqual(direction.events, ["off"])
        self.assertEqual(step.events.count("on"), 3)
        self.assertEqual(step.events[-1], "off")
        self.assertEqual(len(sleeps), 7)

    def test_step_is_left_low_when_pulse_generation_fails(self) -> None:
        direction = FakePin()
        step = FakePin()

        def interrupted_sleep(_seconds: float) -> None:
            if "on" in step.events:
                raise KeyboardInterrupt

        spinner = StepperSpinner(
            direction, step, SpinSettings(), sleep=interrupted_sleep
        )
        with self.assertRaises(KeyboardInterrupt):
            spinner.spin()
        self.assertEqual(step.events[-1], "off")


if __name__ == "__main__":
    unittest.main()
