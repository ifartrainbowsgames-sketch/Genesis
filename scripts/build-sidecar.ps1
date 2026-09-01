param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ServerDir = Join-Path $Root "apps/server"
$TauriDir = Join-Path $Root "apps/desktop/src-tauri"
$BinariesDir = Join-Path $TauriDir "binaries"
$BuildDir = Join-Path $Root "build/sidecar"
$WorkDir = Join-Path $Root "build/pyinstaller"
$SpecDir = Join-Path $Root "build/spec"

$VenvPython = Join-Path $Root ".venv/Scripts/python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
} else {
    $Python = "python"
}

if (-not $SkipInstall) {
    & $Python -m pip install -r (Join-Path $ServerDir "requirements-build.txt")
}

$RustInfo = $null
try {
    $RustInfo = & rustc -vV 2>$null
} catch {
    $RustInfo = $null
}

$TargetTriple = $null
if ($RustInfo) {
    $HostLine = $RustInfo | Where-Object { $_ -like "host:*" } | Select-Object -First 1
    if ($HostLine) {
        $TargetTriple = ($HostLine -replace "^host:\s*", "").Trim()
    }
}

if (-not $TargetTriple) {
    if ($env:PROCESSOR_ARCHITECTURE -eq "ARM64") {
        $TargetTriple = "aarch64-pc-windows-msvc"
    } else {
        $TargetTriple = "x86_64-pc-windows-msvc"
    }
}

New-Item -ItemType Directory -Force -Path $BinariesDir, $BuildDir, $WorkDir, $SpecDir | Out-Null

& $Python -m PyInstaller `
    --clean `
    --noconfirm `
    --onefile `
    --name genesis-server `
    --distpath $BuildDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    --paths $ServerDir `
    (Join-Path $ServerDir "sidecar_entry.py")

$BuiltExe = Join-Path $BuildDir "genesis-server.exe"
$BuiltUnix = Join-Path $BuildDir "genesis-server"
if (Test-Path $BuiltExe) {
    $SourceBinary = $BuiltExe
    $DestinationBinary = Join-Path $BinariesDir "genesis-server-$TargetTriple.exe"
} elseif (Test-Path $BuiltUnix) {
    $SourceBinary = $BuiltUnix
    $DestinationBinary = Join-Path $BinariesDir "genesis-server-$TargetTriple"
} else {
    throw "PyInstaller completed but the Genesis sidecar binary was not found."
}

Copy-Item -Force $SourceBinary $DestinationBinary
Write-Host "Genesis sidecar ready: $DestinationBinary"
Write-Host "Target triple: $TargetTriple"
