param(
  [Parameter(Mandatory=$true)]
  [string]$Path
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Resolved = (Resolve-Path $Path).Path
if (-not (Test-Path $Resolved -PathType Container)) {
  throw "Workspace path is not a directory: $Resolved"
}

if (-not (Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

$Escaped = $Resolved.Replace("\\", "/")
$Content = Get-Content ".env"
$Found = $false
$Updated = foreach ($Line in $Content) {
  if ($Line -match '^WORKSPACE_ROOT=') {
    $Found = $true
    "WORKSPACE_ROOT=$Escaped"
  } else {
    $Line
  }
}
if (-not $Found) {
  $Updated += "WORKSPACE_ROOT=$Escaped"
}
Set-Content ".env" $Updated
Write-Host "Genesis workspace set to: $Resolved"
