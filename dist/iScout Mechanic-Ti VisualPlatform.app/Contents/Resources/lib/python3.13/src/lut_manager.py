"""LUT (Look-Up Table) color palette manager for thermal imaging."""

from __future__ import annotations
import os
import numpy as np

LUT_NAMES = [
    "Iron",        # 1  - classic thermal iron/rainbow
    "Rainbow",     # 2
    "Hot Metal",   # 3
    "Cold",        # 4
    "Jet",         # 5
    "Lava",        # 6
    "Ice Fire",    # 7
    "Spectrum",    # 8
    "Warm",        # 9
    "Cool",        # 10
    "Hot",         # 11
    "Green",       # 12
    "Medical",     # 13
    "Red",         # 14
    "Blue",        # 15
    "Gray",        # 16
    "Invert Gray", # 17
    "Copper",      # 18
    "Amber",       # 19
    "Sepia",       # 20
    "Arctic",      # 21
    "Plasma",      # 22
    "Viridis",     # 23
    "Magma",       # 24
    "Inferno",     # 25
    "Autumn",      # 26
    "Spring",      # 27
]


class LutManager:
    """Loads and manages 27 thermal color palettes from .dat files."""

    def __init__(self, data_dir: str):
        self._data_dir = data_dir
        self._luts: list[np.ndarray | None] = [None] * 27
        self._current_index = 0
        self._load_all()

    def _load_all(self) -> None:
        for i in range(27):
            path = os.path.join(self._data_dir, f"lut_{i + 1}.dat")
            if os.path.isfile(path):
                raw = np.fromfile(path, dtype=np.uint8)
                if raw.size == 768:
                    self._luts[i] = raw.reshape(256, 3)

    def get_lut(self, index: int) -> np.ndarray:
        """Return RGB LUT array (256×3) for the given 0-based index."""
        lut = self._luts[index % 27]
        if lut is None:
            return self._fallback_lut()
        return lut

    def get_current_lut(self) -> np.ndarray:
        return self.get_lut(self._current_index)

    def set_current(self, index: int) -> None:
        self._current_index = index % 27

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def names(self) -> list[str]:
        return LUT_NAMES

    def apply(self, gray: np.ndarray, index: int | None = None) -> np.ndarray:
        """Apply LUT to a uint8 grayscale image, returning a BGR uint8 image."""
        lut = self.get_lut(index if index is not None else self._current_index)
        # lut is [R, G, B] per entry; OpenCV expects BGR
        r = lut[:, 0][gray]
        g = lut[:, 1][gray]
        b = lut[:, 2][gray]
        return np.stack([b, g, r], axis=-1)

    def build_scale_image(self, height: int, width: int = 30) -> np.ndarray:
        """Return a BGR gradient bar image showing the current palette."""
        lut = self.get_current_lut()
        indices = np.linspace(255, 0, height, dtype=np.uint8)
        r = lut[:, 0][indices]
        g = lut[:, 1][indices]
        b = lut[:, 2][indices]
        bar = np.stack([b, g, r], axis=-1)
        return np.repeat(bar[:, np.newaxis, :], width, axis=1)

    @staticmethod
    def _fallback_lut() -> np.ndarray:
        x = np.arange(256, dtype=np.uint8)
        return np.stack([x, x, x], axis=-1)
