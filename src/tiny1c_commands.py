"""
InfiRay Tiny1C vendor command channel (libusb / pyusb).

Reverse-engineered from a USBPcap capture of the Windows app (see
tools/parse_vendor.py and memory). The Tiny1C streams a placeholder frame
(uniform 0x8000 ≈ 238.9 °C) until the host runs a vendor init sequence; an
FFC (flat-field / shutter correction) is a separate vendor command.

Wire protocol — vendor control transfers to **interface 0**:

    WRITE : bmRequestType=0x41 bRequest=0x45 wValue=0x0078 wIndex=<page> + 8 data
    READ  : bmRequestType=0xC1 bRequest=0x44 wValue=0x0078 wIndex=<addr>  -> N

    pages:  0x1D00 main command, 0x9D00 parameters, 0x1D08 status/ack write
    status: poll 1 byte at wIndex=0x0200 until the device is ready

    FFC (basic_shutter_update):
        WRITE 0x1D00  0c41010000000000
        WRITE 0x1D00  0dc1000000000000
        then poll status ~0.75 s while the shutter operates

macOS note
----------
These are vendor requests to interface 0 (UVC VideoControl), which the system
UVC driver claims while AVFoundation streams.  Run :func:`initialize` *before*
AVFoundation opens the device, and stop the capture session briefly around
:func:`do_ffc` if a live FFC fails to claim the interface.
"""
from __future__ import annotations

import os
import time

VID = 0x0BDA
PID = 0x5840

# control-transfer constants
_BM_WRITE = 0x41          # OUT | vendor | interface
_BM_READ = 0xC1           # IN  | vendor | interface
_REQ_WRITE = 0x45
_REQ_READ = 0x44
_WVALUE = 0x0078

PAGE_CMD = 0x1D00         # main command page
PAGE_PARAM = 0x9D00       # parameter page
PAGE_ACK = 0x1D08         # status / ack
ADDR_STATUS = 0x0200      # 1-byte readiness status

# Exact byte sequences captured from the Windows app (hex → bytes).
_INIT_SEQUENCE: list[tuple[int, str]] = [
    (PAGE_CMD,   "0a01000000000000"),
    (PAGE_PARAM, "14c2000000000001"),
    (PAGE_PARAM, "14c2000100000005"),
    (PAGE_PARAM, "14c200020000012c"),
    (PAGE_PARAM, "14c200030000000f"),
    (PAGE_CMD,   "010b0c0000000000"),
    (PAGE_PARAM, "1485000300000000"),
    (PAGE_PARAM, "1485000100000000"),
    (PAGE_PARAM, "1485000200000000"),
    (PAGE_CMD,   "0584070000000010"),
    (PAGE_CMD,   "0182007ff000000f"),
    (PAGE_PARAM, "14c5000500000001"),
    (PAGE_PARAM, "14c5000300000073"),
    (PAGE_PARAM, "14c500010000012c"),
    (PAGE_PARAM, "14c5000200000128"),
    (PAGE_PARAM, "14c500040000007f"),
]

# FFC / shutter update.
_FFC_SEQUENCE: list[tuple[int, str]] = [
    (PAGE_CMD, "0c41010000000000"),
    (PAGE_CMD, "0dc1000000000000"),
]


class Tiny1CError(RuntimeError):
    pass


def _get_backend():
    """Return a usable libusb backend (prefers the pip `libusb` package DLL)."""
    import usb.backend.libusb1 as l1
    try:
        import libusb
        base = os.path.dirname(libusb.__file__)
        for root, _dirs, files in os.walk(base):
            for f in files:
                if f.lower() in ("libusb-1.0.dll", "libusb-1.0.dylib", "libusb.dylib"):
                    be = l1.get_backend(find_library=lambda x, p=os.path.join(root, f): p)
                    if be:
                        return be
    except Exception:
        pass
    return l1.get_backend()


class Tiny1C:
    """Vendor command channel for the Tiny1C over libusb."""

    def __init__(self, vid: int = VID, pid: int = PID):
        self._vid = vid
        self._pid = pid
        self._dev = None
        self._claimed = False

    # -- lifecycle ----------------------------------------------------

    def open(self) -> bool:
        import usb.core
        import usb.util
        dev = usb.core.find(idVendor=self._vid, idProduct=self._pid,
                            backend=_get_backend())
        if dev is None:
            return False
        try:
            # Don't disturb the active configuration if it's already set.
            try:
                dev.get_active_configuration()
            except Exception:
                dev.set_configuration()
            usb.util.claim_interface(dev, 0)
            self._claimed = True
        except Exception:
            # On macOS the interface may be owned by the UVC driver; we can
            # still try control transfers, but claiming is preferred.
            self._claimed = False
        self._dev = dev
        return True

    def close(self) -> None:
        if self._dev is not None:
            import usb.util
            try:
                if self._claimed:
                    usb.util.release_interface(self._dev, 0)
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
        self._dev = None
        self._claimed = False

    def __enter__(self):
        if not self.open():
            raise Tiny1CError(f"Tiny1C {self._vid:04x}:{self._pid:04x} not found")
        return self

    def __exit__(self, *exc):
        self.close()

    # -- primitive transfers -----------------------------------------

    def write_cmd(self, page: int, payload: bytes | str) -> None:
        if isinstance(payload, str):
            payload = bytes.fromhex(payload)
        if len(payload) != 8:
            raise ValueError("Tiny1C command payload must be 8 bytes")
        n = self._dev.ctrl_transfer(_BM_WRITE, _REQ_WRITE, _WVALUE, page,
                                    payload, timeout=1000)
        if n != len(payload):
            raise Tiny1CError(f"short write ({n}/{len(payload)}) to page {page:#06x}")

    def read(self, addr: int, length: int) -> bytes:
        return bytes(self._dev.ctrl_transfer(_BM_READ, _REQ_READ, _WVALUE, addr,
                                            length, timeout=1000))

    def read_status(self) -> int:
        data = self.read(ADDR_STATUS, 1)
        return data[0] if data else 0xFF

    def wait_ready(self, timeout_s: float = 3.0, poll_s: float = 0.01) -> bool:
        """Poll the status byte until the device reports ready (0) or timeout."""
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            try:
                if self.read_status() == 0:
                    return True
            except Exception:
                pass
            time.sleep(poll_s)
        return False

    # -- high-level operations ---------------------------------------

    def initialize(self) -> None:
        """Replay the captured init burst that enables real frame data."""
        for page, hexpayload in _INIT_SEQUENCE:
            self.write_cmd(page, hexpayload)
            self.wait_ready(timeout_s=1.0)

    def do_ffc(self) -> None:
        """Trigger a flat-field (shutter) correction and wait for it to finish."""
        for page, hexpayload in _FFC_SEQUENCE:
            self.write_cmd(page, hexpayload)
        # The shutter operation takes ~0.75 s; wait for the busy bit to clear.
        self.wait_ready(timeout_s=2.0)


# -- module-level convenience -----------------------------------------

def initialize_once() -> bool:
    """Open, run the init sequence, and close. Returns True on success."""
    try:
        with Tiny1C() as cam:
            cam.initialize()
        return True
    except Exception:
        return False


def ffc_once() -> bool:
    """Open, trigger one FFC, and close. Returns True on success."""
    try:
        with Tiny1C() as cam:
            cam.do_ffc()
        return True
    except Exception:
        return False
