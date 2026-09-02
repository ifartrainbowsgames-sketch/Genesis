param(
  [switch]$SkipDocker,
  [switch]$SkipDoctor
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
  throw ".env is missing. Run ./scripts/setup.ps1 first."
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  throw "Python virtual environment is missing. Run ./scripts/setup.ps1 first."
}

if (-not $SkipDoctor) {
  Write-Host "Running Genesis Doctor..."
  & (Join-Path $Root "scripts/doctor.ps1")
}

if (-not $SkipDocker) {
  if (Get-Command docker -ErrorAction SilentlyContinue) {
    Write-Host "Starting PostgreSQL/pgvector and SearXNG..."
    docker compose up -d postgres searxng
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
  } else {
    Write-Warning "Docker was not found. Genesis can open, but persistent memory/research may be unavailable."
  }
}

if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  Write-Warning "Ollama was not found. Local model requests will fail until Ollama is installed and running."
} else {
  try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2
    Write-Host "Ollama is responding."
  } catch {
    Write-Warning "Ollama is installed but not responding on 127.0.0.1:11434. Start Ollama before using local models."
  }
}

$Server = Start-Process powershell -PassThru -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$Root'; .\.venv\Scripts\python.exe -m uvicorn apps.server.app.main:app --reload --port 8000"
)

$WebPath = Join-Path $Root "apps/web"
$Web = Start-Process powershell -PassThru -ArgumentList @(
  "-NoExit",
  "-Command",
  "Set-Location '$WebPath'; npm run dev"
)

$ApiReady = $false
for ($i = 0; $i -lt 30; $i++) {
  Start-Sleep -Seconds 1
  try {
    $Health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 2
    if ($Health.status -eq "ok") {
      $ApiReady = $true
      break
    }
  } catch {}
}

if (-not $ApiReady) {
  Write-Warning "Genesis processes started, but the API health endpoint was not ready after 30 seconds. Check the server window and run ./scripts/doctor.ps1."
} else {
  Write-Host "Genesis API is healthy."
}

Write-Host ""
Write-Host "Genesis started."
Write-Host "Workstation: http://localhost:3000"
Write-Host "Workbench:   http://localhost:3000/workbench"
Write-Host "Runtime:     http://localhost:3000/runtime"
Write-Host "Memory:      http://localhost:3000/memory"
Write-Host "Evolution:   http://localhost:3000/evolution"
Write-Host "Diagnostics: http://localhost:3000/diagnostics"
Write-Host "API docs:    http://localhost:8000/docs"
Write-Host "Server PID: $($Server.Id)  Web PID: $($Web.Id)"
