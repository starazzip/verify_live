param(
  [string]$ApiHost = "127.0.0.1",
  [int]$Port = 8011
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")
$apiDir = Join-Path $root "verify_live_api"

Push-Location $apiDir
try {
  $envFile = Join-Path $root ".env"
  if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
      $line = $_.Trim()
      if (-not $line -or $line.StartsWith("#")) { return }
      $parts = $line.Split("=", 2)
      if ($parts.Count -eq 2) {
        [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
      }
    }
  }

  $py = $null
  if (Test-Path (Join-Path $apiDir ".venv\\Scripts\\python.exe")) {
    $py = Join-Path $apiDir ".venv\\Scripts\\python.exe"
  } elseif (Test-Path (Join-Path $root "..\\.venv\\Scripts\\python.exe")) {
    $py = Join-Path $root "..\\.venv\\Scripts\\python.exe"
  } else {
    $py = "python"
  }

  & $py -m uvicorn app.main:app --host $ApiHost --port $Port
} finally {
  Pop-Location
}
