$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
  throw ".env is missing. Run ./scripts/setup.ps1 first."
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

Write-Host "Genesis started."
Write-Host "Web: http://localhost:3000"
Write-Host "API: http://localhost:8000/docs"
Write-Host "Server PID: $($Server.Id)  Web PID: $($Web.Id)"
