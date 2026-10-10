"""Drive a four-input ULN2003 stepper platform from Raspberry Pi GPIO."""

from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from typing import Callable, Protocol, Sequence


BCM_IN_PINS = (17, 18, 27, 22)
STEPS_PER_REVOLUTION = 4_096
CALIBRATED_QUARTER_STEPS = (1_024, 1_024, 1_024, 1_024)
DEFAULT_QUARTER_RAMP_STEPS = 128

# Eight-state half-step sequence for a 28BYJ-48-style unipolar motor. Reversing
# the tuple reverses the motor direction without changing the wiring.
HALF_STEP_SEQUENCE = (
    (1, 0, 0, 0),
    (1, 1, 0, 0),
    (0, 1, 0, 0),
    (0, 1, 1, 0),
    (0, 0, 1, 0),
    (0, 0, 1, 1),
    (0, 0, 0, 1),
    (1, 0, 0, 1),
)


class OutputPin(Protocol):
    def on(self) -> None: ...

    def off(self) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SpinSettings:
    """Speed profile expressed in ULN2003 half-steps per second."""

    start_rate: int = 300
    cruise_rate: int = 900
    acceleration_steps: int = 128

    def __post_init__(self) -> None:
        if self.start_rate <= 0:
            raise ValueError("start_rate must be greater than zero")
        if self.cruise_rate < self.start_rate:
            raise ValueError("cruise_rate must be at least start_rate")
        if self.acceleration_steps <= 0:
            raise ValueError("acceleration_steps must be greater than zero")


def step_period_us(acceleration_step: int, settings: SpinSettings) -> int:
    """Return the period for one accelerating half-step."""
    ramp_step = min(max(acceleration_step, 0), settings.acceleration_steps)
    rate_range = settings.cruise_rate - settings.start_rate
    rate = settings.start_rate + (
        rate_range * ramp_step // settings.acceleration_steps
    )
    return 1_000_000 // rate


def positioned_step_period_us(
    step_index: int,
    total_steps: int,
    settings: SpinSettings,
    ramp_steps: int = DEFAULT_QUARTER_RAMP_STEPS,
) -> int:
    """Return a symmetric accelerate/decelerate period for a positioned move."""
    if total_steps <= 0:
        raise ValueError("total_steps must be greater than zero")
    if not 0 <= step_index < total_steps:
        raise ValueError("step_index must be within the movement")
    if ramp_steps <= 0:
        raise ValueError("ramp_steps must be greater than zero")

    progress = min(step_index, total_steps - step_index - 1, ramp_steps)
    rate_range = settings.cruise_rate - settings.start_rate
    rate = settings.start_rate + rate_range * progress // ramp_steps
    return 1_000_000 // rate


def quarter_steps(steps_per_revolution: int) -> tuple[int, int, int, int]:
    """Split one configured revolution into four integer quarter turns."""
    if steps_per_revolution < 4:
        raise ValueError("steps_per_revolution must be at least four")
    base, remainder = divmod(steps_per_revolution, 4)
    return tuple(base + int(index < remainder) for index in range(4))


class ULN2003Stepper:
    """Drive a four-input ULN2003 board with an eight-state half-step sequence."""

    def __init__(
        self,
        pins: Sequence[OutputPin],
        settings: SpinSettings,
        clockwise: bool = True,
        quarter_ramp_steps: int = DEFAULT_QUARTER_RAMP_STEPS,
        steps_per_revolution: int = STEPS_PER_REVOLUTION,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if len(pins) != 4:
            raise ValueError("ULN2003 control requires exactly four output pins")
        if quarter_ramp_steps <= 0:
            raise ValueError("quarter_ramp_steps must be greater than zero")

        self.pins = tuple(pins)
        self.settings = settings
        self.clockwise = clockwise
        self.quarter_ramp_steps = quarter_ramp_steps
        self.quarter_step_counts = quarter_steps(steps_per_revolution)
        self.sleep = sleep
        self._quarter_index = 0
        self._phase_index = 0
        self.release()

    @property
    def quarter_index(self) -> int:
        """Current position: 0=green, 1=red, 2=blue, 3=orange."""
        return self._quarter_index

    def _energize(self, state: tuple[int, int, int, int]) -> None:
        for pin, active in zip(self.pins, state):
            pin.on() if active else pin.off()

    def _step_once(self, period_us: int) -> None:
        sequence_index = self._phase_index if self.clockwise else -self._phase_index
        self._energize(HALF_STEP_SEQUENCE[sequence_index % len(HALF_STEP_SEQUENCE)])
        self._phase_index = (self._phase_index + 1) % len(HALF_STEP_SEQUENCE)
        self.sleep(period_us / 1_000_000)

    def release(self) -> None:
        """Remove power from every motor coil."""
        for pin in self.pins:
            pin.off()

    def spin(self, steps: int | None = None) -> int:
        """Rotate until interrupted, or emit a finite number of half-steps."""
        if steps is not None and steps < 0:
            raise ValueError("steps must not be negative")

        total_steps = 0
        acceleration_step = 0
        revolution_steps = sum(self.quarter_step_counts)
        while steps is None or total_steps < steps:
            self._step_once(step_period_us(acceleration_step, self.settings))
            total_steps += 1
            acceleration_step = min(
                acceleration_step + 1, self.settings.acceleration_steps
            )
            if total_steps % revolution_steps == 0:
                print(
                    f"Completed revolutions: {total_steps // revolution_steps}"
                    f" | total half-steps: {total_steps}",
                    flush=True,
                )
        return total_steps

    def move_positioned(self, steps: int) -> int:
        """Move an exact half-step count with acceleration and deceleration."""
        if steps <= 0:
            raise ValueError("steps must be greater than zero")
        for step_index in range(steps):
            self._step_once(
                positioned_step_period_us(
                    step_index,
                    steps,
                    self.settings,
                    self.quarter_ramp_steps,
                )
            )
        return steps

    def rotate_next_quarter(self) -> int:
        """Move clockwise to the next camera position."""
        steps = self.quarter_step_counts[self._quarter_index]
        moved = self.move_positioned(steps)
        self._quarter_index = (self._quarter_index + 1) % 4
        return moved

    def return_home(self) -> int:
        """Complete clockwise quarter turns until green faces the camera."""
        moved = 0
        while self._quarter_index != 0:
            moved += self.rotate_next_quarter()
        return moved

    def spin_quarter_turns(
        self, pause_seconds: float = 1.0, turns: int | None = None
    ) -> int:
        """Repeat 90-degree movements with a pause after every movement."""
        if pause_seconds < 0:
            raise ValueError("pause_seconds must not be negative")
        if turns is not None and turns < 0:
            raise ValueError("turns must not be negative")

        total_steps = 0
        turn_index = 0
        while turns is None or turn_index < turns:
            total_steps += self.rotate_next_quarter()
            turn_index += 1
            angle = (turn_index % 4) * 90 or 360
            print(
                f"Position: {angle} degrees"
                f" | completed revolutions: {turn_index // 4}"
                f" | total half-steps: {total_steps}",
                flush=True,
            )
            self.sleep(pause_seconds)
        return total_steps

    def close(self) -> None:
        self.release()
        for pin in self.pins:
            pin.close()


def create_stepper_platform(
    in1_pin: int = BCM_IN_PINS[0],
    in2_pin: int = BCM_IN_PINS[1],
    in3_pin: int = BCM_IN_PINS[2],
    in4_pin: int = BCM_IN_PINS[3],
    clockwise: bool = True,
    start_rate: int = 300,
    cruise_rate: int = 900,
    quarter_ramp_steps: int = DEFAULT_QUARTER_RAMP_STEPS,
    steps_per_revolution: int = STEPS_PER_REVOLUTION,
) -> ULN2003Stepper:
    """Create a ULN2003 platform using Raspberry Pi BCM pin numbers."""
    try:
        from gpiozero import OutputDevice
    except ImportError as exc:
        raise RuntimeError(
            "GPIO Zero is unavailable; install requirements.txt on the Raspberry Pi"
        ) from exc

    pins: list[OutputPin] = []
    try:
        for pin_number in (in1_pin, in2_pin, in3_pin, in4_pin):
            pins.append(
                OutputDevice(pin_number, active_high=True, initial_value=False)
            )
    except Exception:
        for pin in pins:
            pin.close()
        raise

    return ULN2003Stepper(
        pins,
        SpinSettings(start_rate=start_rate, cruise_rate=cruise_rate),
        clockwise=clockwise,
        quarter_ramp_steps=quarter_ramp_steps,
        steps_per_revolution=steps_per_revolution,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in1-pin", type=int, default=BCM_IN_PINS[0])
    parser.add_argument("--in2-pin", type=int, default=BCM_IN_PINS[1])
    parser.add_argument("--in3-pin", type=int, default=BCM_IN_PINS[2])
    parser.add_argument("--in4-pin", type=int, default=BCM_IN_PINS[3])
    parser.add_argument("--start-rate", type=int, default=300)
    parser.add_argument("--cruise-rate", type=int, default=900)
    parser.add_argument("--acceleration-steps", type=int, default=128)
    parser.add_argument("--ramp-steps", type=int, default=128)
    parser.add_argument("--steps-per-revolution", type=int, default=4_096)
    parser.add_argument(
        "--direction",
        choices=("clockwise", "counterclockwise"),
        default="clockwise",
    )
    parser.add_argument(
        "--steps",
        type=int,
        help="diagnostic: make one movement with this many half-steps, then stop",
    )
    parser.add_argument(
        "--continuous", action="store_true", help="spin without quarter-turn pauses"
    )
    parser.add_argument(
        "--pause-seconds",
        type=float,
        default=1.0,
        help="pause after each 90-degree turn (default: 1.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    spinner = create_stepper_platform(
        in1_pin=args.in1_pin,
        in2_pin=args.in2_pin,
        in3_pin=args.in3_pin,
        in4_pin=args.in4_pin,
        clockwise=args.direction == "clockwise",
        start_rate=args.start_rate,
        cruise_rate=args.cruise_rate,
        quarter_ramp_steps=args.ramp_steps,
        steps_per_revolution=args.steps_per_revolution,
    )
    spinner.settings = SpinSettings(
        start_rate=args.start_rate,
        cruise_rate=args.cruise_rate,
        acceleration_steps=args.acceleration_steps,
    )

    print(
        "ULN2003 inputs: "
        f"IN1=GPIO{args.in1_pin}, IN2=GPIO{args.in2_pin}, "
        f"IN3=GPIO{args.in3_pin}, IN4=GPIO{args.in4_pin}"
    )
    print(
        f"Direction: {args.direction}; speed: {args.start_rate} to "
        f"{args.cruise_rate} half-steps/s. Press Ctrl+C to stop safely."
    )
    try:
        if args.steps is not None:
            spinner.spin(args.steps)
        elif args.continuous:
            spinner.spin()
        else:
            spinner.spin_quarter_turns(args.pause_seconds)
    except KeyboardInterrupt:
        print("\nMotor stopped.")
    finally:
        spinner.close()


if __name__ == "__main__":
    main()
