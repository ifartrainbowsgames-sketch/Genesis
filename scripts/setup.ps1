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
  Write-Host "Rust detected. Desktop shell can be built with: npm run desktop:dev"
} else {
  Write-Host "Rust not detected. Web/API will work; install Rust before building the Tauri desktop shell."
}

Write-Host "Setup complete."
Write-Host "Next: docker compose up -d postgres"
Write-Host "Then: ./scripts/start.ps1"
