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
        # Real per-pixel temperatures (°C) for the current frame, when the
        # camera provides a calibrated data block.  None -> estimate from
        # pixel intensity instead.
        self._temp_map: np.ndarray | None = None

    @property
    def has_real_temps(self) -> bool:
        return self._temp_map is not None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(self, frame: np.ndarray, lut_fn,
                temp_map: np.ndarray | None = None) -> tuple[np.ndarray, ThermalStats]:
        """
        Process one camera frame.

        Parameters
        ----------
        frame    : H×W×3 BGR uint8 array
        lut_fn   : callable(gray_uint8) -> BGR uint8  (from LutManager.apply)
        temp_map : optional H×W float32 array of real °C temperatures.  When
                   provided (calibrated thermal camera) it is used for all
                   measurements; otherwise temperatures are estimated from
                   pixel intensity.

        Returns
        -------
        colorised : H×W×3 BGR uint8
        stats     : ThermalStats
        """
        self._temp_map = temp_map
        if temp_map is not None:
            stats = self._stats_from_temps(temp_map)
            normalised = self._normalise_temps(temp_map)
        else:
            gray = self._to_gray16(frame)
            stats = self._compute_stats(gray)
            normalised = self._normalise(gray, stats)
        coloured = lut_fn(normalised)
        return coloured, stats

    def pixel_temp(self, frame: np.ndarray, x: int, y: int) -> float:
        """Return temperature at pixel (x, y)."""
        if self._temp_map is not None:
            tm = self._temp_map
            if 0 <= y < tm.shape[0] and 0 <= x < tm.shape[1]:
                return float(tm[y, x])
            return 0.0
        gray = self._to_gray16(frame)
        if 0 <= y < gray.shape[0] and 0 <= x < gray.shape[1]:
            pv = float(gray[y, x])
            return self._pv_to_temp(pv, float(gray.min()), float(gray.max()))
        return 0.0

    def rect_stats(self, frame: np.ndarray, x1: int, y1: int,
                   x2: int, y2: int) -> ThermalStats:
        """Return stats for the rectangle region."""
        if self._temp_map is not None:
            h, w = self._temp_map.shape[:2]
            rx1, rx2 = sorted([max(0, x1), min(w - 1, x2)])
            ry1, ry2 = sorted([max(0, y1), min(h - 1, y2)])
            roi = self._temp_map[ry1:ry2 + 1, rx1:rx2 + 1]
            if roi.size == 0:
                return ThermalStats()
            return self._stats_from_temps(roi)
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
        xs = np.linspace(x1, x2, num_points).astype(int)
        ys = np.linspace(y1, y2, num_points).astype(int)
        dists = np.linspace(0, np.hypot(x2 - x1, y2 - y1), num_points)
        if self._temp_map is not None:
            tm = self._temp_map
            h, w = tm.shape[:2]
            xs = np.clip(xs, 0, w - 1)
            ys = np.clip(ys, 0, h - 1)
            return dists, tm[ys, xs].astype(float)
        gray = self._to_gray16(frame)
        h, w = gray.shape[:2]
        xs = np.clip(xs, 0, w - 1)
        ys = np.clip(ys, 0, h - 1)
        pvs = gray[ys, xs].astype(float)
        gmin, gmax = float(gray.min()), float(gray.max())
        temps = np.array([self._pv_to_temp(p, gmin, gmax) for p in pvs])
        return dists, temps

    # ------------------------------------------------------------------
    # Real-temperature helpers
    # ------------------------------------------------------------------

    def _stats_from_temps(self, temps: np.ndarray) -> ThermalStats:
        st = ThermalStats()
        st.max_temp = float(temps.max())
        st.min_temp = float(temps.min())
        st.avg_temp = float(temps.mean())
        st.med_temp = float(np.median(temps))
        max_idx = np.unravel_index(np.argmax(temps), temps.shape)
        min_idx = np.unravel_index(np.argmin(temps), temps.shape)
        st.max_pos = (int(max_idx[1]), int(max_idx[0]))
        st.min_pos = (int(min_idx[1]), int(min_idx[0]))
        return st

    def _normalise_temps(self, temps: np.ndarray) -> np.ndarray:
        if self.params.auto_range:
            lo, hi = float(temps.min()), float(temps.max())
        else:
            lo, hi = self.params.temp_min, self.params.temp_max
        span = (hi - lo) or 1.0
        norm = np.clip((temps - lo) / span * 255.0, 0, 255)
        return norm.astype(np.uint8)

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
