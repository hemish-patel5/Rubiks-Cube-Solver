"""Drive a STEP/DIR rotating platform from Raspberry Pi GPIO."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable, Protocol


BCM_DIR_PIN = 5
BCM_STEP_PIN = 6
STEPS_PER_REVOLUTION = 18_000
# Segment lengths derived from cumulative positions 5450, 9500, 13750, 18000.
CALIBRATED_QUARTER_STEPS = (5_450, 4_050, 4_250, 4_250)


class OutputPin(Protocol):
    def on(self) -> None: ...

    def off(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SpinSettings:
    # Defaults match the original fast Arduino profile. CLI options remain
    # available for slower mechanical testing when needed.
    start_rate: int = 100
    cruise_rate: int = 1_500
    acceleration_steps: int = 7_000
    pulse_high_us: int = 10
    settle_seconds: float = 0.0001

    def __post_init__(self) -> None:
        if self.start_rate <= 0:
            raise ValueError("start_rate must be greater than zero")
        if self.cruise_rate < self.start_rate:
            raise ValueError("cruise_rate must be at least start_rate")
        if self.acceleration_steps <= 0:
            raise ValueError("acceleration_steps must be greater than zero")
        if self.pulse_high_us <= 0:
            raise ValueError("pulse_high_us must be greater than zero")
        if self.pulse_high_us >= 1_000_000 // self.cruise_rate:
            raise ValueError("pulse_high_us must be shorter than the cruise period")
        if self.settle_seconds < 0:
            raise ValueError("settle_seconds must not be negative")


def step_period_us(acceleration_step: int, settings: SpinSettings) -> int:
    """Return the Arduino-equivalent linear ramp period for one pulse."""
    ramp_step = min(max(acceleration_step, 0), settings.acceleration_steps)
    rate_range = settings.cruise_rate - settings.start_rate
    rate = settings.start_rate + (
        rate_range * ramp_step // settings.acceleration_steps
    )
    return 1_000_000 // rate


class StepperSpinner:
    """Drive a motor continuously, or for a finite pulse count in tests."""

    def __init__(
        self,
        direction_pin: OutputPin,
        step_pin: OutputPin,
        settings: SpinSettings,
        clockwise_high: bool = False,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.direction_pin = direction_pin
        self.step_pin = step_pin
        self.settings = settings
        self.clockwise_high = clockwise_high
        self.sleep = sleep

    def spin(self, steps: int | None = None) -> int:
        """Rotate clockwise until interrupted, or until ``steps`` are emitted."""
        if steps is not None and steps < 0:
            raise ValueError("steps must not be negative")

        total_steps = 0
        acceleration_step = 0
        self.step_pin.off()
        if self.clockwise_high:
            self.direction_pin.on()
        else:
            self.direction_pin.off()
        # Give the platform time to stop moving before the acceleration ramp.
        self.sleep(self.settings.settle_seconds)

        try:
            while steps is None or total_steps < steps:
                period_us = step_period_us(acceleration_step, self.settings)
                self.step_pin.on()
                self.sleep(self.settings.pulse_high_us / 1_000_000)
                self.step_pin.off()
                self.sleep(
                    (period_us - self.settings.pulse_high_us) / 1_000_000
                )

                total_steps += 1
                if acceleration_step < self.settings.acceleration_steps:
                    acceleration_step += 1
                if total_steps % STEPS_PER_REVOLUTION == 0:
                    print(
                        f"Completed revolutions: {total_steps // STEPS_PER_REVOLUTION}"
                        f" | total pulses: {total_steps}",
                        flush=True,
                    )
        finally:
            self.step_pin.off()

        return total_steps

    def spin_quarter_turns(
        self, pause_seconds: float = 1.0, turns: int | None = None
    ) -> int:
        """Repeat calibrated 90-degree moves with a pause after every move."""
        if pause_seconds < 0:
            raise ValueError("pause_seconds must not be negative")
        if turns is not None and turns < 0:
            raise ValueError("turns must not be negative")

        total_steps = 0
        turn_index = 0
        while turns is None or turn_index < turns:
            segment_steps = CALIBRATED_QUARTER_STEPS[
                turn_index % len(CALIBRATED_QUARTER_STEPS)
            ]
            # Restart the acceleration ramp after each stationary position.
            total_steps += self.spin(segment_steps)
            turn_index += 1
            angle = (turn_index % 4) * 90 or 360
            print(
                f"Position: {angle} degrees"
                f" | completed revolutions: {turn_index // 4}"
                f" | total pulses: {total_steps}",
                flush=True,
            )
            self.sleep(pause_seconds)

        return total_steps

    def close(self) -> None:
        self.step_pin.off()
        self.step_pin.close()
        self.direction_pin.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir-pin", type=int, default=BCM_DIR_PIN)
    parser.add_argument("--step-pin", type=int, default=BCM_STEP_PIN)
    parser.add_argument("--start-rate", type=int, default=100)
    parser.add_argument("--cruise-rate", type=int, default=1_500)
    parser.add_argument("--acceleration-steps", type=int, default=7_000)
    parser.add_argument("--pulse-high-us", type=int, default=10)
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=0.0001,
        help="pause after setting direction (default: 0.0001 seconds)",
    )
    parser.add_argument(
        "--clockwise-level",
        choices=("low", "high"),
        default="low",
        help="DIR level that produces clockwise rotation (default: low)",
    )
    parser.add_argument(
        "--steps",
        type=int,
        help="diagnostic: make one movement with this many pulses, then stop",
    )
    parser.add_argument(
        "--continuous",
        action="store_true",
        help="spin without quarter-turn pauses (the previous behavior)",
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="pause after each calibrated 90-degree turn (default: 1.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = SpinSettings(
        start_rate=args.start_rate,
        cruise_rate=args.cruise_rate,
        acceleration_steps=args.acceleration_steps,
        pulse_high_us=args.pulse_high_us,
        settle_seconds=args.settle_seconds,
    )

    try:
        from gpiozero import OutputDevice
    except ImportError as exc:
        raise SystemExit(
            "GPIO Zero is unavailable. Install requirements.txt on the Raspberry Pi."
        ) from exc

    direction_pin = OutputDevice(args.dir_pin, active_high=True, initial_value=False)
    step_pin = OutputDevice(args.step_pin, active_high=True, initial_value=False)
    spinner = StepperSpinner(
        direction_pin,
        step_pin,
        settings,
        clockwise_high=args.clockwise_level == "high",
    )

    print(f"Clockwise rotation: BCM DIR={args.dir_pin}, BCM STEP={args.step_pin}")
    print(
        f"Ramping from {settings.start_rate} to {settings.cruise_rate} "
        f"pulses/s over {settings.acceleration_steps} pulses."
    )
    print("Press Ctrl+C to stop safely.")
    try:
        if args.steps is not None:
            spinner.spin(args.steps)
        elif args.continuous:
            spinner.spin()
        else:
            print(
                f"Moving in calibrated 90-degree segments with a "
                f"{args.pause_seconds:g}-second pause."
            )
            spinner.spin_quarter_turns(args.pause_seconds)
    except KeyboardInterrupt:
        print("\nMotor stopped.")
    finally:
        spinner.close()


if __name__ == "__main__":
    main()
