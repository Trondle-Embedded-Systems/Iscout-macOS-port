"""
Camera capture backends.

macOS note
----------
OpenCV's AVFoundation backend cannot open the iScout/Mechanic-Ti thermal
module (Realtek 0x0BDA UVC device): ``cv2.VideoCapture`` raises an internal
C++ exception for it.  We therefore capture directly through AVFoundation via
PyObjC on macOS, and fall back to OpenCV elsewhere.

The thermal module streams a 256x384 ``yuvs`` (packed YUV 4:2:2) frame:

    rows   0..191  -> visible thermal image (luma plane carries the picture)
    rows 192..383  -> raw 16-bit temperature data (little-endian per pixel)

Temperature: ``celsius = raw16 / 64.0 - 273.15`` (InfiRay P2/T2 family).
"""

from __future__ import annotations

import sys
import threading
import numpy as np

# Native 'yuvs' (kCVPixelFormatType_422YpCbCr8_yuvs) so the raw bytes — and in
# particular the temperature data block — are passed through untouched.
_YUVS = 0x79757673

# Realtek VID + supported Mechanic-Ti / InfiRay PIDs (uniqueID looks like
# "0x10000000bda5840" on macOS, i.e. ...<vid><pid>).
_THERMAL_UNIQUE_HINTS = ("bda5830", "bda5840", "bda5846")


def is_macos() -> bool:
    return sys.platform == "darwin"


# ----------------------------------------------------------------------
# AVFoundation (macOS)
# ----------------------------------------------------------------------

def _avf_available() -> bool:
    if not is_macos():
        return False
    try:
        import AVFoundation  # noqa: F401
        import Quartz        # noqa: F401
        import CoreMedia     # noqa: F401
        return True
    except Exception:
        return False


def list_avf_devices() -> list[dict]:
    """Return [{index, name, unique_id, is_thermal}] for AVFoundation video devices."""
    if not _avf_available():
        return []
    import AVFoundation as AVF
    types = []
    for attr in ("AVCaptureDeviceTypeBuiltInWideAngleCamera",
                 "AVCaptureDeviceTypeExternal",
                 "AVCaptureDeviceTypeContinuityCamera"):
        t = getattr(AVF, attr, None)
        if t:
            types.append(t)
    sess = AVF.AVCaptureDeviceDiscoverySession.\
        discoverySessionWithDeviceTypes_mediaType_position_(
            types, AVF.AVMediaTypeVideo, AVF.AVCaptureDevicePositionUnspecified)
    out = []
    for i, d in enumerate(sess.devices()):
        uid = str(d.uniqueID())
        out.append({
            "index": i,
            "name": str(d.localizedName()),
            "unique_id": uid,
            "is_thermal": any(h in uid.lower() for h in _THERMAL_UNIQUE_HINTS),
            "_device": d,
        })
    return out


class AVFThermalCapture:
    """
    AVFoundation capture for the thermal module.

    Mirrors the small slice of the cv2.VideoCapture API the app needs:
    ``isOpened()``, ``read()`` and ``release()``.  ``read()`` returns
    ``(ok, frame_bgr, temp_map)`` where ``temp_map`` is a float32 °C array (or
    ``None`` if the device is not the stacked thermal format).
    """

    def __init__(self):
        self._session = None
        self._delegate = None
        self._lock = threading.Lock()
        self._latest: np.ndarray | None = None   # raw HxWx2 uint8
        self._w = 0
        self._h = 0
        self._opened = False

    # -- lifecycle ----------------------------------------------------

    def open(self, unique_id: str | None = None) -> bool:
        import AVFoundation as AVF
        from CoreMedia import CMVideoFormatDescriptionGetDimensions
        from Foundation import NSObject
        from Quartz import (
            CVPixelBufferLockBaseAddress, CVPixelBufferUnlockBaseAddress,
            CVPixelBufferGetBaseAddress, CVPixelBufferGetBytesPerRow,
            CVPixelBufferGetWidth, CVPixelBufferGetHeight,
        )
        from CoreMedia import CMSampleBufferGetImageBuffer
        import dispatch

        devs = list_avf_devices()
        if not devs:
            return False
        dev = None
        if unique_id:
            dev = next((d["_device"] for d in devs if d["unique_id"] == unique_id), None)
        if dev is None:
            dev = next((d["_device"] for d in devs if d["is_thermal"]), None)
        if dev is None:
            return False

        # Prefer the 256x384 (image + temperature) format if present.
        target = None
        for f in dev.formats():
            dim = CMVideoFormatDescriptionGetDimensions(f.formatDescription())
            if dim.height >= dim.width * 1.4:   # stacked frame (e.g. 256x384)
                target = f
                break
        if target is not None:
            if dev.lockForConfiguration_(None):
                dev.setActiveFormat_(target)
                dev.unlockForConfiguration()

        capture = self

        class _Delegate(NSObject):
            def captureOutput_didOutputSampleBuffer_fromConnection_(self, output, sb, conn):
                pb = CMSampleBufferGetImageBuffer(sb)
                if pb is None:
                    return
                CVPixelBufferLockBaseAddress(pb, 1)
                try:
                    w = CVPixelBufferGetWidth(pb)
                    h = CVPixelBufferGetHeight(pb)
                    bpr = CVPixelBufferGetBytesPerRow(pb)
                    base = CVPixelBufferGetBaseAddress(pb)
                    arr = np.frombuffer(base.as_buffer(bpr * h), dtype=np.uint8)
                    arr = arr.reshape(h, bpr)[:, :w * 2].reshape(h, w, 2).copy()
                finally:
                    CVPixelBufferUnlockBaseAddress(pb, 1)
                with capture._lock:
                    capture._latest = arr
                    capture._w, capture._h = w, h

        session = AVF.AVCaptureSession.alloc().init()
        session.beginConfiguration()
        inp, _err = AVF.AVCaptureDeviceInput.deviceInputWithDevice_error_(dev, None)
        if inp is None or not session.canAddInput_(inp):
            return False
        session.addInput_(inp)
        out = AVF.AVCaptureVideoDataOutput.alloc().init()
        out.setAlwaysDiscardsLateVideoFrames_(True)
        out.setVideoSettings_({"PixelFormatType": _YUVS})
        delegate = _Delegate.alloc().init()
        out.setSampleBufferDelegate_queue_(
            delegate, dispatch.dispatch_queue_create(b"iscout.thermal.capture", None))
        session.addOutput_(out)
        session.commitConfiguration()
        session.startRunning()

        self._session = session
        self._delegate = delegate
        self._opened = True
        return True

    def isOpened(self) -> bool:  # noqa: N802  (cv2 API parity)
        return self._opened

    def read(self):
        """Return (ok, frame_bgr_uint8, temp_map_celsius_or_None)."""
        with self._lock:
            raw = None if self._latest is None else self._latest.copy()
            w, h = self._w, self._h
        if raw is None:
            return False, None, None
        return _decode_thermal(raw, w, h)

    def release(self) -> None:
        if self._session is not None:
            try:
                self._session.stopRunning()
            except Exception:
                pass
        self._session = None
        self._delegate = None
        self._opened = False
        with self._lock:
            self._latest = None


def frame_is_blank(bgr: np.ndarray | None, temp_map: np.ndarray | None) -> bool:
    """
    True when a decoded frame carries no real sensor data.

    These modules emit a placeholder frame (black image, uniform 0x8000 in the
    temperature block -> ~238.9 C) until a vendor init/FFC command is issued.
    """
    if bgr is None:
        return True
    if temp_map is not None:
        return float(temp_map.std()) < 0.5
    return int(bgr.max()) < 5


def _decode_thermal(raw: np.ndarray, w: int, h: int):
    """
    Decode a raw HxWx2 'yuvs' buffer into (ok, bgr_image, temp_map).

    For a stacked 256x384 frame: top half -> image, bottom half -> temperatures.
    For a plain image frame (height ~= width): whole luma -> image, no temps.
    """
    import cv2
    luma = raw[:, :, 0]                       # 'yuvs' byte order: Y0 Cb Y1 Cr
    stacked = h >= w * 1.4
    if stacked:
        img_h = h // 2
        image_luma = luma[:img_h]
        data = raw[img_h:img_h * 2].astype(np.uint16)
        raw16 = data[:, :, 0] | (data[:, :, 1] << 8)
        temp_map = (raw16.astype(np.float32) / 64.0) - 273.15
    else:
        image_luma = luma
        temp_map = None
    bgr = cv2.cvtColor(np.ascontiguousarray(image_luma), cv2.COLOR_GRAY2BGR)
    return True, bgr, temp_map
