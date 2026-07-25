# Aether desktop launcher.
#
# Uses pythonw.exe so no console window flashes on launch. For debugging,
# run the shell directly with python.exe -m desktop.main to get logs on
# stderr.

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonw  = Join-Path $repoRoot ".venv\Scripts\pythonw.exe"

if (-not (Test-Path $pythonw)) {
    Write-Error "pythonw.exe not found at $pythonw. Create the venv first: py -3.13 -m venv .venv"
    exit 1
}

Start-Process -FilePath $pythonw -ArgumentList "-m", "desktop.main" -WorkingDirectory $repoRoot
