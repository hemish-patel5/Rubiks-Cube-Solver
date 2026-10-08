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
    positioned_step_period_us,
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

    def test_positioned_move_accelerates_and_decelerates(self) -> None:
        settings = SpinSettings(start_rate=100, cruise_rate=1_000)
        periods = [
            positioned_step_period_us(index, 2_001, settings, ramp_steps=800)
            for index in (0, 800, 1_000, 1_200, 2_000)
        ]
        self.assertEqual(periods, [10_000, 1_000, 1_000, 1_000, 10_000])

    def test_rotate_next_quarter_uses_each_calibrated_segment(self) -> None:
        spinner = StepperSpinner(FakePin(), FakePin(), SpinSettings())
        with mock.patch.object(
            spinner, "move_positioned", side_effect=CALIBRATED_QUARTER_STEPS
        ) as move:
            moved = [spinner.rotate_next_quarter() for _ in range(4)]

        self.assertEqual(moved, list(CALIBRATED_QUARTER_STEPS))
        self.assertEqual(
            [call.args[0] for call in move.call_args_list],
            list(CALIBRATED_QUARTER_STEPS),
        )
        self.assertEqual(spinner.quarter_index, 0)

    def test_quarter_turn_sequence_moves_and_pauses(self) -> None:
        pauses: list[float] = []
        spinner = StepperSpinner(
            FakePin(), FakePin(), SpinSettings(), sleep=pauses.append
        )
        with mock.patch.object(
            spinner, "rotate_next_quarter", side_effect=[5_450, 4_050]
        ) as rotate, mock.patch("builtins.print"):
            total = spinner.spin_quarter_turns(pause_seconds=1.0, turns=2)

        self.assertEqual(total, 9_500)
        self.assertEqual(
            rotate.call_count, 2
        )
        self.assertEqual(pauses, [1.0, 1.0])

    def test_return_home_finishes_remaining_clockwise_segments(self) -> None:
        spinner = StepperSpinner(FakePin(), FakePin(), SpinSettings())
        spinner._quarter_index = 2
        with mock.patch.object(
            spinner, "move_positioned", side_effect=[4_250, 4_250]
        ) as move:
            moved = spinner.return_home()

        self.assertEqual(moved, 8_500)
        self.assertEqual(spinner.quarter_index, 0)
        self.assertEqual([call.args[0] for call in move.call_args_list], [4_250, 4_250])


if __name__ == "__main__":
    unittest.main()
