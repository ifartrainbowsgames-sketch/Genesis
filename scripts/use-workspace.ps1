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
$AllowedRoot = (Split-Path -Parent $Resolved).Replace("\\", "/")
$Content = Get-Content ".env"
$FoundWorkspace = $false
$FoundAllowed = $false
$Updated = foreach ($Line in $Content) {
  if ($Line -match '^WORKSPACE_ROOT=') {
    $FoundWorkspace = $true
    "WORKSPACE_ROOT=$Escaped"
  } elseif ($Line -match '^WORKSPACE_ALLOWED_ROOTS=') {
    $FoundAllowed = $true
    "WORKSPACE_ALLOWED_ROOTS=$AllowedRoot"
  } else {
    $Line
  }
}
if (-not $FoundWorkspace) { $Updated += "WORKSPACE_ROOT=$Escaped" }
if (-not $FoundAllowed) { $Updated += "WORKSPACE_ALLOWED_ROOTS=$AllowedRoot" }
Set-Content ".env" $Updated
Write-Host "Genesis workspace set to: $Resolved"
Write-Host "Repository selector allowed root: $AllowedRoot"
Write-Host "Restart the Genesis API if it is already running."
