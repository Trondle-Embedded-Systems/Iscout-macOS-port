# Capturing the Tiny1C FFC / init command (Windows)

Goal: record the exact USB vendor commands the Windows app (`CAAnalyzer.exe` /
Mechanic-Ti VisualPlatform) sends to the camera, so we can replay the FFC and
stream-start on macOS.

What we already know (so decode is easy):
- Camera: **Tiny1C**, USB `0BDA:5840`.
- Command channel: UVC **Extension Unit id 4** on interface 0 →
  every command is a control transfer with **wIndex = 0x0400**.
- FFC = `basic_shutter_update`; stream enable = `i2c_start_stream`.

---

## 1. Install USBPcap  (one time, needs admin + reboot)

Download from the official site and run the installer **as Administrator**:

- https://desowin.org/usbpcap/  →  `USBPcapSetup-1.5.4.0.exe`
  (or the GitHub release: https://github.com/desowin/usbpcap/releases)

Accept the driver install, then **reboot** (required for the driver to load).

> My automated download was blocked by the network here (returned 9 bytes), so
> please grab it with your browser.

After reboot, confirm it's visible:

```
& "C:\Program Files\Wireshark\tshark.exe" -D
```
You should now see entries like `\\.\USBPcap1`, `\\.\USBPcap2`, …

---

## 2. Capture the init sequence

1. **Unplug** the thermal camera.
2. Start the capture (replace `USBPcap2` with whichever interface is the root
   hub the camera will be plugged into — if unsure, capture them all in
   separate terminals, or just try each):

   ```powershell
   & "C:\Program Files\Wireshark\dumpcap.exe" -i \\.\USBPcap2 -w "$env:TEMP\tiny1c_init.pcapng"
   ```

3. **Plug in** the camera, launch the Mechanic-Ti app, let the live image come
   up, then **press the FFC / shutter / calibrate button** in the app a couple
   of times (so the shutter command is unmistakable in the timeline).
4. Stop the capture (Ctrl-C in the dumpcap window).

(Alternative: just run **`USBPcapCMD.exe`** — it lists the device tree, you pick
the hub the camera is under, and it writes a `.pcap`.)

---

## 3. Decode

```powershell
python "tools\decode_xu.py" "$env:TEMP\tiny1c_init.pcapng"
```

This prints every control transfer to the Extension Unit (wIndex 0x0400) as
annotated hex. The `OUT/SET_CUR … [XU u4 CS=n]` rows are the vendor commands.
Use `--all` to see every control transfer if nothing shows up.

Send me that output (or the `.pcapng`) and I'll identify the FFC + stream-start
byte sequences and wire them into the macOS app.
