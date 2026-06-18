"""About dialog for iScout Mechanic-Ti VisualPlatform."""

from __future__ import annotations
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtCore import Qt


APP_VERSION = "3.0.6"
APP_NAME = "iScout Mechanic-Ti VisualPlatformSetUp"


class AboutDialog(QDialog):
    def __init__(self, assets_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About")
        self.setFixedSize(400, 260)
        self._assets_dir = assets_dir
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Logo + title row
        row = QHBoxLayout()
        logo_label = QLabel()
        logo_path = os.path.join(self._assets_dir, "logo.png")
        if os.path.isfile(logo_path):
            pm = QPixmap(logo_path).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pm)
        row.addWidget(logo_label)

        title_col = QVBoxLayout()
        name_lbl = QLabel(APP_NAME)
        name_font = QFont()
        name_font.setBold(True)
        name_font.setPointSize(12)
        name_lbl.setFont(name_font)
        title_col.addWidget(name_lbl)

        ver_lbl = QLabel(f"Version {APP_VERSION}  (macOS Port)")
        title_col.addWidget(ver_lbl)
        title_col.addStretch()
        row.addLayout(title_col)
        row.addStretch()
        layout.addLayout(row)

        # Divider line
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("QFrame { color: #555; }")
        layout.addWidget(line)

        # Info block
        info_lines = [
            "Thermal Imaging & Analysis Platform",
            "Supports Mechanic-Ti CA09B / CA09D / CA30D / iScout cameras",
            "",
            "macOS port built with Python + PyQt6 + OpenCV",
            "Original application © Mechanic-Ti / DYT",
        ]
        for txt in info_lines:
            lbl = QLabel(txt)
            lbl.setStyleSheet("color: #ccc;")
            layout.addWidget(lbl)

        layout.addStretch()

        # Close button
        btn = QPushButton("Close")
        btn.clicked.connect(self.accept)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
