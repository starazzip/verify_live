param(
  [string]$ApiBase = "http://127.0.0.1:8011"
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$webDir = Join-Path $root "verify_live_web"

Push-Location $webDir
try {
  $env:VITE_VERIFY_LIVE_API_BASE = $ApiBase
  npm run dev
} finally {
  Pop-Location
}

