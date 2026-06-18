"""Camera parameter settings dialog."""

from __future__ import annotations
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox,
    QVBoxLayout, QHBoxLayout, QLabel, QSlider,
)
from PyQt6.QtCore import Qt
from ..thermal_processor import CameraParams


LANGUAGES = ["English", "中文", "Español", "Русский", "中文(繁體)"]
CAMERA_MODELS = ["CA09B", "CA09D", "CA30D", "iScout"]


class SettingsDialog(QDialog):
    def __init__(self, params: CameraParams, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(380)
        self._params = CameraParams(
            emissivity=params.emissivity,
            distance=params.distance,
            humidity=params.humidity,
            altitude=params.altitude,
            temp_min=params.temp_min,
            temp_max=params.temp_max,
            auto_range=params.auto_range,
        )
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── Measurement conditions ────────────────────────────────────
        grp_meas = QGroupBox("Measurement Conditions")
        form = QFormLayout(grp_meas)

        self._emi = QDoubleSpinBox()
        self._emi.setRange(0.01, 1.00)
        self._emi.setSingleStep(0.01)
        self._emi.setDecimals(2)
        self._emi.setValue(self._params.emissivity)
        self._emi.setToolTip(
            "Emissivity (0.01–1.00). Most objects: 0.95. "
            "Shiny metal: 0.05–0.20."
        )
        form.addRow("Emissivity:", self._emi)

        self._dist = QDoubleSpinBox()
        self._dist.setRange(0.1, 100.0)
        self._dist.setSingleStep(0.1)
        self._dist.setDecimals(1)
        self._dist.setSuffix(" m")
        self._dist.setValue(self._params.distance)
        form.addRow("Distance:", self._dist)

        self._hum = QDoubleSpinBox()
        self._hum.setRange(0.0, 1.0)
        self._hum.setSingleStep(0.01)
        self._hum.setDecimals(2)
        self._hum.setValue(self._params.humidity)
        self._hum.setToolTip("Relative humidity (0.00–1.00)")
        form.addRow("Humidity:", self._hum)

        self._alt = QDoubleSpinBox()
        self._alt.setRange(0.0, 9000.0)
        self._alt.setSingleStep(10.0)
        self._alt.setDecimals(0)
        self._alt.setSuffix(" m")
        self._alt.setValue(self._params.altitude)
        form.addRow("Altitude:", self._alt)

        layout.addWidget(grp_meas)

        # ── Temperature range ─────────────────────────────────────────
        grp_range = QGroupBox("Temperature Range")
        form2 = QFormLayout(grp_range)

        self._auto_range = QCheckBox("Auto range")
        self._auto_range.setChecked(self._params.auto_range)
        self._auto_range.stateChanged.connect(self._on_auto_changed)
        form2.addRow(self._auto_range)

        self._t_min = QDoubleSpinBox()
        self._t_min.setRange(-40.0, 500.0)
        self._t_min.setSingleStep(1.0)
        self._t_min.setSuffix(" °C")
        self._t_min.setValue(self._params.temp_min)
        self._t_min.setEnabled(not self._params.auto_range)
        form2.addRow("Min temp:", self._t_min)

        self._t_max = QDoubleSpinBox()
        self._t_max.setRange(-40.0, 2000.0)
        self._t_max.setSingleStep(1.0)
        self._t_max.setSuffix(" °C")
        self._t_max.setValue(self._params.temp_max)
        self._t_max.setEnabled(not self._params.auto_range)
        form2.addRow("Max temp:", self._t_max)

        layout.addWidget(grp_range)

        # ── Display options ───────────────────────────────────────────
        grp_disp = QGroupBox("Display")
        form3 = QFormLayout(grp_disp)

        self._show_max = QCheckBox("Show MAX crosshair")
        self._show_max.setChecked(True)
        form3.addRow(self._show_max)

        self._show_min = QCheckBox("Show MIN crosshair")
        self._show_min.setChecked(True)
        form3.addRow(self._show_min)

        self._show_center = QCheckBox("Show center temperature")
        self._show_center.setChecked(True)
        form3.addRow(self._show_center)

        self._lang = QComboBox()
        self._lang.addItems(LANGUAGES)
        form3.addRow("Language:", self._lang)

        layout.addWidget(grp_disp)

        # ── OK / Cancel ───────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_auto_changed(self, state: int) -> None:
        enabled = state == 0  # unchecked → manual range
        self._t_min.setEnabled(enabled)
        self._t_max.setEnabled(enabled)

    def get_params(self) -> CameraParams:
        p = self._params
        p.emissivity = self._emi.value()
        p.distance = self._dist.value()
        p.humidity = self._hum.value()
        p.altitude = self._alt.value()
        p.auto_range = self._auto_range.isChecked()
        p.temp_min = self._t_min.value()
        p.temp_max = self._t_max.value()
        return p

    def show_max(self) -> bool:
        return self._show_max.isChecked()

    def show_min(self) -> bool:
        return self._show_min.isChecked()

    def show_center(self) -> bool:
        return self._show_center.isChecked()
