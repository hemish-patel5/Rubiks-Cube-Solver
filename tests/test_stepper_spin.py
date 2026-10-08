import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from hardware.stepper_spin import (
    CALIBRATED_QUARTER_STEPS,
    STEPS_PER_REVOLUTION,
    SpinSettings,
    StepperSpinner,
    step_period_us,
)


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
        self.assertEqual(sleeps[0], 0.0001)

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

    def test_calibrated_quarters_complete_one_revolution(self) -> None:
        self.assertEqual(CALIBRATED_QUARTER_STEPS, (5_450, 4_050, 4_250, 4_250))
        self.assertEqual(sum(CALIBRATED_QUARTER_STEPS), STEPS_PER_REVOLUTION)

    def test_quarter_turn_sequence_moves_and_pauses(self) -> None:
        pauses: list[float] = []
        spinner = StepperSpinner(
            FakePin(), FakePin(), SpinSettings(), sleep=pauses.append
        )
        with mock.patch.object(
            spinner, "spin", side_effect=[5_450, 4_050]
        ) as spin, mock.patch("builtins.print"):
            total = spinner.spin_quarter_turns(pause_seconds=1.0, turns=2)

        self.assertEqual(total, 9_500)
        self.assertEqual(
            [call.args[0] for call in spin.call_args_list], [5_450, 4_050]
        )
        self.assertEqual(pauses, [1.0, 1.0])


if __name__ == "__main__":
    unittest.main()
