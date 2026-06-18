"""Thermal image processing: normalization, colorization, temperature extraction."""

import numpy as np
import cv2
from dataclasses import dataclass, field


@dataclass
class ThermalStats:
    max_temp: float = 0.0
    min_temp: float = 0.0
    avg_temp: float = 0.0
    med_temp: float = 0.0
    max_pos: tuple[int, int] = (0, 0)
    min_pos: tuple[int, int] = (0, 0)


@dataclass
class CameraParams:
    emissivity: float = 0.95
    distance: float = 1.0          # metres
    humidity: float = 0.60         # 0–1
    altitude: float = 0.0          # metres above sea level
    temp_min: float = -20.0        # °C, user-locked range low
    temp_max: float = 120.0        # °C, user-locked range high
    auto_range: bool = True


class ThermalProcessor:
    """
    Converts raw camera frames into colorised thermal images and computes
    temperature statistics.

    The actual temperature mapping depends on camera calibration.  Without
    proprietary calibration data we use a linear mapping over the detected
    pixel intensity range, which gives visually correct results for most
    uncooled microbolometer cameras.
    """

    def __init__(self, params: CameraParams | None = None):
        self.params = params or CameraParams()
        self._raw_min: float = 0.0
        self._raw_max: float = 255.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray, lut_fn) -> tuple[np.ndarray, ThermalStats]:
        """
        Process one camera frame.

        Parameters
        ----------
        frame   : H×W×3 BGR uint8 array from OpenCV
        lut_fn  : callable(gray_uint8) -> BGR uint8  (from LutManager.apply)

        Returns
        -------
        colorised : H×W×3 BGR uint8
        stats     : ThermalStats
        """
        gray = self._to_gray16(frame)
        stats = self._compute_stats(gray)
        normalised = self._normalise(gray, stats)
        coloured = lut_fn(normalised)
        return coloured, stats

    def pixel_temp(self, frame: np.ndarray, x: int, y: int) -> float:
        """Return estimated temperature at pixel (x, y)."""
        gray = self._to_gray16(frame)
        if 0 <= y < gray.shape[0] and 0 <= x < gray.shape[1]:
            pv = float(gray[y, x])
            return self._pv_to_temp(pv, float(gray.min()), float(gray.max()))
        return 0.0

    def rect_stats(self, frame: np.ndarray, x1: int, y1: int,
                   x2: int, y2: int) -> ThermalStats:
        """Return stats for the rectangle region."""
        gray = self._to_gray16(frame)
        h, w = gray.shape[:2]
        rx1, rx2 = sorted([max(0, x1), min(w - 1, x2)])
        ry1, ry2 = sorted([max(0, y1), min(h - 1, y2)])
        roi = gray[ry1:ry2 + 1, rx1:rx2 + 1]
        if roi.size == 0:
            return ThermalStats()
        return self._compute_stats(roi)

    def line_profile(self, frame: np.ndarray,
                     x1: int, y1: int, x2: int, y2: int,
                     num_points: int = 100) -> tuple[np.ndarray, np.ndarray]:
        """Return (distances, temps) arrays for a line profile."""
        gray = self._to_gray16(frame)
        xs = np.linspace(x1, x2, num_points).astype(int)
        ys = np.linspace(y1, y2, num_points).astype(int)
        h, w = gray.shape[:2]
        xs = np.clip(xs, 0, w - 1)
        ys = np.clip(ys, 0, h - 1)
        pvs = gray[ys, xs].astype(float)
        gmin, gmax = float(gray.min()), float(gray.max())
        temps = np.array([self._pv_to_temp(p, gmin, gmax) for p in pvs])
        dists = np.linspace(0, np.hypot(x2 - x1, y2 - y1), num_points)
        return dists, temps

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_gray16(frame: np.ndarray) -> np.ndarray:
        """Convert any frame to a single-channel float32 proxy."""
        if frame is None or frame.size == 0:
            return np.zeros((1, 1), dtype=np.float32)
        if frame.ndim == 3:
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32)
        return frame.astype(np.float32)

    def _compute_stats(self, gray: np.ndarray) -> ThermalStats:
        gmin = float(gray.min())
        gmax = float(gray.max())
        max_idx = np.unravel_index(np.argmax(gray), gray.shape)
        min_idx = np.unravel_index(np.argmin(gray), gray.shape)
        st = ThermalStats()
        st.max_temp = self._pv_to_temp(gmax, gmin, gmax)
        st.min_temp = self._pv_to_temp(gmin, gmin, gmax)
        st.avg_temp = self._pv_to_temp(float(gray.mean()), gmin, gmax)
        st.med_temp = self._pv_to_temp(float(np.median(gray)), gmin, gmax)
        st.max_pos = (int(max_idx[1]), int(max_idx[0]))
        st.min_pos = (int(min_idx[1]), int(min_idx[0]))
        return st

    def _normalise(self, gray: np.ndarray, stats: ThermalStats) -> np.ndarray:
        """Normalise to 0–255 uint8 for LUT application."""
        if self.params.auto_range:
            lo, hi = gray.min(), gray.max()
        else:
            lo = self._temp_to_pv(self.params.temp_min)
            hi = self._temp_to_pv(self.params.temp_max)
        span = float(hi - lo) or 1.0
        norm = np.clip((gray.astype(float) - lo) / span * 255.0, 0, 255)
        return norm.astype(np.uint8)

    def _pv_to_temp(self, pv: float, lo: float, hi: float) -> float:
        """Linear pixel-value → temperature mapping."""
        span = hi - lo or 1.0
        t_lo = self.params.temp_min
        t_hi = self.params.temp_max
        return t_lo + (pv - lo) / span * (t_hi - t_lo)

    def _temp_to_pv(self, temp: float) -> float:
        t_lo = self.params.temp_min
        t_hi = self.params.temp_max
        span = t_hi - t_lo or 1.0
        return (temp - t_lo) / span * 255.0
