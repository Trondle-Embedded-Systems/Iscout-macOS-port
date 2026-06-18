"""Video recording and snapshot capture for the thermal camera feed."""

from __future__ import annotations
import os
import time
import cv2
import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal


class Recorder(QObject):
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal(str)   # emits saved path
    snapshot_saved = pyqtSignal(str)       # emits saved path
    error_occurred = pyqtSignal(str)

    def __init__(self, output_dir: str, parent=None):
        super().__init__(parent)
        self._output_dir = output_dir
        self._writer: cv2.VideoWriter | None = None
        self._recording = False
        self._current_path = ""
        self._fps = 25.0
        self._frame_size: tuple[int, int] = (640, 480)

        os.makedirs(os.path.join(output_dir, "Picture"), exist_ok=True)
        os.makedirs(os.path.join(output_dir, "Video"), exist_ok=True)

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start_recording(self, frame: np.ndarray) -> None:
        if self._recording:
            return
        h, w = frame.shape[:2]
        self._frame_size = (w, h)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._output_dir, "Video", f"thermal_{timestamp}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(path, fourcc, self._fps, (w, h))
        if not self._writer.isOpened():
            self.error_occurred.emit(f"Cannot open video writer: {path}")
            self._writer = None
            return
        self._current_path = path
        self._recording = True
        self.recording_started.emit()

    def add_frame(self, frame: np.ndarray) -> None:
        if self._recording and self._writer is not None:
            if frame.shape[:2][::-1] != self._frame_size:
                frame = cv2.resize(frame, self._frame_size)
            self._writer.write(frame)

    def stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        if self._writer is not None:
            self._writer.release()
            self._writer = None
        self.recording_stopped.emit(self._current_path)

    def save_snapshot(self, frame: np.ndarray) -> str:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._output_dir, "Picture", f"thermal_{timestamp}.jpg")
        cv2.imwrite(path, frame)
        self.snapshot_saved.emit(path)
        return path

    def set_output_dir(self, directory: str) -> None:
        self._output_dir = directory
        os.makedirs(os.path.join(directory, "Picture"), exist_ok=True)
        os.makedirs(os.path.join(directory, "Video"), exist_ok=True)
