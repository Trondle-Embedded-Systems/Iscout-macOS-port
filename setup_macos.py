"""
py2app build script – creates a native macOS .app bundle.

Usage:
    pip install py2app
    python setup_macos.py py2app
"""

from setuptools import setup
import os
import sys
import glob


def _find_libffi():
    """Locate libffi.8.dylib so py2app bundles it.

    The CPython _ctypes extension links against @rpath/libffi.8.dylib, but
    py2app (esp. with conda/miniconda Python) does not always pick it up,
    which causes the bundled app to fail at launch with:
        ImportError: ... Library not loaded: @rpath/libffi.8.dylib
    """
    candidates = []
    for prefix in (sys.prefix, sys.base_prefix):
        candidates.append(os.path.join(prefix, "lib", "libffi.8.dylib"))
        candidates += glob.glob(os.path.join(prefix, "lib", "libffi*.dylib"))
    for path in candidates:
        if os.path.exists(path):
            return path
    return None

APP = ["main.py"]
DATA_FILES = [
    ("data/Luts", [f"data/Luts/{f}" for f in os.listdir("data/Luts")]),
    ("assets", [f"assets/{f}" for f in os.listdir("assets") if os.path.isfile(f"assets/{f}")]),
    ("assets/sounds", [f"assets/sounds/{f}" for f in os.listdir("assets/sounds")]),
]
OPTIONS = {
    "argv_emulation": False,
    "iconfile": "assets/logo.png",
    "plist": {
        "CFBundleName": "iScout Mechanic-Ti VisualPlatform",
        "CFBundleDisplayName": "iScout Mechanic-Ti VisualPlatform",
        "CFBundleIdentifier": "com.mechanicti.iscout.visualplatform",
        "CFBundleVersion": "3.0.6",
        "CFBundleShortVersionString": "3.0.6",
        "NSCameraUsageDescription": "Required for thermal camera access.",
        "NSMicrophoneUsageDescription": "Required for video recording with audio.",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        # Required to enumerate iPhone Continuity cameras without a runtime
        # warning; harmless for the USB thermal camera.
        "NSCameraUseContinuityCameraDeviceType": True,
    },
    "packages": ["PyQt6", "cv2", "numpy"],
    "includes": [
        "PyQt6.QtMultimedia",
        "PyQt6.QtCore",
        "PyQt6.QtWidgets",
        "PyQt6.QtGui",
        # AVFoundation thermal-camera capture path (macOS).
        "objc",
        "AVFoundation",
        "Quartz",
        "CoreMedia",
        "Foundation",
        "dispatch",
    ],
    "excludes": ["tkinter", "wx"],
    "strip": True,
}

_libffi = _find_libffi()
if _libffi:
    OPTIONS["frameworks"] = [_libffi]
else:
    print(
        "WARNING: libffi.8.dylib not found near the Python prefix; the bundled "
        "app may fail to launch with a missing @rpath/libffi.8.dylib error.",
        file=sys.stderr,
    )

setup(
    name="iScout Mechanic-Ti VisualPlatform",
    version="3.0.6",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
