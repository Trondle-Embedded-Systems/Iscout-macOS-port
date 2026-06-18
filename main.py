#!/usr/bin/env python3
"""
iScout Mechanic-Ti VisualPlatformSetUp v3.0.6 – macOS Port
Entry point.
"""

import sys
import os

# Allow running from the project root without installing
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication, QSplashScreen
from PyQt6.QtGui import QPixmap, QColor, QPainter, QFont
from PyQt6.QtCore import Qt, QTimer

from src.main_window import MainWindow, _ASSETS


def _make_splash() -> QSplashScreen:
    pm = QPixmap(520, 300)
    pm.fill(QColor("#1e1e1e"))
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    # Load logo
    logo_path = os.path.join(_ASSETS, "logo.png")
    if os.path.isfile(logo_path):
        logo = QPixmap(logo_path).scaled(
            96, 96,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(210, 30, logo)

    title_font = QFont("Arial", 18, QFont.Weight.Bold)
    painter.setFont(title_font)
    painter.setPen(QColor("#f5c518"))
    painter.drawText(pm.rect().adjusted(0, 140, 0, 0),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                     "iScout Mechanic-Ti")

    sub_font = QFont("Arial", 11)
    painter.setFont(sub_font)
    painter.setPen(QColor("#aaaaaa"))
    painter.drawText(pm.rect().adjusted(0, 175, 0, 0),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                     "VisualPlatformSetUp  v3.0.6  –  macOS Port")

    painter.setPen(QColor("#666666"))
    small_font = QFont("Arial", 9)
    painter.setFont(small_font)
    painter.drawText(pm.rect().adjusted(0, 210, 0, 0),
                     Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                     "Thermal Imaging & Analysis Platform")

    painter.end()
    splash = QSplashScreen(pm, Qt.WindowType.SplashScreen)
    splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
    return splash


def main() -> int:
    # macOS: allow Qt to use the native look
    if sys.platform == "darwin":
        os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

    app = QApplication(sys.argv)
    app.setApplicationName("iScout Mechanic-Ti VisualPlatform")
    app.setApplicationVersion("3.0.6")
    app.setOrganizationName("Mechanic-Ti")
    app.setOrganizationDomain("mechanic-ti.com")

    splash = _make_splash()
    splash.show()
    app.processEvents()

    window = MainWindow()

    # Show main window after a brief splash
    def _show_main():
        splash.finish(window)
        window.show()
        window.raise_()

    QTimer.singleShot(1800, _show_main)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
