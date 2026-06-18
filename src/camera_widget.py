"""
Thermal camera display widget.

Handles:
  - Camera capture loop (OpenCV)
  - Colorisation via LutManager
  - Overlay drawing (mouse-driven measurement tools)
  - Temperature statistics
"""

from __future__ import annotations
import cv2
import numpy as np
from PyQt6.QtCore import (
    Qt, QTimer, QPoint, QRect, pyqtSignal, QSize
)
from PyQt6.QtGui import (
    QImage, QPixmap, QPainter, QPen, QColor, QCursor, QFont
)
from PyQt6.QtWidgets import QWidget, QSizePolicy

from .lut_manager import LutManager
from .thermal_processor import ThermalProcessor, ThermalStats, CameraParams
from . import camera_backend
from .analysis_tools import (
    OverlayManager, ToolMode,
    PointMeasure, RectMeasure, LineMeasure, EllipseMeasure, PolygonMeasure,
)

# Supported Mechanic-Ti camera USB product IDs (Realtek VID 0x0BDA)
CAMERA_PIDS = [0x5830, 0x5840, 0x5846]

# These uncooled thermal modules expose small native resolutions over UVC.
# Anything in this range (and clearly smaller than a webcam) is treated as the
# thermal camera during auto-detection.  256x192 sensors commonly report either
# 256x192 (image only) or 256x384 (image stacked on top of a Y16 data block).
_THERMAL_MAX_WIDTH = 800
_THERMAL_MAX_HEIGHT = 640

_DEMO_NOISE_SCALE = 0.3


def _av_backend() -> int:
    """Preferred OpenCV capture backend for this platform."""
    import sys as _sys
    if _sys.platform == "darwin":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def enumerate_cameras(max_index: int = 6) -> list[dict]:
    """
    Probe camera indices and return metadata for each that opens.

    Each entry: {"index": int, "width": int, "height": int,
                 "fourcc": str, "is_thermal": bool}.

    Note: on macOS this requires camera (TCC) permission to have been granted;
    without it every index fails to open.
    """
    found: list[dict] = []
    backend = _av_backend()
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            cap.release()
            continue
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
        else:
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        fourcc = "".join(chr((fcc >> 8 * k) & 0xFF) for k in range(4)).strip("\x00")
        is_thermal = (0 < w <= _THERMAL_MAX_WIDTH and 0 < h <= _THERMAL_MAX_HEIGHT)
        found.append({
            "index": idx, "width": w, "height": h,
            "fourcc": fourcc, "is_thermal": is_thermal,
        })
        cap.release()
    return found


class CameraWidget(QWidget):
    """Central widget that shows the live (or demo) thermal camera feed."""

    stats_updated = pyqtSignal(ThermalStats)
    status_message = pyqtSignal(str)
    connection_changed = pyqtSignal(bool)  # True = connected

    def __init__(self, lut_manager: LutManager,
                 processor: ThermalProcessor,
                 parent=None):
        super().__init__(parent)
        self._lut = lut_manager
        self._proc = processor
        self._overlay = OverlayManager()

        self._cap: cv2.VideoCapture | None = None
        self._av_cap = None  # camera_backend.AVFThermalCapture | None (macOS)
        self._av_uid: str | None = None  # AVFoundation device id (for re-open)
        self._current_frame: np.ndarray | None = None
        self._display_pixmap: QPixmap | None = None
        self._connected = False
        self._demo_mode = False

        self._tool = ToolMode.NONE
        self._drag_start: QPoint | None = None
        self._drag_end: QPoint | None = None
        self._active_polygon: PolygonMeasure | None = None

        self._show_max_crosshair = True
        self._show_min_crosshair = True
        self._show_center_temp = True
        self._fusion_alpha = 0.0     # 0=thermal, 1=visible
        self._pip_enabled = False
        self._fullscreen = False

        self._last_stats = ThermalStats()
        self._alarm_max: float | None = None
        self._alarm_min: float | None = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._grab_frame)
        self._timer.setInterval(40)  # ~25 fps

        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ------------------------------------------------------------------
    # Camera connection
    # ------------------------------------------------------------------

    def connect_camera(self, device_index: int | None = 0) -> bool:
        """
        Open a camera.

        Pass ``device_index=None`` to auto-detect the thermal camera.

        On macOS the thermal module is opened through AVFoundation (OpenCV's
        AVFoundation backend cannot open this Realtek UVC device); other indices
        and platforms use OpenCV.
        """
        self.disconnect_camera()

        # macOS: try the AVFoundation thermal backend first.
        if camera_backend.is_macos() and device_index is None:
            if self._connect_avf():
                return True
            # Fall through to OpenCV probing if AVF found nothing.

        if device_index is None:
            device_index = self._auto_detect_index()
            if device_index is None:
                self.status_message.emit(
                    "No camera available. On macOS, grant camera access in "
                    "System Settings ▸ Privacy & Security ▸ Camera (and replug "
                    "the thermal camera), then reconnect."
                )
                return False

        cap = cv2.VideoCapture(device_index, _av_backend())
        if not cap.isOpened():
            cap.release()
            self.status_message.emit(
                f"Cannot open camera {device_index}. If no camera prompt "
                "appeared, grant access in System Settings ▸ Privacy & "
                "Security ▸ Camera."
            )
            return False

        # Do NOT force a webcam-style resolution: the thermal sensor has a small
        # native frame (e.g. 256x192 / 256x384) and forcing 640x480 can make the
        # device hand back an upscaled or empty frame.  Use whatever it reports.
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release()
            self.status_message.emit(
                f"Camera {device_index} opened but returned no frame "
                "(check camera permission / that the device is the thermal "
                "camera)."
            )
            return False

        h, w = frame.shape[:2]
        self._cap = cap
        self._av_cap = None
        self._connected = True
        self._demo_mode = False
        self._timer.start()
        self.connection_changed.emit(True)
        self.status_message.emit(f"Camera {device_index} connected ({w}x{h})")
        return True

    def _connect_avf(self) -> bool:
        """Open the thermal camera via AVFoundation (macOS).  Returns success."""
        try:
            devs = camera_backend.list_avf_devices()
        except Exception as exc:  # pragma: no cover - defensive
            self.status_message.emit(f"AVFoundation unavailable: {exc}")
            return False
        thermal = next((d for d in devs if d["is_thermal"]), None)
        if thermal is None:
            return False
        self._av_uid = thermal["unique_id"]

        # Run the vendor init burst over libusb BEFORE AVFoundation opens the
        # device (the init talks to interface 0, which the UVC driver claims
        # once a capture session is running).  This is what makes the Tiny1C
        # output real thermal data instead of the 0x8000 placeholder frame.
        if camera_backend.initialize_thermal():
            self.status_message.emit("Thermal sensor initialised (FFC/vendor init).")

        cap = camera_backend.AVFThermalCapture()
        if not cap.open(thermal["unique_id"]):
            cap.release()
            self.status_message.emit("Failed to start thermal camera (AVFoundation).")
            return False

        # Give the stream a moment, then check whether the sensor is producing
        # real data or just uninitialised placeholder frames.
        import time as _t
        blank = True
        deadline = _t.time() + 1.5
        while _t.time() < deadline:
            ok, bgr, tmap = cap.read()
            if ok and bgr is not None:
                blank = camera_backend.frame_is_blank(bgr, tmap)
                break
            _t.sleep(0.05)

        # If it's still blank, AVFoundation may have reset the sensor when it
        # opened interface 0.  Stop the session, re-run init, and restart.
        if blank:
            cap.release()
            camera_backend.initialize_thermal()
            cap = camera_backend.AVFThermalCapture()
            if cap.open(thermal["unique_id"]):
                deadline = _t.time() + 1.5
                while _t.time() < deadline:
                    ok, bgr, tmap = cap.read()
                    if ok and bgr is not None:
                        blank = camera_backend.frame_is_blank(bgr, tmap)
                        break
                    _t.sleep(0.05)

        self._av_cap = cap
        self._cap = None
        self._connected = True
        self._demo_mode = False
        self._timer.start()
        self.connection_changed.emit(True)
        if blank:
            self.status_message.emit(
                f"{thermal['name']} connected but streaming no thermal data — "
                "unplug/replug the camera; if it stays blank the sensor needs "
                "the vendor initialisation command."
            )
        else:
            self.status_message.emit(
                f"Thermal camera connected: {thermal['name']} (AVFoundation)"
            )
        return True

    def _auto_detect_index(self) -> int | None:
        """Return the best camera index for the thermal camera, or None."""
        cams = enumerate_cameras()
        if not cams:
            return None
        for c in cams:
            if c["is_thermal"]:
                self.status_message.emit(
                    f"Auto-detected thermal camera at index {c['index']} "
                    f"({c['width']}x{c['height']})"
                )
                return c["index"]
        # No obviously-thermal device; fall back to the first that works.
        return cams[0]["index"]

    def start_demo(self) -> None:
        """Run a synthetic thermal scene for UI development / no-camera testing."""
        self.disconnect_camera()
        self._demo_mode = True
        self._connected = True
        self._timer.start()
        self.connection_changed.emit(True)
        self.status_message.emit("Demo mode – no camera connected")

    def disconnect_camera(self) -> None:
        self._timer.stop()
        if self._cap is not None:
            self._cap.release()
            self._cap = None
        if self._av_cap is not None:
            self._av_cap.release()
            self._av_cap = None
        self._connected = False
        self._demo_mode = False
        self.connection_changed.emit(False)
        self.status_message.emit("Disconnected")

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------------
    # Tool / display settings
    # ------------------------------------------------------------------

    def set_tool(self, mode: ToolMode) -> None:
        self._tool = mode
        self._drag_start = None
        self._drag_end = None
        if mode == ToolMode.POLYGON:
            self._active_polygon = self._overlay.begin_polygon()
        else:
            self._active_polygon = None
        cursors = {
            ToolMode.NONE:      Qt.CursorShape.ArrowCursor,
            ToolMode.POINT:     Qt.CursorShape.CrossCursor,
            ToolMode.RECTANGLE: Qt.CursorShape.CrossCursor,
            ToolMode.LINE:      Qt.CursorShape.CrossCursor,
            ToolMode.ELLIPSE:   Qt.CursorShape.CrossCursor,
            ToolMode.POLYGON:   Qt.CursorShape.CrossCursor,
        }
        self.setCursor(QCursor(cursors.get(mode, Qt.CursorShape.ArrowCursor)))

    def clear_overlays(self) -> None:
        self._overlay.clear_all()
        self._active_polygon = None
        self.update()

    def trigger_ffc(self) -> bool:
        """
        Perform a flat-field (shutter) correction.

        The FFC command goes over libusb to interface 0.  While the macOS
        AVFoundation session is streaming it holds that interface, so we stop
        the session, issue the FFC, and restart it (a brief video blip).
        """
        if self._av_cap is not None:
            self._timer.stop()
            self._av_cap.release()
            ok = camera_backend.ffc_thermal()
            # Re-open the AVFoundation stream.
            self._av_cap = camera_backend.AVFThermalCapture()
            if self._av_uid is not None:
                self._av_cap.open(self._av_uid)
            else:
                self._av_cap.open()
            self._timer.start()
            self.status_message.emit(
                "FFC complete." if ok else "FFC failed (could not access camera)."
            )
            return ok
        # Non-AVFoundation path (e.g. libusbK on Windows): issue directly.
        ok = camera_backend.ffc_thermal()
        self.status_message.emit("FFC complete." if ok else "FFC unavailable.")
        return ok

    def set_alarm_temps(self, max_t: float | None, min_t: float | None) -> None:
        self._alarm_max = max_t
        self._alarm_min = min_t

    def set_show_crosshairs(self, show_max: bool, show_min: bool) -> None:
        self._show_max_crosshair = show_max
        self._show_min_crosshair = show_min

    def get_current_frame(self) -> np.ndarray | None:
        return self._current_frame

    def get_overlay_manager(self) -> OverlayManager:
        return self._overlay

    # ------------------------------------------------------------------
    # Frame grab / processing
    # ------------------------------------------------------------------

    def _grab_frame(self) -> None:
        temp_map = None
        if self._demo_mode:
            frame = self._make_demo_frame()
        elif self._av_cap is not None:
            ret, frame, temp_map = self._av_cap.read()
            if not ret or frame is None:
                return
        elif self._cap is not None:
            ret, frame = self._cap.read()
            if not ret:
                return
        else:
            return

        coloured, stats = self._proc.process(
            frame,
            lambda g: self._lut.apply(g),
            temp_map=temp_map,
        )
        self._current_frame = frame
        self._last_stats = stats

        self._update_rect_stats(frame)
        self._update_line_stats(frame)
        self.stats_updated.emit(stats)

        qimg = QImage(
            coloured.data,
            coloured.shape[1], coloured.shape[0],
            coloured.strides[0],
            QImage.Format.Format_BGR888
        )
        self._display_pixmap = QPixmap.fromImage(qimg)
        self.update()

    def _update_rect_stats(self, frame: np.ndarray) -> None:
        for r in self._overlay.rectangles:
            st = self._proc.rect_stats(frame, r.x1, r.y1, r.x2, r.y2)
            r.max_temp = st.max_temp
            r.min_temp = st.min_temp
            r.avg_temp = st.avg_temp

    def _update_line_stats(self, frame: np.ndarray) -> None:
        for ln in self._overlay.lines:
            _, temps = self._proc.line_profile(frame, ln.x1, ln.y1, ln.x2, ln.y2)
            if temps.size:
                ln.max_temp = float(temps.max())
                ln.min_temp = float(temps.min())
                ln.avg_temp = float(temps.mean())

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()

        if self._display_pixmap is None:
            painter.fillRect(0, 0, w, h, QColor(30, 30, 30))
            painter.setPen(QPen(QColor(100, 100, 100)))
            painter.setFont(QFont("Arial", 14))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "iScout Mechanic-Ti\nNo camera connected"
            )
            return

        # Scale pixmap to fit widget keeping aspect ratio
        pm = self._display_pixmap.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        px = (w - pm.width()) // 2
        py = (h - pm.height()) // 2
        painter.drawPixmap(px, py, pm)

        # Scale factor for overlay coordinates
        src_w = self._display_pixmap.width()
        src_h = self._display_pixmap.height()
        scale_x = pm.width() / max(src_w, 1)
        scale_y = pm.height() / max(src_h, 1)
        scale = min(scale_x, scale_y)

        painter.translate(px, py)

        # Draw overlays
        self._overlay.draw_all(
            painter, scale,
            get_temp=lambda x, y: self._proc.pixel_temp(
                self._current_frame, x, y
            ) if self._current_frame is not None else 0.0
        )

        # Max / min crosshairs
        if self._show_max_crosshair:
            self._draw_extreme_marker(
                painter, self._last_stats.max_pos, scale,
                QColor(255, 60, 60), f"H {self._last_stats.max_temp:.1f}°C"
            )
        if self._show_min_crosshair:
            self._draw_extreme_marker(
                painter, self._last_stats.min_pos, scale,
                QColor(60, 120, 255), f"L {self._last_stats.min_temp:.1f}°C"
            )

        # Center temperature dot
        if self._show_center_temp and src_w and src_h:
            cx = int(src_w / 2 * scale)
            cy = int(src_h / 2 * scale)
            ct = self._proc.pixel_temp(
                self._current_frame, src_w // 2, src_h // 2
            ) if self._current_frame is not None else 0.0
            self._draw_extreme_marker(
                painter, (src_w // 2, src_h // 2), scale,
                QColor(255, 255, 0), f"C {ct:.1f}°C"
            )

        # Live drag preview
        if self._drag_start and self._drag_end:
            self._draw_drag_preview(painter, scale)

        painter.resetTransform()

        # Alarm flash overlay
        if self._alarm_max is not None and self._last_stats.max_temp > self._alarm_max:
            painter.fillRect(
                0, 0, w, h, QColor(255, 0, 0, 40)
            )

    def _draw_extreme_marker(self, painter: QPainter,
                             pos: tuple[int, int], scale: float,
                             color: QColor, label: str) -> None:
        cx = int(pos[0] * scale)
        cy = int(pos[1] * scale)
        r = 8
        pen = QPen(color, 1)
        painter.setPen(pen)
        painter.drawLine(cx - r, cy, cx + r, cy)
        painter.drawLine(cx, cy - r, cx, cy + r)
        painter.drawRect(cx - 3, cy - 3, 6, 6)
        font = QFont("Arial", 9)
        painter.setFont(font)
        painter.fillRect(cx + 5, cy - 14, len(label) * 7, 14, QColor(0, 0, 0, 160))
        painter.setPen(QPen(color))
        painter.drawText(cx + 7, cy - 2, label)

    def _draw_drag_preview(self, painter: QPainter, scale: float) -> None:
        p1 = self._drag_start
        p2 = self._drag_end
        pen = QPen(QColor(255, 255, 255, 180), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        if self._tool == ToolMode.RECTANGLE:
            painter.drawRect(
                min(p1.x(), p2.x()), min(p1.y(), p2.y()),
                abs(p2.x() - p1.x()), abs(p2.y() - p1.y())
            )
        elif self._tool == ToolMode.LINE:
            painter.drawLine(p1, p2)
        elif self._tool == ToolMode.ELLIPSE:
            cx = (p1.x() + p2.x()) // 2
            cy = (p1.y() + p2.y()) // 2
            rx = abs(p2.x() - p1.x()) // 2
            ry = abs(p2.y() - p1.y()) // 2
            painter.drawEllipse(cx - rx, cy - ry, rx * 2, ry * 2)

    # ------------------------------------------------------------------
    # Mouse interaction
    # ------------------------------------------------------------------

    def _view_to_img(self, pos: QPoint) -> QPoint:
        """Convert widget coordinates to image coordinates."""
        if self._display_pixmap is None:
            return pos
        w, h = self.width(), self.height()
        pm_w = self._display_pixmap.width()
        pm_h = self._display_pixmap.height()
        scale = min(w / max(pm_w, 1), h / max(pm_h, 1))
        px = (w - pm_w * scale) / 2
        py = (h - pm_h * scale) / 2
        ix = int((pos.x() - px) / scale)
        iy = int((pos.y() - py) / scale)
        return QPoint(ix, iy)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self._tool == ToolMode.NONE:
            return
        img_pos = self._view_to_img(event.pos())
        if self._tool == ToolMode.POINT:
            self._overlay.add_point(img_pos.x(), img_pos.y())
            self.update()
        elif self._tool == ToolMode.POLYGON:
            if self._active_polygon is None:
                self._active_polygon = self._overlay.begin_polygon()
            self._active_polygon.points.append((img_pos.x(), img_pos.y()))
            self.update()
        else:
            self._drag_start = img_pos
            self._drag_end = img_pos

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._drag_start and self._tool not in (
                ToolMode.NONE, ToolMode.POINT, ToolMode.POLYGON):
            self._drag_end = self._view_to_img(event.pos())
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if not self._drag_start:
            return
        img_end = self._view_to_img(event.pos())
        x1, y1 = self._drag_start.x(), self._drag_start.y()
        x2, y2 = img_end.x(), img_end.y()
        if self._tool == ToolMode.RECTANGLE:
            self._overlay.add_rect(x1, y1, x2, y2)
        elif self._tool == ToolMode.LINE:
            self._overlay.add_line(x1, y1, x2, y2)
        elif self._tool == ToolMode.ELLIPSE:
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            rx, ry = abs(x2 - x1) // 2, abs(y2 - y1) // 2
            self._overlay.add_ellipse(cx, cy, rx, ry)
        self._drag_start = None
        self._drag_end = None
        self.update()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        if self._tool == ToolMode.POLYGON and self._active_polygon:
            self._active_polygon.closed = True
            self._active_polygon = None
            self.update()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._drag_start = None
            self._drag_end = None
            self._active_polygon = None
            self.update()

    # ------------------------------------------------------------------
    # Demo mode synthetic frame
    # ------------------------------------------------------------------

    _demo_t = 0.0

    def _make_demo_frame(self) -> np.ndarray:
        import math
        self._demo_t += 0.05
        h, w = 240, 320
        y_idx, x_idx = np.mgrid[0:h, 0:w]
        # Simulated heat source moving in a figure-8
        cx = int(w / 2 + w / 4 * math.sin(self._demo_t))
        cy = int(h / 2 + h / 4 * math.sin(self._demo_t * 2))
        dist = np.sqrt((x_idx - cx) ** 2 + (y_idx - cy) ** 2)
        intensity = np.exp(-dist / 40) * 200
        # Background gradient
        bg = np.linspace(30, 80, w)
        frame_f = bg[np.newaxis, :] + intensity + np.random.normal(0, 3, (h, w))
        frame_u8 = np.clip(frame_f, 0, 255).astype(np.uint8)
        return cv2.cvtColor(frame_u8, cv2.COLOR_GRAY2BGR)
