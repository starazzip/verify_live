param(
  [string]$ApiHost = "127.0.0.1",
  [int]$ApiPort = 8011,
  [int]$WebPort = 5179
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptDir "..")

$apiScript = Join-Path $scriptDir "start_verify_live_api.ps1"
$webScript = Join-Path $scriptDir "start_verify_live_web.ps1"
$apiBase = "http://$ApiHost`:$ApiPort"
$webUrl = "http://127.0.0.1:$WebPort"

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  "`"$apiScript`"",
  "-ApiHost",
  $ApiHost,
  "-Port",
  $ApiPort
)

Start-Sleep -Seconds 1

Start-Process powershell -ArgumentList @(
  "-NoExit",
  "-ExecutionPolicy",
  "Bypass",
  "-File",
  "`"$webScript`"",
  "-ApiBase",
  $apiBase
)

Start-Sleep -Seconds 2
Start-Process $webUrl
