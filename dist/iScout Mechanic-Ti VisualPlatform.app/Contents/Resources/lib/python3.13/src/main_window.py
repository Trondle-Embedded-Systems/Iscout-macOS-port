"""
Main application window for iScout Mechanic-Ti VisualPlatformSetUp (macOS port).

Layout
------
  ┌──────────────────────────────────────────────────────────────────┐
  │  Toolbar  (camera selector, connect, tool buttons, etc.)         │
  ├─────────────────────────────────────┬────────────────────────────┤
  │                                     │  Color scale bar           │
  │  CameraWidget  (live thermal feed)  │  LUT palette selector      │
  │                                     │  Temperature stats panel   │
  │                                     │  Point measurement list    │
  ├─────────────────────────────────────┴────────────────────────────┤
  │  Status bar                                                       │
  └──────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations
import os
import sys
import time
import numpy as np
import cv2

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QToolBar, QStatusBar, QLabel, QComboBox, QPushButton,
    QSlider, QSizePolicy, QSplitter, QGroupBox, QScrollArea,
    QFrame, QFileDialog, QMessageBox, QSpacerItem,
    QApplication,
)
from PyQt6.QtGui import (
    QAction, QIcon, QPixmap, QColor, QPainter, QImage, QFont,
    QPen, QKeySequence,
)
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSlot

from .lut_manager import LutManager, LUT_NAMES
from .thermal_processor import ThermalProcessor, CameraParams
from .camera_widget import CameraWidget
from .analysis_tools import ToolMode
from .recorder import Recorder
from .dialogs.settings_dialog import SettingsDialog
from .dialogs.alarm_dialog import AlarmDialog, AlarmSettings
from .dialogs.about_dialog import AboutDialog


_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ASSETS = os.path.join(_HERE, "assets")
_DATA = os.path.join(_HERE, "data")
_CAPTURES = os.path.join(_HERE, "captures")
_SOUNDS = os.path.join(_ASSETS, "sounds")

CAMERA_MODELS = ["CA09B", "CA09D", "CA30D", "iScout"]
_DARK_BG = "#1e1e1e"
_PANEL_BG = "#2a2a2a"
_ACCENT = "#f5c518"  # Mechanic-Ti yellow


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("iScout Mechanic-Ti VisualPlatformSetUp v3.0.6")
        self.setMinimumSize(1000, 650)
        self.resize(1280, 780)

        # Core objects
        self._params = CameraParams()
        self._lut_mgr = LutManager(os.path.join(_DATA, "Luts"))
        self._processor = ThermalProcessor(self._params)
        self._camera_widget = CameraWidget(self._lut_mgr, self._processor)
        self._recorder = Recorder(_CAPTURES)
        self._alarm = AlarmSettings()
        self._alarm_player: QTimer = QTimer(self)
        self._alarm_player.timeout.connect(self._play_alarm_sound)

        self._build_ui()
        self._connect_signals()
        self._apply_dark_theme()

        # Start in demo mode so the UI shows something immediately
        self._camera_widget.start_demo()
        self._update_lut_scale()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # ── Main toolbar ──────────────────────────────────────────────
        self._build_toolbar()

        # ── Central widget ────────────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        h_layout = QHBoxLayout(central)
        h_layout.setContentsMargins(4, 4, 4, 4)
        h_layout.setSpacing(4)

        # Camera view
        h_layout.addWidget(self._camera_widget, stretch=1)

        # Right panel
        right_panel = self._build_right_panel()
        h_layout.addWidget(right_panel)

        # ── Status bar ────────────────────────────────────────────────
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_label = QLabel("Ready")
        self._status_conn = QLabel("●  Disconnected")
        self._status_conn.setStyleSheet("color: #888;")
        self._status_record = QLabel()
        self._status_fps = QLabel("0 fps")
        sb.addWidget(self._status_label, 1)
        sb.addPermanentWidget(self._status_record)
        sb.addPermanentWidget(self._status_fps)
        sb.addPermanentWidget(self._status_conn)

        # FPS counter
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)
        self._frame_count = 0

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main Toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(22, 22))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(tb)

        # Logo
        logo_path = os.path.join(_ASSETS, "logo.png")
        if os.path.isfile(logo_path):
            logo_lbl = QLabel()
            logo_pm = QPixmap(logo_path).scaled(
                36, 36,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_lbl.setPixmap(logo_pm)
            logo_lbl.setContentsMargins(4, 0, 8, 0)
            tb.addWidget(logo_lbl)

        # Camera model selector
        lbl_model = QLabel("Camera:")
        lbl_model.setStyleSheet("color: #ccc; padding: 0 4px;")
        tb.addWidget(lbl_model)
        self._model_combo = QComboBox()
        self._model_combo.addItems(CAMERA_MODELS)
        self._model_combo.setCurrentIndex(3)  # iScout
        self._model_combo.setFixedWidth(90)
        tb.addWidget(self._model_combo)

        # Camera device index
        lbl_dev = QLabel("  Device:")
        lbl_dev.setStyleSheet("color: #ccc; padding: 0 4px;")
        tb.addWidget(lbl_dev)
        self._device_combo = QComboBox()
        # Default: auto-detect the thermal camera (index 0 is usually the
        # built-in FaceTime camera, not the USB thermal module).
        self._device_combo.addItem("Auto", None)
        for i in range(4):
            self._device_combo.addItem(f"Camera {i}", i)
        self._device_combo.setFixedWidth(90)
        tb.addWidget(self._device_combo)

        tb.addSeparator()

        # Connect / disconnect
        self._act_connect = QAction("Connect", self)
        self._act_connect.setCheckable(True)
        self._act_connect.triggered.connect(self._on_connect_toggle)
        self._act_connect.setToolTip("Connect to thermal camera")
        tb.addAction(self._act_connect)

        self._act_demo = QAction("Demo", self)
        self._act_demo.setToolTip("Run synthetic demo (no camera required)")
        self._act_demo.triggered.connect(self._camera_widget.start_demo)
        tb.addAction(self._act_demo)

        tb.addSeparator()

        # ── Measurement tools ──────────────────────────────────────────
        self._tool_group: dict[ToolMode, QAction] = {}

        def _add_tool(mode: ToolMode, label: str, tip: str) -> None:
            act = QAction(label, self)
            act.setCheckable(True)
            act.setToolTip(tip)
            act.triggered.connect(lambda checked, m=mode: self._on_tool(m, checked))
            tb.addAction(act)
            self._tool_group[mode] = act

        _add_tool(ToolMode.POINT,     "Point",  "Place temperature point measurement")
        _add_tool(ToolMode.RECTANGLE, "Rect",   "Draw rectangle measurement region")
        _add_tool(ToolMode.LINE,      "Line",   "Draw line temperature profile")
        _add_tool(ToolMode.ELLIPSE,   "Ellipse","Draw ellipse measurement region")
        _add_tool(ToolMode.POLYGON,   "Polygon","Draw polygon measurement region\n"
                                                 "(double-click to close)")

        act_clear = QAction("Clear", self)
        act_clear.setToolTip("Remove all measurement overlays")
        act_clear.triggered.connect(self._camera_widget.clear_overlays)
        tb.addAction(act_clear)

        tb.addSeparator()

        # ── Capture / record ───────────────────────────────────────────
        act_photo = QAction("Photo", self)
        act_photo.setToolTip("Save snapshot (Ctrl+S)")
        act_photo.setShortcut(QKeySequence("Ctrl+S"))
        act_photo.triggered.connect(self._take_snapshot)
        tb.addAction(act_photo)

        self._act_record = QAction("● Record", self)
        self._act_record.setCheckable(True)
        self._act_record.setToolTip("Start/stop video recording (Ctrl+R)")
        self._act_record.setShortcut(QKeySequence("Ctrl+R"))
        self._act_record.triggered.connect(self._toggle_recording)
        tb.addAction(self._act_record)

        act_open = QAction("Open", self)
        act_open.setToolTip("Open saved thermal image or video")
        act_open.triggered.connect(self._open_file)
        tb.addAction(act_open)

        tb.addSeparator()

        # ── Extra features ─────────────────────────────────────────────
        act_alarm = QAction("Alarm", self)
        act_alarm.setToolTip("Temperature alarm settings")
        act_alarm.triggered.connect(self._show_alarm_dialog)
        tb.addAction(act_alarm)

        act_settings = QAction("Settings", self)
        act_settings.setToolTip("Camera and display settings")
        act_settings.triggered.connect(self._show_settings_dialog)
        tb.addAction(act_settings)

        act_about = QAction("About", self)
        act_about.setToolTip("About iScout Mechanic-Ti VisualPlatform")
        act_about.triggered.connect(self._show_about)
        tb.addAction(act_about)

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        panel.setFixedWidth(200)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # ── Color scale bar ────────────────────────────────────────────
        scale_grp = QGroupBox("Color Scale")
        scale_layout = QVBoxLayout(scale_grp)
        scale_layout.setContentsMargins(6, 6, 6, 6)

        self._scale_max_lbl = QLabel("-- °C")
        self._scale_max_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._scale_max_lbl.setStyleSheet("color: #f66; font-weight: bold;")
        scale_layout.addWidget(self._scale_max_lbl)

        self._scale_bar = QLabel()
        self._scale_bar.setFixedWidth(36)
        self._scale_bar.setMinimumHeight(150)
        self._scale_bar.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding
        )
        bar_row = QHBoxLayout()
        bar_row.addWidget(self._scale_bar)
        bar_row.addStretch()
        scale_layout.addLayout(bar_row)

        self._scale_min_lbl = QLabel("-- °C")
        self._scale_min_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._scale_min_lbl.setStyleSheet("color: #88f; font-weight: bold;")
        scale_layout.addWidget(self._scale_min_lbl)

        layout.addWidget(scale_grp)

        # ── LUT palette selector ───────────────────────────────────────
        lut_grp = QGroupBox("Palette")
        lut_layout = QVBoxLayout(lut_grp)
        lut_layout.setContentsMargins(4, 4, 4, 4)

        self._lut_combo = QComboBox()
        self._lut_combo.addItems(LUT_NAMES)
        self._lut_combo.currentIndexChanged.connect(self._on_lut_changed)
        lut_layout.addWidget(self._lut_combo)

        # LUT swatch grid (3 columns)
        swatch_container = QWidget()
        swatch_layout = QHBoxLayout(swatch_container)
        swatch_layout.setSpacing(2)
        swatch_layout.setContentsMargins(0, 0, 0, 0)

        self._lut_swatches: list[QPushButton] = []
        col_layouts = [QVBoxLayout() for _ in range(3)]
        for i in range(27):
            btn = QPushButton()
            btn.setFixedSize(50, 14)
            btn.setToolTip(LUT_NAMES[i])
            btn.setProperty("lut_index", i)
            btn.clicked.connect(self._on_swatch_clicked)
            self._lut_swatches.append(btn)
            col_layouts[i % 3].addWidget(btn)
        for col in col_layouts:
            col.addStretch()
            swatch_layout.addLayout(col)

        scroll = QScrollArea()
        scroll.setWidget(swatch_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(160)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lut_layout.addWidget(scroll)

        layout.addWidget(lut_grp)
        self._update_lut_swatches()

        # ── Temperature statistics ─────────────────────────────────────
        stats_grp = QGroupBox("Temperature")
        stats_layout = QVBoxLayout(stats_grp)
        stats_layout.setSpacing(4)

        def _stat_row(label: str, color: str) -> QLabel:
            row_w = QWidget()
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px;")
            lbl.setFixedWidth(36)
            val = QLabel("--.-°C")
            val.setStyleSheet("color: #eee; font-family: monospace; font-size: 11px;")
            row_h.addWidget(lbl)
            row_h.addWidget(val)
            row_h.addStretch()
            stats_layout.addWidget(row_w)
            return val

        self._lbl_max = _stat_row("MAX:", "#ff6666")
        self._lbl_min = _stat_row("MIN:", "#6688ff")
        self._lbl_avg = _stat_row("AVG:", "#88ff88")
        self._lbl_med = _stat_row("MED:", "#ffcc44")

        layout.addWidget(stats_grp)
        layout.addStretch()

        return panel

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._camera_widget.stats_updated.connect(self._on_stats_updated)
        self._camera_widget.status_message.connect(self._set_status)
        self._camera_widget.connection_changed.connect(self._on_connection_changed)
        self._recorder.snapshot_saved.connect(
            lambda p: self._set_status(f"Snapshot saved: {p}")
        )
        self._recorder.recording_started.connect(
            lambda: self._set_status("Recording…")
        )
        self._recorder.recording_stopped.connect(
            lambda p: self._set_status(f"Recording saved: {p}")
        )

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @pyqtSlot(object)  # ThermalStats
    def _on_stats_updated(self, stats) -> None:
        self._frame_count += 1
        self._lbl_max.setText(f"{stats.max_temp:6.1f}°C")
        self._lbl_min.setText(f"{stats.min_temp:6.1f}°C")
        self._lbl_avg.setText(f"{stats.avg_temp:6.1f}°C")
        self._lbl_med.setText(f"{stats.med_temp:6.1f}°C")
        self._scale_max_lbl.setText(f"{stats.max_temp:.1f} °C")
        self._scale_min_lbl.setText(f"{stats.min_temp:.1f} °C")

        # Feed frame to recorder
        frame = self._camera_widget.get_current_frame()
        if frame is not None:
            self._recorder.add_frame(frame)

        # Alarm check
        self._check_alarm(stats)

    def _on_connection_changed(self, connected: bool) -> None:
        if connected:
            self._status_conn.setText("●  Connected")
            self._status_conn.setStyleSheet("color: #4f4;")
            self._act_connect.setChecked(True)
            self._act_connect.setText("Disconnect")
        else:
            self._status_conn.setText("●  Disconnected")
            self._status_conn.setStyleSheet("color: #888;")
            self._act_connect.setChecked(False)
            self._act_connect.setText("Connect")

    def _on_connect_toggle(self, checked: bool) -> None:
        if checked:
            idx = self._device_combo.currentData()
            success = self._camera_widget.connect_camera(idx)
            if not success:
                self._act_connect.setChecked(False)
        else:
            self._camera_widget.disconnect_camera()

    def _on_tool(self, mode: ToolMode, checked: bool) -> None:
        if checked:
            for m, act in self._tool_group.items():
                if m != mode:
                    act.setChecked(False)
            self._camera_widget.set_tool(mode)
        else:
            self._camera_widget.set_tool(ToolMode.NONE)

    def _on_lut_changed(self, index: int) -> None:
        self._lut_mgr.set_current(index)
        self._update_lut_swatches()
        self._update_lut_scale()
        # Highlight the matching swatch
        for i, btn in enumerate(self._lut_swatches):
            btn.setProperty("selected", i == index)
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_swatch_clicked(self) -> None:
        idx = self.sender().property("lut_index")
        self._lut_combo.setCurrentIndex(idx)

    def _update_lut_swatches(self) -> None:
        for i, btn in enumerate(self._lut_swatches):
            lut = self._lut_mgr.get_lut(i)
            mid_r, mid_g, mid_b = int(lut[128, 0]), int(lut[128, 1]), int(lut[128, 2])
            btn.setStyleSheet(
                f"QPushButton {{ background: rgb({mid_r},{mid_g},{mid_b}); "
                f"border: 1px solid #555; }}"
                f"QPushButton:hover {{ border: 1px solid #f5c518; }}"
            )

    def _update_lut_scale(self) -> None:
        bar_h = max(self._scale_bar.height(), 150)
        bar_img = self._lut_mgr.build_scale_image(bar_h, 36)
        qimg = QImage(
            bar_img.data, 36, bar_h, bar_img.strides[0],
            QImage.Format.Format_BGR888
        )
        self._scale_bar.setPixmap(QPixmap.fromImage(qimg))

    def _take_snapshot(self) -> None:
        frame = self._camera_widget.get_current_frame()
        if frame is None:
            QMessageBox.warning(self, "No Frame", "No camera frame available.")
            return
        self._recorder.save_snapshot(frame)

    def _toggle_recording(self, checked: bool) -> None:
        if checked:
            frame = self._camera_widget.get_current_frame()
            if frame is None:
                QMessageBox.warning(self, "No Frame", "No camera frame available.")
                self._act_record.setChecked(False)
                return
            self._recorder.start_recording(frame)
            self._act_record.setText("■ Stop Rec")
            self._status_record.setText(
                '<span style="color:#f44;">● REC</span>'
            )
        else:
            self._recorder.stop_recording()
            self._act_record.setText("● Record")
            self._status_record.setText("")

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Thermal Image / Video",
            _CAPTURES,
            "Images & Videos (*.jpg *.png *.bmp *.mp4 *.avi);;All Files (*)"
        )
        if not path:
            return
        if path.lower().endswith((".jpg", ".png", ".bmp")):
            img = cv2.imread(path)
            if img is not None:
                self._camera_widget._current_frame = img
                col, stats = self._processor.process(
                    img, lambda g: self._lut_mgr.apply(g)
                )
                qimg = QImage(
                    col.data, col.shape[1], col.shape[0],
                    col.strides[0], QImage.Format.Format_BGR888
                )
                self._camera_widget._display_pixmap = QPixmap.fromImage(qimg)
                self._camera_widget.update()
        else:
            # Video – not handled inline, could open in OS player
            os.startfile(path) if sys.platform == "win32" else (
                os.system(f'open "{path}"') if sys.platform == "darwin"
                else os.system(f'xdg-open "{path}"')
            )

    def _show_settings_dialog(self) -> None:
        dlg = SettingsDialog(self._params, self)
        if dlg.exec():
            new_params = dlg.get_params()
            self._params.emissivity = new_params.emissivity
            self._params.distance = new_params.distance
            self._params.humidity = new_params.humidity
            self._params.altitude = new_params.altitude
            self._params.auto_range = new_params.auto_range
            self._params.temp_min = new_params.temp_min
            self._params.temp_max = new_params.temp_max
            self._camera_widget.set_show_crosshairs(
                dlg.show_max(), dlg.show_min()
            )

    def _show_alarm_dialog(self) -> None:
        dlg = AlarmDialog(self._alarm, _SOUNDS, self)
        if dlg.exec():
            self._alarm = dlg.get_settings()
            self._camera_widget.set_alarm_temps(
                self._alarm.high_temp if self._alarm.high_enabled else None,
                self._alarm.low_temp if self._alarm.low_enabled else None,
            )
            if self._alarm.high_enabled or self._alarm.low_enabled:
                self._alarm_player.start(self._alarm.repeat_interval * 1000)
            else:
                self._alarm_player.stop()

    def _show_about(self) -> None:
        AboutDialog(_ASSETS, self).exec()

    def _check_alarm(self, stats) -> None:
        triggered = (
            (self._alarm.high_enabled and stats.max_temp > self._alarm.high_temp) or
            (self._alarm.low_enabled and stats.min_temp < self._alarm.low_temp)
        )
        if triggered and not self._alarm_player.isActive():
            self._alarm_player.start(self._alarm.repeat_interval * 1000)
            self._play_alarm_sound()

    def _play_alarm_sound(self) -> None:
        from PyQt6.QtMultimedia import QSoundEffect
        from PyQt6.QtCore import QUrl
        idx = self._alarm.sound_index
        if idx == 0 or not os.path.isdir(_SOUNDS):
            return
        files = sorted(
            [f for f in os.listdir(_SOUNDS) if f.endswith(".wav")]
        )
        if idx - 1 < len(files):
            path = os.path.join(_SOUNDS, files[idx - 1])
            sfx = QSoundEffect(self)
            sfx.setSource(QUrl.fromLocalFile(path))
            sfx.play()

    def _set_status(self, msg: str) -> None:
        self._status_label.setText(msg)

    def _update_fps(self) -> None:
        self._status_fps.setText(f"{self._frame_count} fps")
        self._frame_count = 0

    # ------------------------------------------------------------------
    # Dark theme
    # ------------------------------------------------------------------

    def _apply_dark_theme(self) -> None:
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {_DARK_BG};
                color: #e0e0e0;
            }}
            QToolBar {{
                background-color: #252525;
                border-bottom: 1px solid #3a3a3a;
                spacing: 3px;
                padding: 2px 4px;
            }}
            QToolBar QToolButton {{
                background: transparent;
                color: #ddd;
                border: 1px solid transparent;
                border-radius: 3px;
                padding: 3px 6px;
                min-width: 44px;
                font-size: 11px;
            }}
            QToolBar QToolButton:hover {{
                background: #3a3a3a;
                border-color: #555;
            }}
            QToolBar QToolButton:checked {{
                background: #3d3000;
                border-color: {_ACCENT};
                color: {_ACCENT};
            }}
            QGroupBox {{
                color: #aaa;
                border: 1px solid #3a3a3a;
                border-radius: 4px;
                margin-top: 8px;
                font-size: 11px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
            }}
            QComboBox {{
                background: #333;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 2px 4px;
            }}
            QComboBox:hover {{ border-color: {_ACCENT}; }}
            QComboBox QAbstractItemView {{
                background: #333;
                color: #ddd;
                selection-background-color: #3d3000;
            }}
            QScrollArea {{ border: none; }}
            QStatusBar {{
                background: #222;
                color: #aaa;
                border-top: 1px solid #333;
            }}
            QDialog {{
                background: {_DARK_BG};
                color: #e0e0e0;
            }}
            QLabel {{ color: #e0e0e0; }}
            QDoubleSpinBox, QSpinBox {{
                background: #333;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 1px 4px;
            }}
            QDoubleSpinBox:hover, QSpinBox:hover {{ border-color: {_ACCENT}; }}
            QCheckBox {{ color: #ddd; }}
            QCheckBox::indicator {{
                width: 14px; height: 14px;
                background: #333;
                border: 1px solid #555;
                border-radius: 2px;
            }}
            QCheckBox::indicator:checked {{
                background: {_ACCENT};
                border-color: {_ACCENT};
            }}
            QPushButton {{
                background: #333;
                color: #ddd;
                border: 1px solid #555;
                border-radius: 3px;
                padding: 4px 12px;
            }}
            QPushButton:hover {{ background: #444; border-color: {_ACCENT}; }}
            QPushButton:pressed {{ background: #3d3000; }}
            QDialogButtonBox QPushButton {{
                min-width: 70px;
            }}
            QScrollBar:vertical {{
                background: #2a2a2a;
                width: 8px;
            }}
            QScrollBar::handle:vertical {{
                background: #555;
                border-radius: 4px;
            }}
        """)

    # ------------------------------------------------------------------
    # Window events
    # ------------------------------------------------------------------

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        QTimer.singleShot(50, self._update_lut_scale)

    def closeEvent(self, event) -> None:  # noqa: N802
        self._camera_widget.disconnect_camera()
        self._recorder.stop_recording()
        super().closeEvent(event)
