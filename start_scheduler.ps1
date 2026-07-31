param(
  [string]$EnvFile = "deploy/env/.env.dev"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
$CondaEnv = "pulsedeck"

if (-not (Test-Path $EnvFile)) {
  Write-Error "Missing $EnvFile"
}

Write-Host "[ENV] Ladowanie zmiennych srodowiskowych..."
$json = python -c "import json,sys; from pathlib import Path; sys.path.insert(0, r'$Root'); from scripts.load_env import parse_env_file; print(json.dumps(parse_env_file(sys.argv[1])))" "$EnvFile"
if ($LASTEXITCODE -ne 0) {
  Write-Error "Nie udalo sie odczytac env"
}
$pairs = $json | ConvertFrom-Json
foreach ($pair in $pairs) {
  Set-Item -Path "Env:$($pair[0])" -Value $pair[1]
}

Write-Host "[CONDA] Aktywacja srodowiska $CondaEnv..."
$condaHook = & conda "shell.powershell" "hook" 2>$null
if (-not $condaHook) {
  Write-Error "conda nie jest w PATH"
}
$condaHook | Out-String | Invoke-Expression
conda activate $CondaEnv
if ($env:CONDA_DEFAULT_ENV -ne $CondaEnv) {
  Write-Error "conda env `"$CondaEnv`" nie istnieje"
}

Write-Host "[MAIL] Worker outbox (Ctrl+C aby zatrzymac)"
python -m app.workers.mail
