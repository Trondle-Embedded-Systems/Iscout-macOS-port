"""Temperature alarm configuration dialog."""

from __future__ import annotations
import os
from dataclasses import dataclass
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFormLayout, QGroupBox,
    QDoubleSpinBox, QCheckBox, QComboBox, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton,
)
from PyQt6.QtCore import Qt
from PyQt6.QtMultimedia import QSoundEffect
from PyQt6.QtCore import QUrl


@dataclass
class AlarmSettings:
    high_enabled: bool = False
    high_temp: float = 60.0
    low_enabled: bool = False
    low_temp: float = -10.0
    sound_index: int = 0        # 0=none, 1-8=WAV files
    repeat_interval: int = 5    # seconds between repeats


SOUND_NAMES = [
    "None",
    "01 - Chime",
    "02 - Ding",
    "03 - Falling",
    "04 - Rising",
    "05 - Dry",
    "06 - Dry 2",
    "07 - Ring",
    "08 - Bell",
]


class AlarmDialog(QDialog):
    def __init__(self, settings: AlarmSettings,
                 sounds_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alarm Settings")
        self.setMinimumWidth(340)
        self._settings = AlarmSettings(
            high_enabled=settings.high_enabled,
            high_temp=settings.high_temp,
            low_enabled=settings.low_enabled,
            low_temp=settings.low_temp,
            sound_index=settings.sound_index,
            repeat_interval=settings.repeat_interval,
        )
        self._sounds_dir = sounds_dir
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # ── High temperature alarm ────────────────────────────────────
        grp_high = QGroupBox("High Temperature Alarm")
        form_h = QFormLayout(grp_high)

        self._high_en = QCheckBox("Enable high alarm")
        self._high_en.setChecked(self._settings.high_enabled)
        form_h.addRow(self._high_en)

        self._high_val = QDoubleSpinBox()
        self._high_val.setRange(-40.0, 2000.0)
        self._high_val.setSingleStep(0.5)
        self._high_val.setSuffix(" °C")
        self._high_val.setValue(self._settings.high_temp)
        form_h.addRow("Trigger above:", self._high_val)

        layout.addWidget(grp_high)

        # ── Low temperature alarm ─────────────────────────────────────
        grp_low = QGroupBox("Low Temperature Alarm")
        form_l = QFormLayout(grp_low)

        self._low_en = QCheckBox("Enable low alarm")
        self._low_en.setChecked(self._settings.low_enabled)
        form_l.addRow(self._low_en)

        self._low_val = QDoubleSpinBox()
        self._low_val.setRange(-273.0, 2000.0)
        self._low_val.setSingleStep(0.5)
        self._low_val.setSuffix(" °C")
        self._low_val.setValue(self._settings.low_temp)
        form_l.addRow("Trigger below:", self._low_val)

        layout.addWidget(grp_low)

        # ── Sound & timing ────────────────────────────────────────────
        grp_snd = QGroupBox("Alert Sound")
        form_s = QFormLayout(grp_snd)

        self._sound_combo = QComboBox()
        self._sound_combo.addItems(SOUND_NAMES)
        self._sound_combo.setCurrentIndex(self._settings.sound_index)
        form_s.addRow("Sound:", self._sound_combo)

        test_row = QHBoxLayout()
        btn_test = QPushButton("Test Sound")
        btn_test.clicked.connect(self._test_sound)
        test_row.addWidget(btn_test)
        test_row.addStretch()
        form_s.addRow(test_row)

        self._interval = QDoubleSpinBox()
        self._interval.setRange(1, 300)
        self._interval.setSingleStep(1)
        self._interval.setDecimals(0)
        self._interval.setSuffix(" s")
        self._interval.setValue(self._settings.repeat_interval)
        form_s.addRow("Repeat interval:", self._interval)

        layout.addWidget(grp_snd)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _test_sound(self) -> None:
        idx = self._sound_combo.currentIndex()
        if idx == 0:
            return
        wav_name = f"0{idx}-{SOUND_NAMES[idx].split(' - ', 1)[-1].replace(' ', '')}.wav"
        # Map combo index to actual file names
        files = sorted(
            [f for f in os.listdir(self._sounds_dir) if f.endswith(".wav")]
        ) if os.path.isdir(self._sounds_dir) else []
        if idx - 1 < len(files):
            path = os.path.join(self._sounds_dir, files[idx - 1])
            sfx = QSoundEffect(self)
            sfx.setSource(QUrl.fromLocalFile(path))
            sfx.play()

    def get_settings(self) -> AlarmSettings:
        s = self._settings
        s.high_enabled = self._high_en.isChecked()
        s.high_temp = self._high_val.value()
        s.low_enabled = self._low_en.isChecked()
        s.low_temp = self._low_val.value()
        s.sound_index = self._sound_combo.currentIndex()
        s.repeat_interval = int(self._interval.value())
        return s
