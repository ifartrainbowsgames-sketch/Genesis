$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example"
}

Write-Host "Creating Python virtual environment..."
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\pip.exe install -r apps/server/requirements.txt

Write-Host "Installing web dependencies..."
Push-Location apps/web
npm install
Pop-Location

Write-Host "Installing desktop shell dependencies..."
Push-Location apps/desktop
npm install
Pop-Location

if (Get-Command cargo -ErrorAction SilentlyContinue) {
  Write-Host "Rust detected."
  Write-Host "Desktop dev with packaged API sidecar: npm run desktop:dev:windows"
  Write-Host "Desktop installer build: npm run desktop:build:windows"
} else {
  Write-Host "Rust not detected. Web/API will work; install Rust before building the Tauri desktop app."
}

Write-Host "Setup complete."
Write-Host "Start local data + research services: docker compose up -d postgres searxng"
Write-Host "Then start the web workstation: ./scripts/start.ps1"
Write-Host "Optional local voice: set WHISPER_CPP_BINARY and WHISPER_CPP_MODEL in .env"
