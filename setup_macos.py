"""
py2app build script – creates a native macOS .app bundle.

Usage:
    pip install py2app
    python setup_macos.py py2app
"""

from setuptools import setup
import os

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
    },
    "packages": ["PyQt6", "cv2", "numpy"],
    "includes": [
        "PyQt6.QtMultimedia",
        "PyQt6.QtCore",
        "PyQt6.QtWidgets",
        "PyQt6.QtGui",
    ],
    "excludes": ["tkinter", "wx"],
    "strip": True,
}

setup(
    name="iScout Mechanic-Ti VisualPlatform",
    version="3.0.6",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
