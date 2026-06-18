"""Overlay measurement tools: Point, Rectangle, Line, Ellipse, Polygon."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen, QFont, QFontMetrics


class ToolMode(Enum):
    NONE = auto()
    POINT = auto()
    RECTANGLE = auto()
    LINE = auto()
    ELLIPSE = auto()
    POLYGON = auto()


@dataclass
class PointMeasure:
    x: int
    y: int
    temp: float = 0.0
    label: str = ""

    def draw(self, painter: QPainter, scale: float = 1.0,
             get_temp: Callable[[int, int], float] | None = None) -> None:
        if get_temp:
            self.temp = get_temp(self.x, self.y)
        pen = QPen(QColor(255, 255, 0), 1)
        painter.setPen(pen)
        cx, cy = int(self.x * scale), int(self.y * scale)
        r = 4
        painter.drawLine(cx - r, cy, cx + r, cy)
        painter.drawLine(cx, cy - r, cx, cy + r)
        painter.drawEllipse(cx - 2, cy - 2, 4, 4)
        lbl = f"{self.label} {self.temp:.1f}°C" if self.label else f"{self.temp:.1f}°C"
        _draw_label(painter, cx + 5, cy - 5, lbl)


@dataclass
class RectMeasure:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0

    def draw(self, painter: QPainter, scale: float = 1.0) -> None:
        pen = QPen(QColor(0, 255, 0), 1)
        painter.setPen(pen)
        rx1 = int(min(self.x1, self.x2) * scale)
        ry1 = int(min(self.y1, self.y2) * scale)
        rx2 = int(max(self.x1, self.x2) * scale)
        ry2 = int(max(self.y1, self.y2) * scale)
        painter.drawRect(rx1, ry1, rx2 - rx1, ry2 - ry1)
        lbl = (f"{self.label}  " if self.label else "") + (
            f"Max:{self.max_temp:.1f}  Min:{self.min_temp:.1f}  "
            f"Avg:{self.avg_temp:.1f}°C"
        )
        _draw_label(painter, rx1, ry1 - 4, lbl)
        # Crosshair at max/min within rect could be added here


@dataclass
class LineMeasure:
    x1: int
    y1: int
    x2: int
    y2: int
    label: str = ""
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0

    def draw(self, painter: QPainter, scale: float = 1.0) -> None:
        pen = QPen(QColor(0, 200, 255), 1)
        painter.setPen(pen)
        painter.drawLine(
            int(self.x1 * scale), int(self.y1 * scale),
            int(self.x2 * scale), int(self.y2 * scale)
        )
        mx = int((self.x1 + self.x2) / 2 * scale)
        my = int((self.y1 + self.y2) / 2 * scale)
        lbl = (f"{self.label}  " if self.label else "") + (
            f"Max:{self.max_temp:.1f}  Min:{self.min_temp:.1f}  "
            f"Avg:{self.avg_temp:.1f}°C"
        )
        _draw_label(painter, mx, my - 10, lbl)


@dataclass
class EllipseMeasure:
    cx: int
    cy: int
    rx: int
    ry: int
    label: str = ""
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0

    def draw(self, painter: QPainter, scale: float = 1.0) -> None:
        pen = QPen(QColor(255, 140, 0), 1)
        painter.setPen(pen)
        scx = int(self.cx * scale)
        scy = int(self.cy * scale)
        srx = int(self.rx * scale)
        sry = int(self.ry * scale)
        painter.drawEllipse(scx - srx, scy - sry, srx * 2, sry * 2)
        lbl = (f"{self.label}  " if self.label else "") + (
            f"Max:{self.max_temp:.1f}  Min:{self.min_temp:.1f}  "
            f"Avg:{self.avg_temp:.1f}°C"
        )
        _draw_label(painter, scx - srx, scy - sry - 4, lbl)


@dataclass
class PolygonMeasure:
    points: list[tuple[int, int]] = field(default_factory=list)
    label: str = ""
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0
    closed: bool = False

    def draw(self, painter: QPainter, scale: float = 1.0) -> None:
        if len(self.points) < 2:
            return
        pen = QPen(QColor(255, 80, 200), 1)
        painter.setPen(pen)
        scaled = [(int(x * scale), int(y * scale)) for x, y in self.points]
        for i in range(len(scaled) - 1):
            painter.drawLine(scaled[i][0], scaled[i][1],
                             scaled[i + 1][0], scaled[i + 1][1])
        if self.closed and len(scaled) > 2:
            painter.drawLine(scaled[-1][0], scaled[-1][1],
                             scaled[0][0], scaled[0][1])
        if scaled:
            lbl = (f"{self.label}  " if self.label else "") + (
                f"Max:{self.max_temp:.1f}  Min:{self.min_temp:.1f}  "
                f"Avg:{self.avg_temp:.1f}°C"
            )
            _draw_label(painter, scaled[0][0], scaled[0][1] - 4, lbl)


def _draw_label(painter: QPainter, x: int, y: int, text: str) -> None:
    """Draw a small label with dark background for readability."""
    font = QFont("Arial", 9)
    painter.setFont(font)
    fm = QFontMetrics(font)
    rect = fm.boundingRect(text)
    bg = QColor(0, 0, 0, 160)
    painter.fillRect(x, y - rect.height(), rect.width() + 4, rect.height() + 2, bg)
    painter.setPen(QPen(QColor(255, 255, 255)))
    painter.drawText(x + 2, y, text)


class OverlayManager:
    """Manages all active measurement overlays on the camera view."""

    def __init__(self) -> None:
        self.points: list[PointMeasure] = []
        self.rectangles: list[RectMeasure] = []
        self.lines: list[LineMeasure] = []
        self.ellipses: list[EllipseMeasure] = []
        self.polygons: list[PolygonMeasure] = []
        self._next_label = 1

    def next_label(self) -> str:
        lbl = f"R{self._next_label}"
        self._next_label += 1
        return lbl

    def add_point(self, x: int, y: int) -> PointMeasure:
        p = PointMeasure(x, y, label=f"P{self._next_label}")
        self._next_label += 1
        self.points.append(p)
        return p

    def add_rect(self, x1: int, y1: int, x2: int, y2: int) -> RectMeasure:
        r = RectMeasure(x1, y1, x2, y2, label=self.next_label())
        self.rectangles.append(r)
        return r

    def add_line(self, x1: int, y1: int, x2: int, y2: int) -> LineMeasure:
        ln = LineMeasure(x1, y1, x2, y2, label=f"L{self._next_label}")
        self._next_label += 1
        self.lines.append(ln)
        return ln

    def add_ellipse(self, cx: int, cy: int, rx: int, ry: int) -> EllipseMeasure:
        e = EllipseMeasure(cx, cy, rx, ry, label=f"E{self._next_label}")
        self._next_label += 1
        self.ellipses.append(e)
        return e

    def begin_polygon(self) -> PolygonMeasure:
        p = PolygonMeasure(label=f"G{self._next_label}")
        self._next_label += 1
        self.polygons.append(p)
        return p

    def clear_all(self) -> None:
        self.points.clear()
        self.rectangles.clear()
        self.lines.clear()
        self.ellipses.clear()
        self.polygons.clear()
        self._next_label = 1

    def draw_all(self, painter: QPainter, scale: float = 1.0,
                 get_temp: Callable[[int, int], float] | None = None) -> None:
        for p in self.points:
            p.draw(painter, scale, get_temp)
        for r in self.rectangles:
            r.draw(painter, scale)
        for ln in self.lines:
            ln.draw(painter, scale)
        for e in self.ellipses:
            e.draw(painter, scale)
        for pg in self.polygons:
            pg.draw(painter, scale)
