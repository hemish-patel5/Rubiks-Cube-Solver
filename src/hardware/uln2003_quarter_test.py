"""Quick ULN2003 test: rotate 90 degrees, pause one second, and repeat."""

import time

from stepper_spin import create_stepper_platform


def main() -> None:
    platform = create_stepper_platform()
    print("Repeating fast 90-degree turns. Press Ctrl+C to stop.")
    try:
        while True:
            platform.rotate_next_quarter()
            print("Moved 90 degrees; pausing for one second.")
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nTest stopped.")
    finally:
        platform.close()


if __name__ == "__main__":
    main()
