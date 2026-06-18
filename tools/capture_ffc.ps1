<#
  capture_ffc.ps1 — capture the Tiny1C's USB init/FFC vendor commands.

  RUN THIS IN AN ELEVATED POWERSHELL (Run as Administrator) — USBPcap needs admin.

      powershell -ExecutionPolicy Bypass -File tools\capture_ffc.ps1

  It auto-detects which USB root hub the Tiny1C (VID 0BDA) is on, starts a
  capture, waits while you drive the Windows app, then decodes the Extension
  Unit (vdcmd) commands.
#>

$ErrorActionPreference = "Stop"

$USBPcap = "C:\Program Files\USBPcap\USBPcapCMD.exe"
$TShark  = "C:\Program Files\Wireshark\tshark.exe"
$OutDir  = $env:TEMP
$Capture = Join-Path $OutDir "tiny1c_init.pcap"
$DecodePy = Join-Path $PSScriptRoot "decode_xu.py"

# --- admin check ---------------------------------------------------------
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object System.Security.Principal.WindowsPrincipal($id)
if (-not $pr.IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "ERROR: not elevated. Re-open PowerShell with 'Run as Administrator'." -ForegroundColor Red
    exit 1
}
foreach ($exe in @($USBPcap, $TShark)) {
    if (-not (Test-Path $exe)) { Write-Host "ERROR: missing $exe" -ForegroundColor Red; exit 1 }
}

# --- find which USBPcap root hub has the Tiny1C (VID 0bda) ---------------
Write-Host "Detecting which USB root hub the Tiny1C is on..." -ForegroundColor Cyan
$hub = $null
foreach ($n in 1..8) {
    $dev = "\\.\USBPcap$n"
    $probe = Join-Path $OutDir "hubprobe$n.pcap"
    Remove-Item $probe -ErrorAction SilentlyContinue
    $p = Start-Process -FilePath $USBPcap `
        -ArgumentList @("-d", $dev, "-A", "--inject-descriptors", "-o", $probe) `
        -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 2
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
    if ((Test-Path $probe) -and (Get-Item $probe).Length -gt 24) {
        $match = & $TShark -r $probe -Y "usb.idVendor == 0x0bda" -T fields -e usb.idVendor 2>$null
        if ($match) { $hub = $dev; Write-Host "  -> Tiny1C found on $dev" -ForegroundColor Green; break }
    }
}
if (-not $hub) {
    Write-Host "Could not auto-detect the hub. Is the camera plugged in?" -ForegroundColor Red
    Write-Host "Run '$USBPcap' manually to see the device tree." -ForegroundColor Yellow
    exit 1
}

# --- start the real capture ----------------------------------------------
Remove-Item $Capture -ErrorAction SilentlyContinue
Write-Host "`nStarting capture on $hub -> $Capture" -ForegroundColor Cyan
$cap = Start-Process -FilePath $USBPcap `
    -ArgumentList @("-d", $hub, "-A", "--inject-descriptors", "-o", $Capture) `
    -PassThru -WindowStyle Hidden

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host " CAPTURE IS RUNNING. Now, in this order:" -ForegroundColor Yellow
Write-Host "   1. Launch the Mechanic-Ti / CAAnalyzer app." -ForegroundColor Yellow
Write-Host "   2. Wait for the live thermal image to appear." -ForegroundColor Yellow
Write-Host "   3. Press the FFC / shutter / calibrate button 2-3 times." -ForegroundColor Yellow
Write-Host "   4. Come back here and press ENTER to stop." -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Read-Host "Press ENTER to stop capture"

if (-not $cap.HasExited) { Stop-Process -Id $cap.Id -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 500

$sz = (Get-Item $Capture -ErrorAction SilentlyContinue).Length
Write-Host "`nCapture saved: $Capture ($sz bytes)" -ForegroundColor Green

# --- decode ---------------------------------------------------------------
Write-Host "`n===== Extension Unit (vdcmd) commands =====" -ForegroundColor Cyan
python $DecodePy $Capture
Write-Host "`nFull capture file: $Capture"
Write-Host "Re-run decode any time with:  python `"$DecodePy`" `"$Capture`""
