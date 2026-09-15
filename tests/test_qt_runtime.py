import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from vision.qt_runtime import configure_opencv_display


class QtRuntimeTests(unittest.TestCase):
    def test_backend_selection_for_bundled_plugins(self) -> None:
        cases = [
            ({"DISPLAY": ":0"}, False, "xcb"),
            ({"DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}, False, "xcb"),
            ({"DISPLAY": ":0", "QT_QPA_PLATFORM": "offscreen"}, False, "offscreen"),
            ({"DISPLAY": ":0", "QT_QPA_PLATFORM": "wayland"}, True, "wayland"),
            ({"QT_QPA_PLATFORM": "wayland"}, False, "wayland"),
        ]
        for environment, has_wayland, expected in cases:
            with self.subTest(environment=environment, has_wayland=has_wayland):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    platforms = root / "qt" / "plugins" / "platforms"
                    platforms.mkdir(parents=True)
                    (platforms / "libqxcb.so").touch()
                    if has_wayland:
                        (platforms / "libqwayland-generic.so").touch()
                    with mock.patch.dict(os.environ, environment, clear=True), mock.patch(
                        "vision.qt_runtime.sys.platform", "linux"
                    ), mock.patch(
                        "vision.qt_runtime.importlib.util.find_spec",
                        return_value=SimpleNamespace(origin=str(root / "__init__.py")),
                    ):
                        configure_opencv_display()
                        self.assertEqual(os.environ.get("QT_QPA_PLATFORM"), expected)
