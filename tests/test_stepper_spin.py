import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from hardware.stepper_spin import (
    CALIBRATED_QUARTER_STEPS,
    HALF_STEP_SEQUENCE,
    STEPS_PER_REVOLUTION,
    SpinSettings,
    ULN2003Stepper,
    positioned_step_period_us,
    quarter_steps,
    step_period_us,
)


class FakePin:
    def __init__(self) -> None:
        self.active = False
        self.events: list[str] = []

    def on(self) -> None:
        self.active = True
        self.events.append("on")

    def off(self) -> None:
        self.active = False
        self.events.append("off")

    def close(self) -> None:
        self.events.append("close")


class ULN2003StepperTests(unittest.TestCase):
    def make_spinner(self, **kwargs):
        pins = [FakePin() for _ in range(4)]
        spinner = ULN2003Stepper(pins, SpinSettings(), **kwargs)
        return spinner, pins

    def test_ramp_matches_configured_start_and_cruise_rates(self) -> None:
        settings = SpinSettings()
        self.assertEqual(step_period_us(0, settings), 3_333)
        self.assertEqual(step_period_us(128, settings), 1_111)
        self.assertEqual(step_period_us(1_000, settings), 1_111)

    def test_clockwise_spin_emits_half_step_sequence(self) -> None:
        pins = [FakePin() for _ in range(4)]
        states: list[tuple[int, ...]] = []

        def capture_state(_seconds: float) -> None:
            states.append(tuple(int(pin.active) for pin in pins))

        spinner = ULN2003Stepper(pins, SpinSettings(), sleep=capture_state)
        self.assertEqual(spinner.spin(4), 4)
        self.assertEqual(states, list(HALF_STEP_SEQUENCE[:4]))

    def test_counterclockwise_reverses_half_step_sequence(self) -> None:
        pins = [FakePin() for _ in range(4)]
        states: list[tuple[int, ...]] = []

        def capture_state(_seconds: float) -> None:
            states.append(tuple(int(pin.active) for pin in pins))

        spinner = ULN2003Stepper(
            pins, SpinSettings(), clockwise=False, sleep=capture_state
        )
        spinner.spin(3)
        self.assertEqual(
            states,
            [HALF_STEP_SEQUENCE[0], HALF_STEP_SEQUENCE[-1], HALF_STEP_SEQUENCE[-2]],
        )

    def test_close_deenergizes_and_closes_every_input(self) -> None:
        spinner, pins = self.make_spinner(sleep=lambda _seconds: None)
        spinner.spin(1)
        spinner.close()
        self.assertTrue(all(not pin.active for pin in pins))
        self.assertTrue(all(pin.events[-1] == "close" for pin in pins))

    def test_calibrated_quarters_complete_one_revolution(self) -> None:
        self.assertEqual(CALIBRATED_QUARTER_STEPS, (1_024,) * 4)
        self.assertEqual(sum(CALIBRATED_QUARTER_STEPS), STEPS_PER_REVOLUTION)
        self.assertEqual(quarter_steps(4_078), (1_020, 1_020, 1_019, 1_019))

    def test_positioned_move_accelerates_and_decelerates(self) -> None:
        settings = SpinSettings()
        periods = [
            positioned_step_period_us(index, 1_024, settings, ramp_steps=128)
            for index in (0, 128, 512, 895, 1_023)
        ]
        self.assertEqual(periods, [3_333, 1_111, 1_111, 1_111, 3_333])

    def test_rotate_next_quarter_uses_each_configured_segment(self) -> None:
        spinner, _pins = self.make_spinner()
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
        spinner, _pins = self.make_spinner(sleep=pauses.append)
        with mock.patch.object(
            spinner, "rotate_next_quarter", side_effect=[1_024, 1_024]
        ) as rotate, mock.patch("builtins.print"):
            total = spinner.spin_quarter_turns(pause_seconds=1.0, turns=2)

        self.assertEqual(total, 2_048)
        self.assertEqual(rotate.call_count, 2)
        self.assertEqual(pauses, [1.0, 1.0])

    def test_return_home_finishes_remaining_quarters(self) -> None:
        spinner, _pins = self.make_spinner()
        spinner._quarter_index = 2
        with mock.patch.object(
            spinner, "move_positioned", side_effect=[1_024, 1_024]
        ) as move:
            moved = spinner.return_home()

        self.assertEqual(moved, 2_048)
        self.assertEqual(spinner.quarter_index, 0)
        self.assertEqual([call.args[0] for call in move.call_args_list], [1_024] * 2)


if __name__ == "__main__":
    unittest.main()
