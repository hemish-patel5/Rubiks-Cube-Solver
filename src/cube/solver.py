"""Small Kociemba adapter for solver-ready 3x3 facelet strings."""

from __future__ import annotations

from collections import Counter


FACE_ORDER = "URFDLB"
SOLVED_STATE = "".join(face * 9 for face in FACE_ORDER)


class InvalidCubeState(ValueError):
    """Raised when a facelet string cannot describe a physical 3x3 cube."""


def _check_facelets(facelets: str) -> None:
    if len(facelets) != 54:
        raise InvalidCubeState("expected exactly 54 facelets")
    counts = Counter(facelets)
    if set(counts) != set(FACE_ORDER) or any(counts[face] != 9 for face in FACE_ORDER):
        raise InvalidCubeState("expected exactly nine U, R, F, D, L, and B facelets")
    if "".join(facelets[index] for index in (4, 13, 22, 31, 40, 49)) != FACE_ORDER:
        raise InvalidCubeState("centre facelets must remain in URFDLB order")


def solve_3x3(facelets: str) -> list[str]:
    """Validate and solve a 3x3 state, returning Singmaster move tokens."""
    _check_facelets(facelets)
    if facelets == SOLVED_STATE:
        return []

    try:
        import kociemba

        solution = kociemba.solve(facelets)
    except (ImportError, ValueError) as exc:
        if isinstance(exc, ImportError):
            raise RuntimeError(
                "Kociemba is unavailable; install requirements.txt"
            ) from exc
        raise InvalidCubeState("the stickers form an impossible cube state") from exc
    return solution.split() if solution else []
