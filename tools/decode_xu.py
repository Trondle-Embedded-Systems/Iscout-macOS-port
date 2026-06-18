#!/usr/bin/env python3
"""
Decode a USBPcap capture of the Tiny1C and print the InfiRay vendor (vdcmd)
commands the Windows app sends to the camera's UVC Extension Unit.

The Tiny1C's command channel is UVC Extension Unit id 4 on interface 0, so
every command is a class control transfer with wIndex = 0x0400.  This script
shells out to tshark (bundled with Wireshark) to pull those transfers out of
the capture and prints them as annotated hex so we can identify the FFC
(`basic_shutter_update`) and stream-start (`i2c_start_stream`) sequences.

Usage:
    python tools/decode_xu.py path\\to\\capture.pcapng
    python tools/decode_xu.py path\\to\\capture.pcapng --all   # all control xfers
"""
from __future__ import annotations
import os
import sys
import subprocess
import argparse

TSHARK = r"C:\Program Files\Wireshark\tshark.exe"
W_INDEX_XU = 0x0400          # unit 4 << 8 | interface 0

# UVC request codes (bRequest) for readability
UVC_REQ = {
    0x01: "SET_CUR", 0x81: "GET_CUR",
    0x82: "GET_MIN", 0x83: "GET_MAX", 0x84: "GET_RES",
    0x85: "GET_LEN", 0x86: "GET_INFO", 0x87: "GET_DEF",
}


def run_tshark(pcap: str, only_xu: bool) -> list[dict]:
    if not os.path.isfile(TSHARK):
        sys.exit(f"tshark not found at {TSHARK} — install/locate Wireshark.")
    # Control-transfer setup filter. USBPcap puts setup fields under usb.setup.*
    disp = "usb.transfer_type == 0x02"  # control
    if only_xu:
        disp += " && usb.setup.wIndex == 0x0400"
    fields = [
        "frame.number", "frame.time_relative",
        "usb.bmRequestType", "usb.setup.bRequest",
        "usb.setup.wValue", "usb.setup.wIndex", "usb.setup.wLength",
        "usb.capdata", "usb.control.Response",
    ]
    cmd = [TSHARK, "-r", pcap, "-Y", disp, "-T", "fields"]
    for f in fields:
        cmd += ["-e", f]
    cmd += ["-E", "separator=|", "-E", "occurrence=f"]
    out = subprocess.run(cmd, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"tshark error:\n{out.stderr}")
    rows = []
    for line in out.stdout.splitlines():
        parts = line.split("|")
        if len(parts) < 9:
            continue
        rows.append({
            "frame": parts[0], "t": parts[1],
            "bmReqType": parts[2], "bRequest": parts[3],
            "wValue": parts[4], "wIndex": parts[5], "wLength": parts[6],
            "capdata": parts[7], "response": parts[8],
        })
    return rows


def hx(v: str) -> int | None:
    if not v:
        return None
    try:
        return int(v, 16) if v.lower().startswith("0x") else int(v, 16)
    except ValueError:
        try:
            return int(v)
        except ValueError:
            return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--all", action="store_true",
                    help="show all control transfers, not just XU (wIndex 0x0400)")
    args = ap.parse_args()

    rows = run_tshark(args.pcap, only_xu=not args.all)
    if not rows:
        print("No matching control transfers found.")
        print("Tip: re-run with --all to see every control transfer, and confirm "
              "the capture actually contains the camera's traffic.")
        return 0

    print(f"{'#':>5}  {'time':>9}  {'dir/req':<16} {'wValue':>7} {'wIndex':>7} "
          f"{'len':>4}  data")
    print("-" * 90)
    for r in rows:
        breq = hx(r["bRequest"])
        bmrt = hx(r["bmReqType"])
        direction = "IN " if (bmrt is not None and bmrt & 0x80) else "OUT"
        reqname = UVC_REQ.get(breq, f"req{breq:#04x}" if breq is not None else "?")
        wval = hx(r["wValue"]) or 0
        widx = hx(r["wIndex"]) or 0
        wlen = hx(r["wLength"]) or 0
        cs = (wval >> 8) & 0xFF        # control selector (high byte of wValue)
        data = r["capdata"] or r["response"] or ""
        data = data.replace(":", "").strip()
        tag = ""
        if widx == W_INDEX_XU:
            tag = f"  [XU u4 CS={cs}]"
        print(f"{r['frame']:>5}  {r['t']:>9}  {direction}/{reqname:<11} "
              f"{wval:#07x} {widx:#07x} {wlen:>4}  {data}{tag}")

    print("\nLegend: OUT/SET_CUR rows to wIndex 0x0400 are the vendor commands.")
    print("Look for a repeated short command early in the session (stream-start)")
    print("and one issued when you press the FFC/calibrate button (shutter_update).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
