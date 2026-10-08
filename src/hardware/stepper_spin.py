"""Continuously spin a STEP/DIR stepper driver from Raspberry Pi GPIO."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable, Protocol


BCM_DIR_PIN = 5
BCM_STEP_PIN = 6
STEPS_PER_REVOLUTION = 18_000


class OutputPin(Protocol):
    def on(self) -> None: ...

    def off(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SpinSettings:
    # Gentle defaults reduce shock loading in the geared platform. They can be
    # raised with CLI options after the mechanism runs without slipping.
    start_rate: int = 20
    cruise_rate: int = 250
    acceleration_steps: int = 2_500
    pulse_high_us: int = 100
    settle_seconds: float = 0.25

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

    def close(self) -> None:
        self.step_pin.off()
        self.step_pin.close()
        self.direction_pin.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir-pin", type=int, default=BCM_DIR_PIN)
    parser.add_argument("--step-pin", type=int, default=BCM_STEP_PIN)
    parser.add_argument("--start-rate", type=int, default=20)
    parser.add_argument("--cruise-rate", type=int, default=250)
    parser.add_argument("--acceleration-steps", type=int, default=2_500)
    parser.add_argument("--pulse-high-us", type=int, default=100)
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=0.25,
        help="pause before stepping so the platform can settle (default: 0.25)",
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
        help="stop after this many pulses; omitted means spin continuously",
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

    print(
        f"Continuous clockwise rotation: BCM DIR={args.dir_pin}, "
        f"BCM STEP={args.step_pin}"
    )
    print(
        f"Ramping from {settings.start_rate} to {settings.cruise_rate} "
        f"pulses/s over {settings.acceleration_steps} pulses."
    )
    print("Press Ctrl+C to stop safely.")
    try:
        spinner.spin(args.steps)
    except KeyboardInterrupt:
        print("\nMotor stopped.")
    finally:
        spinner.close()


if __name__ == "__main__":
    main()
