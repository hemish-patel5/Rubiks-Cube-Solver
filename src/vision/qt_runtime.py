"""Select a supported Qt display backend before importing OpenCV."""

import importlib.util
import os
import sys
from pathlib import Path


def configure_opencv_display() -> None:
    """Use XWayland when OpenCV bundles xcb but no Wayland plugin.

    Keep other explicit backend choices and native Wayland installations intact.
    A desktop/X11 connection is still required; this does not create a display.
    """
    if not sys.platform.startswith("linux") or not os.environ.get("DISPLAY"):
        return
    preference = os.environ.get("QT_QPA_PLATFORM", "")
    if preference and preference not in {"wayland", "wayland-egl"}:
        return
    spec = importlib.util.find_spec("cv2")
    if spec is None or spec.origin is None:
        return
    platforms = Path(spec.origin).parent / "qt" / "plugins" / "platforms"
    if (platforms / "libqxcb.so").is_file() and not any(
        platforms.glob("*wayland*.so")
    ):
        os.environ["QT_QPA_PLATFORM"] = "xcb"
