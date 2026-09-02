$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

function Report-Command($Name, $Command) {
    $found = Get-Command $Command -ErrorAction SilentlyContinue
    if ($found) {
        Write-Host "[ready] $Name -> $($found.Source)"
        return $true
    }
    Write-Host "[missing] $Name ($Command)"
    return $false
}

Write-Host "Genesis Doctor"
Write-Host "=============="

$PythonReady = Report-Command "Python" "python"
$NodeReady = Report-Command "Node.js" "node"
$NpmReady = Report-Command "npm" "npm"
$GitReady = Report-Command "Git" "git"
$DockerReady = Report-Command "Docker" "docker"
$CargoReady = Report-Command "Rust/Cargo (desktop builds)" "cargo"

if (Test-Path ".env") {
    Write-Host "[ready] .env"
} else {
    Write-Host "[missing] .env -> run ./scripts/setup.ps1"
}

if (Test-Path ".venv\Scripts\python.exe") {
    Write-Host "[ready] Python virtual environment"
} else {
    Write-Host "[missing] .venv -> run ./scripts/setup.ps1"
}

if (Test-Path "apps\web\node_modules") {
    Write-Host "[ready] Web dependencies"
} else {
    Write-Host "[missing] apps/web/node_modules -> run ./scripts/setup.ps1"
}

if ($DockerReady) {
    try {
        docker compose config --quiet 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[ready] docker-compose.yml parses"
        } else {
            Write-Host "[warning] docker compose config failed"
        }
    } catch {
        Write-Host "[warning] Docker is installed but compose is not responding"
    }
}

try {
    $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/system/health" -TimeoutSec 3
    Write-Host "[server] $($health.status)"
    foreach ($entry in $health.components.PSObject.Properties) {
        Write-Host "  [$($entry.Value.status)] $($entry.Name): $($entry.Value.detail)"
    }
} catch {
    Write-Host "[info] Genesis API is not running on 127.0.0.1:8000; start it to run live dependency diagnostics."
}

Write-Host ""
if (-not ($PythonReady -and $NodeReady -and $NpmReady -and $GitReady)) {
    Write-Host "Core developer prerequisites are incomplete."
} else {
    Write-Host "Core developer prerequisites are present."
}
if (-not $CargoReady) {
    Write-Host "Rust is optional for web/API development but required for Tauri desktop builds."
}
