# Builds dist\oneaudio-send.exe, dist\oneaudio-receive.exe and dist\OneAudio-Setup-<version>.exe.
# Usage: .\build.ps1 -Version 0.2.0
param([string]$Version = "0.0.0")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

pyinstaller --onefile --noconfirm --log-level WARN --name oneaudio-send sender.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }
pyinstaller --onefile --noconfirm --log-level WARN --name oneaudio-receive receiver.py
if ($LASTEXITCODE) { exit $LASTEXITCODE }

$iscc = @(
    (Get-Command iscc -ErrorAction SilentlyContinue).Source,
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 not found (winget install JRSoftware.InnoSetup)" }

& $iscc /Q "/DAppVersion=$Version" installer\oneaudio.iss
exit $LASTEXITCODE
