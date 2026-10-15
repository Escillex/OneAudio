# Builds dist\oneaudio-send.exe, dist\oneaudio-receive.exe, dist\oneaudio-tray.exe and
# dist\OneAudio-Setup-<version>.exe.
# Usage: .\build.ps1 -Version 0.2.0
param([string]$Version = "0.0.0")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Baked into the exes for update checks; removed afterwards so source runs stay "dev".
"VERSION = `"$Version`"" | Set-Content -Encoding ascii _version.py
# pystray only needs Pillow to draw the tray icon: leave out its codecs and anything that
# drags in numpy (several MB each).
$exclude = "numpy", "tkinter", "PIL.ImageQt", "PIL.ImageTk", "PIL._imagingft", "PIL._imagingcms",
    "PIL._imagingmath", "PIL._imagingmorph", "PIL._avif", "PIL._webp", "PIL.AvifImagePlugin",
    "PIL.WebPImagePlugin" | ForEach-Object { "--exclude-module", $_ }
try {
    pyinstaller --onefile --noconfirm --log-level WARN --hidden-import pystray._win32 @exclude --name oneaudio-send sender.py
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    pyinstaller --onefile --noconfirm --log-level WARN --hidden-import pystray._win32 @exclude --name oneaudio-receive receiver.py
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
    # Windowed (no console) build for the Start menu shortcuts.
    pyinstaller --onefile --windowed --noconfirm --log-level WARN --hidden-import pystray._win32 @exclude --name oneaudio-tray oneaudio_tray.py
    if ($LASTEXITCODE) { exit $LASTEXITCODE }

    $iscc = @(
        (Get-Command iscc -ErrorAction SilentlyContinue).Source,
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }

    & $iscc /Q "/DAppVersion=$Version" installer\oneaudio.iss
    exit $LASTEXITCODE
} finally {
    Remove-Item _version.py -ErrorAction SilentlyContinue
}
