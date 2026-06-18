#!/usr/bin/env python3
"""
Parse a USBPcap capture of the Tiny1C and extract the InfiRay vendor
(vdcmd) control transfers directly from the pcap bytes (tshark doesn't
expose the control data stage as a single field for this device).

iRay vendor protocol (observed):
    OUT: bmRequestType=0x41 bRequest=0x45  wValue=0x0078 wIndex=<cmd/addr> + Ndata
    IN : bmRequestType=0xc1 bRequest=0x44  wValue=0x0078 wIndex=<cmd/addr> -> Ndata

Usage:
    python tools/parse_vendor.py <capture.pcap> [--out] [--in] [--max-len N]
                                 [--timeline] [--counts]
"""
from __future__ import annotations
import struct
import sys
import argparse
from collections import Counter

DLT_USBPCAP = 249


def read_pcap(path: str):
    with open(path, "rb") as f:
        gh = f.read(24)
        magic = gh[:4]
        if magic in (b"\xd4\xc3\xb2\xa1", b"\xa1\xb2\xc3\xd4"):
            le = magic == b"\xd4\xc3\xb2\xa1"
        else:
            raise SystemExit("not a classic pcap (pcapng not supported here)")
        endian = "<" if le else ">"
        usec_div = 1_000_000
        while True:
            rh = f.read(16)
            if len(rh) < 16:
                break
            ts_sec, ts_usec, incl, orig = struct.unpack(endian + "IIII", rh)
            data = f.read(incl)
            if len(data) < incl:
                break
            yield ts_sec + ts_usec / usec_div, data


def parse_usbpcap(payload: bytes):
    """Return dict for a control transfer, else None."""
    if len(payload) < 28:
        return None
    header_len = struct.unpack_from("<H", payload, 0)[0]
    if header_len < 27 or header_len > len(payload):
        return None
    endpoint = payload[21]
    transfer = payload[22]            # 0=iso 1=int 2=control 3=bulk
    data_len = struct.unpack_from("<I", payload, 23)[0]
    if transfer != 2:
        return None
    body = payload[header_len:]
    if len(body) < 8:
        return None
    setup = body[:8]
    bmReqType, bRequest, wValue, wIndex, wLength = struct.unpack("<BBHHH", setup)
    stage_data = body[8:8 + wLength]
    return {
        "bmReqType": bmReqType, "bRequest": bRequest,
        "wValue": wValue, "wIndex": wIndex, "wLength": wLength,
        "data": stage_data, "ep": endpoint,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pcap")
    ap.add_argument("--out", action="store_true", help="only OUT (writes)")
    ap.add_argument("--in", dest="in_", action="store_true", help="only IN (reads)")
    ap.add_argument("--max-len", type=int, default=64,
                    help="only show transfers with wLength <= this (commands, not tables)")
    ap.add_argument("--timeline", action="store_true",
                    help="print every matching transfer with timestamp")
    ap.add_argument("--counts", action="store_true",
                    help="print frequency of each distinct (dir,wIndex,data)")
    args = ap.parse_args()

    rows = []
    for ts, payload in read_pcap(args.pcap):
        rec = parse_usbpcap(payload)
        if rec is None:
            continue
        # vendor type = bmRequestType bits 6:5 == 10b
        if (rec["bmReqType"] & 0x60) != 0x40:
            continue
        rec["t"] = ts
        rows.append(rec)

    if not rows:
        print("No vendor control transfers found.")
        return 0
    t0 = rows[0]["t"]

    def is_out(r):
        return (r["bmReqType"] & 0x80) == 0

    sel = []
    for r in rows:
        if args.out and not is_out(r):
            continue
        if args.in_ and is_out(r):
            continue
        if r["wLength"] > args.max_len:
            continue
        sel.append(r)

    if args.counts:
        c = Counter()
        for r in sel:
            d = "OUT" if is_out(r) else "IN "
            c[(d, r["wValue"], r["wIndex"], r["data"].hex())] += 1
        print(f"{'count':>6}  {'dir':3} {'wValue':>6} {'wIndex':>6}  data")
        print("-" * 70)
        for (d, wv, wi, data), n in c.most_common():
            print(f"{n:>6}  {d} {wv:#06x} {wi:#06x}  {data}")
        return 0

    # default / timeline
    print(f"{'t(s)':>10}  {'dir':3} {'bReq':>4} {'wValue':>6} {'wIndex':>6} "
          f"{'len':>4}  data")
    print("-" * 80)
    for r in sel:
        d = "OUT" if is_out(r) else "IN "
        print(f"{r['t']-t0:>10.4f}  {d} {r['bRequest']:#04x} {r['wValue']:#06x} "
              f"{r['wIndex']:#06x} {r['wLength']:>4}  {r['data'].hex()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
