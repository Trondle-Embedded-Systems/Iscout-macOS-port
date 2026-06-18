"""
Camera diagnostic for the iScout Mechanic-Ti thermal module (macOS).

Run this AFTER granting camera permission:
    python probe_camera.py

It lists every camera OpenCV can open, the native frame size / pixel format,
and basic stats — which tells us how the thermal camera packs its data
(e.g. 256x192 image-only vs 256x384 image-stacked-on-Y16-data).
"""
import sys
import cv2
import numpy as np


def fourcc_str(cap):
    fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
    return "".join(chr((fcc >> 8 * k) & 0xFF) for k in range(4)).strip("\x00")


def main():
    backend = cv2.CAP_AVFOUNDATION if sys.platform == "darwin" else cv2.CAP_ANY
    print(f"OpenCV {cv2.__version__}  backend={backend}")
    any_opened = False
    for idx in range(6):
        cap = cv2.VideoCapture(idx, backend)
        if not cap.isOpened():
            print(f"[{idx}] (cannot open)")
            cap.release()
            continue
        any_opened = True
        ok, frame = cap.read()
        if ok and frame is not None:
            h, w = frame.shape[:2]
            ch = 1 if frame.ndim == 2 else frame.shape[2]
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if ch == 3 else frame
            print(f"[{idx}] {w}x{h} ch={ch} fourcc={fourcc_str(cap)!r} "
                  f"min={int(g.min())} max={int(g.max())} mean={g.mean():.1f}")
            # If the frame is twice as tall as wide-ish, it may be stacked
            # (image on top, raw temperature data on the bottom).
            if h >= w * 1.4:
                top = g[: h // 2]
                bot = g[h // 2:]
                print(f"      looks stacked: top mean={top.mean():.1f} "
                      f"bottom mean={bot.mean():.1f} (bottom may be Y16 data)")
        else:
            print(f"[{idx}] opened but no frame (fourcc={fourcc_str(cap)!r})")
        cap.release()

    if not any_opened:
        print("\nNo camera opened. On macOS this is almost always a permission "
              "issue:\n  System Settings ▸ Privacy & Security ▸ Camera ▸ enable "
              "this app/Terminal,\n  then run again.")


if __name__ == "__main__":
    main()
